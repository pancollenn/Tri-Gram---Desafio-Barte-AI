#!/usr/bin/env python3
"""Testes automatizados e validação completa para `src/engine/notas.py`.

Missão 3: Faturamento e Emissão de Notas Fiscais de Serviços (NFS-e)
Regras Oficiais de Faturamento:
1. Checkout: Emitir uma nota fiscal individual para cada lojista ativo cujo saldo
   líquido de comissão de checkout seja estritamente positivo (`> R$ 0.00`).
   - Lojistas com comissão zero (ex.: Casa do Estudante, taxa 0.00%) NÃO emitem nota fiscal.
   - Lojistas com comissão negativa (estornos superando vendas) NÃO emitem nota fiscal.
   - Estabelecimentos sem contrato assinado em 2026 (ex.: Atlas Idiomas) são bloqueados.
2. Remessas: Emitir exatamente UMA ÚNICA NOTA FISCAL consolidada contra a parceira
   Ponte Câmbio S.A. (CNPJ `75374179000146`) pelo somatório das comissões válidas de
   remessa do mês (excluindo os 4 spreads negativos e a duplicata PC-0926-0162).
3. Rastreabilidade (`rastro.csv`): Amarrar cada `id_saida` (`NF-xxxx`) às transações
   da Orbe ou operações da Ponte Câmbio que compõem o valor faturado, garantindo que
   a soma no rastro feche centavo a centavo com `valor_brl`.

Este script valida exaustivamente:
1. Regras unitárias de Checkout (notas individuais, exclusão taxa zero e saldo negativo, bloqueio sem contrato).
2. Regras unitárias de Remessas (nota única consolidada contra a Ponte, expurgo de spreads negativos e duplicatas).
3. Contrato de saída de `notas_a_emitir.csv` (6 colunas estritas, tipos, CNPJ 14 dígitos, valores > 0, unicidade de IDs).
4. Rastreabilidade matemática absoluta (cada nota fiscal amarrada centavo a centavo no `RastroTracker`).
5. Casos de borda e resiliência (entradas vazias/nulas, sem tracker, competência dinâmica, helpers de fallback).
6. Integração completa com o dataset real de fechamento (`data_pack/`).

Uso:
    python tests/test_notas.py               # Executa bateria completa (unitários + integração)
    python tests/test_notas.py --unitario    # Executa apenas bateria de regras unitárias
    python tests/test_notas.py --integrado   # Executa apenas integração com data_pack
    python tests/test_notas.py -v            # Modo verboso
    python -m unittest tests/test_notas.py   # Executa via runner padrão do unittest
"""
from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional
import unittest

# Permite execução direta a partir de qualquer diretório de trabalho
_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from src import config
from src.engine import comissoes, notas
from src.engine.notas import (
    gerar_notas_a_emitir,
    emitir_notas,
    calcular_notas,
    gerar_notas,
    _inferir_competencia,
    _normalizar_texto,
    _fallback_para_decimal,
    _fallback_round_half_up,
    _fallback_clean_cnpj,
    PREFIXO_NOTA,
    LINHA_CHECKOUT,
    LINHA_REMESSA,
    PONTE_CAMBIO_CNPJ,
    PONTE_CAMBIO_NOME,
    EC_ATLAS_IDIOMAS,
    EC_CASA_DO_ESTUDANTE,
)
from src.engine.rastro import RastroTracker
from src.main import _serializar
from src.parsers import parse_orbe, parse_ponte


class TestRunner:
    """Coletor e formatador de resultados de testes CLI."""

    def __init__(self, verboso: bool = False):
        self.verboso = verboso
        self.sucessos = 0
        self.falhas = 0

    def asserir(self, condicao: bool, mensagem: str, detalhe: Optional[str] = None) -> None:
        if condicao:
            self.sucessos += 1
            print(f"  [OK]    {mensagem}")
        else:
            self.falhas += 1
            print(f"  [ERRO]  {mensagem}")
            if detalhe:
                print(f"          -> Detalhe: {detalhe}")


# ============================================================================
# 1. BATERIA DE TESTES UNITÁRIOS SINTÉTICOS (REGRAS DE NEGÓCIO)
# ============================================================================
def testar_casos_unitarios(runner: TestRunner) -> None:
    """Valida todas as regras de faturamento com fixtures e dados sintéticos controlados."""
    print("\n" + "=" * 70)
    print(" 1. TESTES UNITÁRIOS SINTÉTICOS: CHECKOUT (NOTAS INDIVIDUAIS)")
    print("=" * 70)

    tracker_ck = RastroTracker()
    arquivo_ck = "01_orbe_relatorio_comissoes_set2026.csv"

    # Dataset sintético com 5 lojistas:
    # 1. Bridge Idiomas: Comissão positiva -> EMITE NOTA
    # 2. Dublin Hub: Comissão positiva -> EMITE NOTA
    # 3. Casa do Estudante: Taxa 0.00% (comissão 0.00) -> NÃO EMITE NOTA
    # 4. Estorno Total: Saldo negativo (estornos > vendas) -> NÃO EMITE NOTA
    # 5. Atlas Idiomas: Sem contrato assinado em 2026 -> BLOQUEADO / NÃO EMITE NOTA
    dados_mock_checkout: Dict[str, Any] = {
        "arquivo_origem": arquivo_ck,
        "transacoes": [
            # Lojista 1: Bridge Idiomas (Venda R$ 10.000,00 @ 2.50% = R$ 250,00)
            {
                "id_transacao": "TX-CK-01",
                "cod_estabelecimento": "1075624862",
                "cnpj": "22.224.579/0001-09",
                "lojista": "Bridge Idiomas",
                "valor_bruto": Decimal("10000.00"),
                "taxa_contratada_pct": Decimal("2.50"),
                "data_movimento": "2026-09-10",
            },
            # Lojista 2: Dublin Hub (Venda R$ 20.000,00 @ 2.00% = R$ 400,00)
            {
                "id_transacao": "TX-CK-02",
                "cod_estabelecimento": "1088992211",
                "cnpj": "68.567.965/0001-02",
                "lojista": "Dublin Hub Intercâmbio Ltda",
                "valor_bruto": Decimal("20000.00"),
                "taxa_contratada_pct": Decimal("2.00"),
                "data_movimento": "2026-09-12",
            },
            # Lojista 3: Casa do Estudante (Venda R$ 5.000,00 @ 0.00% contratada = R$ 0,00)
            {
                "id_transacao": "TX-CK-03",
                "cod_estabelecimento": EC_CASA_DO_ESTUDANTE,
                "cnpj": "00.520.815/0001-00",
                "lojista": "Casa do Estudante Viagens",
                "valor_bruto": Decimal("5000.00"),
                "taxa_contratada_pct": Decimal("0.00"),
                "data_movimento": "2026-09-15",
            },
            # Lojista 4: Saldo Negativo (Estornos de R$ -10.000,00 @ 3.00% = R$ -300,00)
            {
                "id_transacao": "TX-CK-04",
                "cod_estabelecimento": "1099887766",
                "cnpj": "99.887.766/0001-55",
                "lojista": "Lojista com Saldo Negativo",
                "valor_bruto": Decimal("-10000.00"),
                "taxa_contratada_pct": Decimal("3.00"),
                "data_movimento": "2026-09-18",
            },
            # Lojista 5: Atlas Idiomas (Sem contrato 2026: R$ 15.000,00 @ 3.00% = R$ 450,00)
            {
                "id_transacao": "TX-CK-05",
                "cod_estabelecimento": EC_ATLAS_IDIOMAS,
                "cnpj": "10.768.017/0001-32",
                "lojista": "Atlas Idiomas",
                "valor_bruto": Decimal("15000.00"),
                "taxa_contratada_pct": Decimal("3.00"),
                "sem_contrato": True,
                "data_movimento": "2026-09-20",
            },
        ],
    }

    # Gera comissões prévias sintéticas correspondentes
    comissoes_mock_checkout: List[Dict[str, Any]] = [
        {
            "id_saida": "COM-0001",
            "cnpj": "22224579000109",
            "lojista": "Bridge Idiomas",
            "linha_negocio": LINHA_CHECKOUT,
            "comissao_brl": Decimal("250.00"),
        },
        {
            "id_saida": "COM-0002",
            "cnpj": "68567965000102",
            "lojista": "Dublin Hub Intercâmbio Ltda",
            "linha_negocio": LINHA_CHECKOUT,
            "comissao_brl": Decimal("400.00"),
        },
        {
            "id_saida": "COM-0003",
            "cnpj": "00520815000100",
            "lojista": "Casa do Estudante Viagens",
            "linha_negocio": LINHA_CHECKOUT,
            "comissao_brl": Decimal("0.00"),
        },
        {
            "id_saida": "COM-0004",
            "cnpj": "99887766000155",
            "lojista": "Lojista com Saldo Negativo",
            "linha_negocio": LINHA_CHECKOUT,
            "comissao_brl": Decimal("-300.00"),
        },
    ]

    notas_ck = notas.gerar_notas_a_emitir(
        comissoes=comissoes_mock_checkout,
        dados_checkout=dados_mock_checkout,
        tracker=tracker_ck,
    )

    # Validação 1: Exatamente 2 notas geradas (apenas lojistas com comissão > 0 e com contrato)
    runner.asserir(
        len(notas_ck) == 2,
        "Checkout: apenas lojistas ativos com comissão > 0.00 emitiram nota (Bridge e Dublin Hub)",
        f"Obtido: {len(notas_ck)} notas (esperado: 2)",
    )

    cnpjs_emitidos = {n["tomador_cnpj"] for n in notas_ck}
    runner.asserir(
        cnpjs_emitidos == {"22224579000109", "68567965000102"},
        "Checkout: notas emitidas exclusivamente para Bridge (22224579000109) e Dublin Hub (68567965000102)",
        f"Emitidos: {cnpjs_emitidos}",
    )

    # Validação 2: Casa do Estudante (taxa 0.00) NÃO emite nota
    runner.asserir(
        "00520815000100" not in cnpjs_emitidos,
        "Checkout Casa do Estudante: comissão R$ 0.00 não emitiu nota fiscal (conforme regra do edital)",
    )

    # Validação 3: Saldo Negativo NÃO emite nota
    runner.asserir(
        "99887766000155" not in cnpjs_emitidos,
        "Checkout Saldo Negativo: comissão < R$ 0.00 não emitiu nota fiscal",
    )

    # Validação 4: Atlas Idiomas (sem contrato) NÃO emite nota
    runner.asserir(
        "10768017000132" not in cnpjs_emitidos,
        "Checkout Atlas Idiomas: estabelecimento sem contrato 2026 não emitiu nota fiscal",
    )

    # Validação 5: Valores e Discriminação
    nota_bridge = next((n for n in notas_ck if n["tomador_cnpj"] == "22224579000109"), None)
    runner.asserir(
        nota_bridge is not None and nota_bridge["valor_brl"] == Decimal("250.00"),
        "Checkout Bridge Idiomas: nota emitida com valor exato de R$ 250.00",
        f"Obtido: {nota_bridge.get('valor_brl') if nota_bridge else 'None'}",
    )
    runner.asserir(
        nota_bridge is not None and "09/2026" in nota_bridge["discriminacao"],
        "Checkout Discriminação: discriminação contém a competência inferida (09/2026)",
    )

    # Validação 6: Rastreabilidade de Checkout no RastroTracker
    runner.asserir(
        tracker_ck.total(nota_bridge["id_saida"]) == Decimal("250.00"),
        "Rastreabilidade Checkout: rastro de Bridge Idiomas fecha centavo a centavo (R$ 250.00)",
    )

    # Validação 7: Modo autônomo (sem comissoes passadas previamente)
    tracker_ck_autonomo = RastroTracker()
    notas_ck_autonomas = notas.gerar_notas_a_emitir(
        dados_checkout=dados_mock_checkout,
        tracker=tracker_ck_autonomo,
    )
    runner.asserir(
        len(notas_ck_autonomas) == 2,
        "Checkout Modo Autônomo: reconstruiu notas diretamente dos dados de checkout sem lista de comissões",
        f"Obtido: {len(notas_ck_autonomas)} notas",
    )

    print("\n" + "=" * 70)
    print(" 2. TESTES UNITÁRIOS SINTÉTICOS: REMESSAS (NOTA ÚNICA CONSOLIDADA)")
    print("=" * 70)

    tracker_rem = RastroTracker()
    arquivo_rem = "03_email_ponte_cambio_relatorio_set2026.eml"

    dados_mock_remessas: Dict[str, Any] = {
        "arquivo_origem": arquivo_rem,
        "operacoes_validas": [
            # Op 1: Válida de R$ 10.000,00 -> Spread R$ 200,00 -> Comissão 50% = R$ 100,00
            {
                "ref_origem": "PC-REM-01",
                "num_operacao": "PC-REM-01",
                "lojista": "Mundo Aberto Intercâmbio",
                "spread_brl": Decimal("200.00"),
                "comissao_tarvo_brl": Decimal("100.00"),
                "data": "2026-09-05",
            },
            # Op 2: Válida de R$ 30.000,00 -> Spread R$ 500,00 -> Comissão 50% = R$ 250,00
            {
                "ref_origem": "PC-REM-02",
                "num_operacao": "PC-REM-02",
                "lojista": "Turismo Austral",
                "spread_brl": Decimal("500.00"),
                "comissao_tarvo_brl": Decimal("250.00"),
                "data": "2026-09-08",
            },
        ],
        "operacoes_spread_negativo": [
            # Op 3: Spread Negativo (trava de 2h estourada) -> NÃO ENTRA NA NOTA
            {
                "ref_origem": "PC-REM-NEG",
                "num_operacao": "PC-REM-NEG",
                "spread_brl": Decimal("-450.00"),
                "is_spread_negativo": True,
            }
        ],
        "operacoes_duplicadas": [
            # Op 4: Operação Duplicada -> NÃO ENTRA NA NOTA
            {
                "ref_origem": "PC-0926-0162",
                "num_operacao": "PC-0926-0162",
                "spread_brl": Decimal("821.88"),
                "is_duplicada": True,
            }
        ],
    }

    comissoes_mock_remessas: List[Dict[str, Any]] = [
        {
            "id_saida": "COM-0010",
            "cnpj": "17217888000111",
            "lojista": "Mundo Aberto Intercâmbio",
            "linha_negocio": LINHA_REMESSA,
            "comissao_brl": Decimal("100.00"),
        },
        {
            "id_saida": "COM-0011",
            "cnpj": "95739378000118",
            "lojista": "Turismo Austral",
            "linha_negocio": LINHA_REMESSA,
            "comissao_brl": Decimal("250.00"),
        },
    ]

    notas_rem = notas.gerar_notas_a_emitir(
        comissoes=comissoes_mock_remessas,
        dados_remessas=dados_mock_remessas,
        tracker=tracker_rem,
    )

    # Validação 8: Exatamente 1 nota gerada para remessa (contra Ponte Câmbio S.A.)
    runner.asserir(
        len(notas_rem) == 1,
        "Remessas: gerada exatamente UMA ÚNICA NOTA FISCAL consolidada",
        f"Obtido: {len(notas_rem)} notas",
    )

    nota_ponte = notas_rem[0]
    runner.asserir(
        nota_ponte["tomador_cnpj"] == PONTE_CAMBIO_CNPJ and nota_ponte["tomador"] == PONTE_CAMBIO_NOME,
        f"Remessas Tomador: nota emitida contra {PONTE_CAMBIO_NOME} (CNPJ {PONTE_CAMBIO_CNPJ})",
        f"Obtido: {nota_ponte['tomador']} - {nota_ponte['tomador_cnpj']}",
    )
    runner.asserir(
        nota_ponte["linha_negocio"] == LINHA_REMESSA,
        "Remessas Linha de Negócio: classificada estritamente como 'REMESSA'",
    )
    runner.asserir(
        nota_ponte["valor_brl"] == Decimal("350.00"),
        "Remessas Valor Consolidado: soma exata de R$ 350.00 (100.00 + 250.00), expurgando spreads negativos e duplicatas",
        f"Obtido: {nota_ponte['valor_brl']}",
    )

    # Validação 9: Rastreabilidade de Remessas no RastroTracker
    runner.asserir(
        tracker_rem.total(nota_ponte["id_saida"]) == Decimal("350.00"),
        "Rastreabilidade Remessas: rastro da nota da Ponte Câmbio fecha centavo a centavo (R$ 350.00)",
    )

    # Validação 10: Remessas com fallback de operações planas (sem operacoes_validas pré-segregadas)
    dados_mock_rem_plana: Dict[str, Any] = {
        "arquivo_origem": arquivo_rem,
        "operacoes": [
            {
                "ref_origem": "PC-PL-01",
                "lojista": "Cliente A",
                "spread_brl": Decimal("400.00"),
            },
            {
                "ref_origem": "PC-PL-02",
                "lojista": "Cliente B",
                "spread_brl": Decimal("600.00"),
            },
            {
                "ref_origem": "PC-PL-NEG",
                "lojista": "Cliente C",
                "spread_brl": Decimal("-200.00"),  # negativo ignorado
            },
            {
                "ref_origem": "PC-PL-DUP",
                "lojista": "Cliente D",
                "spread_brl": Decimal("100.00"),
            },
            {
                "ref_origem": "PC-PL-DUP",  # repetido ignorado
                "lojista": "Cliente D",
                "spread_brl": Decimal("100.00"),
            },
        ],
    }
    tracker_rem_plano = RastroTracker()
    notas_rem_plano = notas.gerar_notas_a_emitir(
        dados_remessas=dados_mock_rem_plana,
        tracker=tracker_rem_plano,
    )
    # Válidas: PL-01 (50% de 400 = 200), PL-02 (50% de 600 = 300), PL-DUP (50% de 100 = 50) -> Total: 550.00
    runner.asserir(
        len(notas_rem_plano) == 1 and notas_rem_plano[0]["valor_brl"] == Decimal("550.00"),
        "Remessas Fallback Operações Planas: filtrou negativos e duplicatas diretamente da lista plana (R$ 550.00)",
        f"Obtido: {notas_rem_plano[0]['valor_brl'] if notas_rem_plano else 'None'}",
    )


# ============================================================================
# 2. BATERIA DE CONTRATO, FORMATO E RASTRO MATEMÁTICO
# ============================================================================
def testar_contrato_e_rastro(runner: TestRunner) -> None:
    """Valida especificações estritas de schema do edital, IDs únicos e rastro."""
    print("\n" + "=" * 70)
    print(" 3. TESTES DE CONTRATO, FORMATO E RASTREABILIDADE MATEMÁTICA")
    print("=" * 70)

    tracker_global = RastroTracker()

    dados_mock_ck: Dict[str, Any] = {
        "arquivo_origem": "01_orbe_relatorio_comissoes_set2026.csv",
        "transacoes": [
            {
                "id_transacao": "TX-01",
                "cod_estabelecimento": "1001",
                "cnpj": "22.224.579/0001-09",
                "lojista": "Lojista Um",
                "valor_bruto": Decimal("1000.00"),
                "taxa_contratada_pct": Decimal("2.50"),
            },
            {
                "id_transacao": "TX-02",
                "cod_estabelecimento": "1002",
                "cnpj": "68.567.965/0001-02",
                "lojista": "Lojista Dois",
                "valor_bruto": Decimal("2000.00"),
                "taxa_contratada_pct": Decimal("3.00"),
            },
        ],
    }

    dados_mock_rem: Dict[str, Any] = {
        "arquivo_origem": "03_email_ponte_cambio_relatorio_set2026.eml",
        "operacoes_validas": [
            {
                "ref_origem": "PC-01",
                "lojista": "Lojista Três",
                "spread_brl": Decimal("500.00"),
                "comissao_tarvo_brl": Decimal("250.00"),
            }
        ],
    }

    todas_notas = notas.gerar_notas_a_emitir(
        dados_checkout=dados_mock_ck,
        dados_remessas=dados_mock_rem,
        tracker=tracker_global,
    )

    # 1. Total: 2 de checkout + 1 de remessa = 3 notas
    runner.asserir(
        len(todas_notas) == 3,
        "Consolidação Global: geradas 3 notas (2 checkout + 1 remessa)",
        f"Obtido: {len(todas_notas)}",
    )

    # 2. Contrato de Colunas
    colunas_obrigatorias = config.ARQUIVOS_SAIDA[config.ARQ_NOTAS].colunas
    todos_campos_ok = all(
        all(col in n for col in colunas_obrigatorias) for n in todas_notas
    )
    runner.asserir(
        todos_campos_ok,
        f"Contrato: todos os registros possuem exatamente as colunas {colunas_obrigatorias}",
    )

    # 3. Unicidade e Prefixo de id_saida
    ids = [n["id_saida"] for n in todas_notas]
    runner.asserir(
        len(ids) == len(set(ids)),
        f"Unicidade: todos os id_saida são únicos e distintos ({ids})",
    )
    runner.asserir(
        all(i.startswith(f"{PREFIXO_NOTA}-") for i in ids),
        f"Prefixo: todos os id_saida iniciam com '{PREFIXO_NOTA}-'",
    )

    # 4. Domínio de Linha de Negócio e Tomador
    linhas_validas = {LINHA_CHECKOUT, LINHA_REMESSA}
    runner.asserir(
        all(n["linha_negocio"] in linhas_validas for n in todas_notas),
        f"Domínio linha_negocio: todos os registros são {linhas_validas}",
    )
    remessas = [n for n in todas_notas if n["linha_negocio"] == LINHA_REMESSA]
    runner.asserir(
        len(remessas) == 1 and remessas[0]["tomador_cnpj"] == PONTE_CAMBIO_CNPJ,
        f"Regra estrita: exatamente 1 nota de REMESSA contra o CNPJ da Ponte Câmbio ({PONTE_CAMBIO_CNPJ})",
    )

    # 5. CNPJ com exatamente 14 dígitos
    cnpjs_validos = all(
        len(n["tomador_cnpj"]) == 14 and n["tomador_cnpj"].isdigit()
        for n in todas_notas
    )
    runner.asserir(
        cnpjs_validos,
        "Formatação CNPJ: todos os tomador_cnpj possuem exatamente 14 dígitos numéricos",
    )

    # 6. Valores estritamente positivos (> 0.00)
    valores_positivos = all(n["valor_brl"] > Decimal("0.00") for n in todas_notas)
    runner.asserir(
        valores_positivos,
        "Valores estritos: todas as notas possuem valor_brl > R$ 0.00",
    )

    # 7. Rastreabilidade matemática centavo a centavo
    rastro_bate = True
    detalhe_rastro = ""
    for n in todas_notas:
        total_rastro = tracker_global.total(n["id_saida"])
        if total_rastro != n["valor_brl"]:
            rastro_bate = False
            detalhe_rastro = f"{n['id_saida']}: nota={n['valor_brl']} vs rastro={total_rastro}"
            break

    runner.asserir(
        rastro_bate,
        "Rastreabilidade matemática: soma de cada id_saida no rastro fecha centavo a centavo com valor_brl",
        detalhe_rastro,
    )


# ============================================================================
# 3. BATERIA DE RESILIÊNCIA, COMPETÊNCIA E CASOS DE BORDA
# ============================================================================
def testar_resiliencia_e_casos_borda(runner: TestRunner) -> None:
    """Valida resiliência a entradas vazias, nulas, ausência de tracker e fallbacks."""
    print("\n" + "=" * 70)
    print(" 4. TESTES DE RESILIÊNCIA, COMPETÊNCIA DINÂMICA E HELPERS")
    print("=" * 70)

    # Entrada nula total
    res_nulo = notas.gerar_notas_a_emitir(None, None, None, tracker=None)
    runner.asserir(
        res_nulo == [],
        "Resiliência: gerar_notas_a_emitir(None, None, None) devolve lista vazia sem exceção",
    )

    # Dicionários vazios
    res_vazio = notas.gerar_notas_a_emitir({}, {}, {}, tracker=None)
    runner.asserir(
        res_vazio == [],
        "Resiliência: gerar_notas_a_emitir com dicionários vazios devolve lista vazia",
    )

    # Sem tracker opera com fallback NF-0000 sem quebrar
    mock_sem_tracker = {
        "operacoes_validas": [
            {
                "ref_origem": "PC-TEST",
                "lojista": "Teste",
                "spread_brl": Decimal("100.00"),
                "comissao_tarvo_brl": Decimal("50.00"),
            }
        ]
    }
    res_sem_tracker = notas.gerar_notas_a_emitir(dados_remessas=mock_sem_tracker, tracker=None)
    runner.asserir(
        len(res_sem_tracker) == 1 and res_sem_tracker[0]["id_saida"] == "NF-0000",
        "Resiliência: sem tracker gera id fallback 'NF-0000' sem interromper fluxo",
    )

    # Inferência dinâmica de competência
    comp_outubro = _inferir_competencia(
        dados_checkout={"transacoes": [{"data_movimento": "2026-10-15"}]},
        dados_remessas=None,
    )
    runner.asserir(
        comp_outubro == "10/2026",
        f"Competência Dinâmica: inferiu '10/2026' a partir de transação de outubro ({comp_outubro})",
    )

    comp_fallback = _inferir_competencia(None, None)
    runner.asserir(
        comp_fallback == "09/2026",
        f"Competência Fallback: retornou '09/2026' quando sem datas ({comp_fallback})",
    )

    # Helpers de fallback
    d_fmt = _fallback_para_decimal("R$ 2.450,75")
    runner.asserir(
        d_fmt == Decimal("2450.75"),
        f"Helper _fallback_para_decimal: converteu 'R$ 2.450,75' para Decimal('{d_fmt}')",
    )

    d_round = _fallback_round_half_up("25.005")
    runner.asserir(
        d_round == Decimal("25.01"),
        f"Helper _fallback_round_half_up: arredondou 25.005 para {d_round} (ROUND_HALF_UP)",
    )

    cnpj_limpo = _fallback_clean_cnpj("22.224.579/0001-09")
    runner.asserir(
        cnpj_limpo == "22224579000109",
        f"Helper _fallback_clean_cnpj: limpou pontuação mantendo 14 dígitos ('{cnpj_limpo}')",
    )

    txt_norm = _normalizar_texto("  Átlas Idiômas S.A.  ")
    runner.asserir(
        txt_norm == "atlas idiomas s.a.",
        f"Helper _normalizar_texto: normalizou acentos e caixa alta ('{txt_norm}')",
    )

    # Aliases de compatibilidade
    runner.asserir(
        emitir_notas is gerar_notas_a_emitir
        and calcular_notas is gerar_notas_a_emitir
        and gerar_notas is gerar_notas_a_emitir,
        "Aliases de compatibilidade: emitir_notas, calcular_notas e gerar_notas apontam para gerar_notas_a_emitir",
    )


# ============================================================================
# 4. BATERIA DE INTEGRAÇÃO REAL COM DATASET (DATA_PACK)
# ============================================================================
def testar_integracao_real(runner: TestRunner, data_dir: Path) -> None:
    """Valida o funcionamento integrado com os arquivos reais do data_pack de setembro/2026."""
    print("\n" + "=" * 70)
    print(f" 5. TESTES DE INTEGRAÇÃO REAL COM DATA_PACK: {data_dir}")
    print("=" * 70)

    if not data_dir.is_dir():
        runner.asserir(False, f"Pasta de dados {data_dir} não encontrada", "Ignorando integração real")
        return

    print("  -> Carregando dados de Checkout (parse_orbe)...")
    dados_ck = parse_orbe.parse_orbe_e_taxas(data_dir)
    print("  -> Carregando dados de Remessas (parse_ponte)...")
    dados_rem = parse_ponte.parse_ponte_e_taxas(data_dir)

    tracker = RastroTracker()
    print("  -> Calculando comissões prévias (comissoes.py)...")
    comissoes_linhas = comissoes.calcular_comissoes(dados_ck, dados_rem, tracker)

    print("  -> Gerando notas fiscais reais (notas.py)...")
    lista_notas = notas.gerar_notas_a_emitir(comissoes_linhas, dados_ck, dados_rem, tracker)

    # 1. Total de Notas Fiscais a Emitir (20 de Checkout + 1 de Remessa = 21 notas)
    total_esperado = 21
    runner.asserir(
        len(lista_notas) == total_esperado,
        f"Integração Real: exatamente {total_esperado} notas fiscais geradas (20 Checkout + 1 Remessa)",
        f"Obtido: {len(lista_notas)} notas",
    )

    # 2. Separação por linha de negócio
    notas_checkout = [n for n in lista_notas if n["linha_negocio"] == LINHA_CHECKOUT]
    notas_remessa = [n for n in lista_notas if n["linha_negocio"] == LINHA_REMESSA]

    runner.asserir(
        len(notas_checkout) == 20,
        "Integração Real Checkout: 20 notas individuais emitidas para lojistas de checkout com comissão > R$ 0.00",
        f"Obtido: {len(notas_checkout)} notas",
    )
    runner.asserir(
        len(notas_remessa) == 1,
        "Integração Real Remessas: exatamente 1 nota fiscal única emitida contra a Ponte Câmbio S.A.",
        f"Obtido: {len(notas_remessa)} notas",
    )

    # 3. Exclusão de Casa do Estudante e Atlas Idiomas
    cnpj_casa_do_estudante = "00520815000100"
    cnpj_atlas_idiomas = "10768017000132"
    cnpjs_emitidos = {n["tomador_cnpj"] for n in lista_notas}

    runner.asserir(
        cnpj_casa_do_estudante not in cnpjs_emitidos,
        "Integração Real Casa do Estudante: nenhuma nota fiscal emitida (taxa checkout 0.00%)",
    )
    runner.asserir(
        cnpj_atlas_idiomas not in cnpjs_emitidos,
        "Integração Real Atlas Idiomas: faturamento bloqueado por falta de contrato 2026",
    )

    # 4. Conferência da nota única da Ponte Câmbio S.A.
    nota_ponte = notas_remessa[0]
    valor_esperado_ponte = Decimal("39543.45")
    runner.asserir(
        nota_ponte["tomador_cnpj"] == PONTE_CAMBIO_CNPJ and nota_ponte["tomador"] == PONTE_CAMBIO_NOME,
        f"Integração Real Ponte Câmbio: tomador é {PONTE_CAMBIO_NOME} ({PONTE_CAMBIO_CNPJ})",
    )
    runner.asserir(
        nota_ponte["valor_brl"] == valor_esperado_ponte,
        f"Integração Real Ponte Câmbio: valor consolidado exato de R$ {valor_esperado_ponte}",
        f"Obtido: R$ {nota_ponte['valor_brl']}",
    )
    runner.asserir(
        tracker.total(nota_ponte["id_saida"]) == valor_esperado_ponte,
        f"Integração Real Rastro Ponte: rastro da nota da Ponte totaliza exatamente R$ {valor_esperado_ponte}",
    )

    # 5. Serialização estrita via contrato oficial (src/main.py)
    spec_notas = config.ARQUIVOS_SAIDA[config.ARQ_NOTAS]
    try:
        linhas_serializadas = _serializar(spec_notas, lista_notas)
        runner.asserir(
            len(linhas_serializadas) == total_esperado,
            f"Serialização main.py: todas as {total_esperado} notas passaram na formatação estrita do edital",
        )
    except Exception as exc:
        runner.asserir(
            False,
            f"Serialização main.py falhou: {exc}",
        )

    # 6. Conferência de RastroTracker de notas
    # Cada uma das 21 notas tem seus apontamentos registrados no rastro
    todas_com_rastro = all(
        tracker.possui_rastro(n["id_saida"])
        and tracker.total(n["id_saida"]) == n["valor_brl"]
        for n in lista_notas
    )
    runner.asserir(
        todas_com_rastro,
        "RastroTracker Real: todas as 21 notas fiscais fecham centavo a centavo com o rastro",
    )

    # Contagem de linhas de rastro vinculadas a NF-* (exatamente 2009 linhas)
    linhas_rastro_nf = [row for row in tracker.linhas if row["id_saida"].startswith("NF-")]
    runner.asserir(
        len(linhas_rastro_nf) == 2009,
        f"RastroTracker Real: exatamente 2009 apontamentos de rastro vinculados às notas fiscais (esperado: 2009)",
        f"Obtido: {len(linhas_rastro_nf)}",
    )


# ============================================================================
# 5. CASOS DE TESTE COMPATÍVEIS COM UNITTEST (python -m unittest)
# ============================================================================
class TestNotasUnitario(unittest.TestCase):
    """Bateria de testes unitários executável via runner padrão do unittest."""

    def setUp(self) -> None:
        self.runner = TestRunner(verboso=False)

    def test_regras_unitarias(self) -> None:
        testar_casos_unitarios(self.runner)
        self.assertEqual(self.runner.falhas, 0, f"{self.runner.falhas} teste(s) falharam")

    def test_contrato_e_rastro(self) -> None:
        testar_contrato_e_rastro(self.runner)
        self.assertEqual(self.runner.falhas, 0, f"{self.runner.falhas} teste(s) falharam")

    def test_resiliencia_e_casos_borda(self) -> None:
        testar_resiliencia_e_casos_borda(self.runner)
        self.assertEqual(self.runner.falhas, 0, f"{self.runner.falhas} teste(s) falharam")


class TestNotasIntegrado(unittest.TestCase):
    """Bateria de integração real com data_pack executável via runner padrão do unittest."""

    def test_integracao_real_dataset(self) -> None:
        runner = TestRunner(verboso=False)
        data_dir = _RAIZ / "data_pack"
        if data_dir.is_dir():
            testar_integracao_real(runner, data_dir)
            self.assertEqual(runner.falhas, 0, f"{runner.falhas} teste(s) falharam")


# ============================================================================
# 6. PONTO DE ENTRADA CLI
# ============================================================================
def main() -> int:
    parser = argparse.ArgumentParser(description="Testes de notas.py (Missão 3 · Faturamento Tarvo)")
    parser.add_argument("--unitario", action="store_true", help="Executa apenas a bateria sintética")
    parser.add_argument("--integrado", action="store_true", help="Executa apenas a integração com data_pack")
    parser.add_argument("--data-dir", default=str(_RAIZ / "data_pack"), help="Pasta com dados brutos")
    parser.add_argument("-v", "--verboso", action="store_true", help="Imprime detalhes dos testes")
    args = parser.parse_args()

    runner = TestRunner(verboso=args.verboso)
    data_dir = Path(args.data_dir)

    executar_todos = not args.unitario and not args.integrado

    if executar_todos or args.unitario:
        testar_casos_unitarios(runner)
        testar_contrato_e_rastro(runner)
        testar_resiliencia_e_casos_borda(runner)

    if executar_todos or args.integrado:
        testar_integracao_real(runner, data_dir)

    print("\n" + "=" * 70)
    print(f" RESUMO DOS TESTES: {runner.sucessos} SUCESSOS, {runner.falhas} FALHAS")
    print("=" * 70)

    if runner.falhas == 0:
        print("  >>> TODOS OS TESTES PASSARAM COM SUCESSO! <<<\n")
        return 0
    else:
        print(f"  >>> ATENÇÃO: {runner.falhas} TESTE(S) FALHARAM! <<<\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
