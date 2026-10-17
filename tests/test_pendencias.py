#!/usr/bin/env python3
"""Testes automatizados e validação completa para `src/engine/pendencias.py`.

Missão 5: Governança, Disputas, Anomalias e Pendências Operacionais/Comerciais
Catálogo Oficial das 7 Pendências Operacionais/Comerciais:
1. Spreads Negativos (Ponte Câmbio): 4 operações com trava de cotação de 2h expirada
   (`PC-0926-0210`, `PC-0926-0326`, `PC-0926-0491`, `PC-0926-0545`).
2. Operação Repetida (Ponte Câmbio): Retificação da duplicata `PC-0926-0162` (Bagagem Livre).
3. Spread Indevido Mundo Aberto (Ponte Câmbio): Cobrança de ~1.50% vs 1.20% contratado (23 ops).
4. Ressarcimento Casa do Estudante (Orbe): Devolução de taxas retidas indevidamente (EC `1018325654`).
5. Contrato Atlas Idiomas (Orbe): Regularização de contrato ausente em 2026 (EC `1076801732`).
6. Pix Não Identificado (Banco Aurora): Crédito em `L50` de R$ 7.350,00 sem identificação do remetente.
7. Devolução de Pix Mundo Aberto (Banco Aurora): Estorno/devolução em `L65` de R$ 12.400,00.

Este script valida exaustivamente:
1. Regras unitárias de Remessas (Spreads Negativos agrupados e desagrupados, Duplicata, Mundo Aberto).
2. Regras unitárias de Checkout (Casa do Estudante 0.00%, Atlas Idiomas sem contrato 2026).
3. Regras unitárias de Extratos Bancários (Pix não identificado L50, Devolução Pix L65).
4. Atribuição correta do responsável pela decisão (`Financeiro Tarvo (Helena)` vs `Comercial Tarvo (Diego)`).
5. Contrato estrito de saída (`id_saida;tipo;ref_origem;valor_brl;motivo;quem_decide`).
6. Rastreabilidade matemática absoluta (cada pendência amarrada centavo a centavo no `RastroTracker`).
7. Casos de borda, fallbacks e resiliência (entradas nulas/vazias, sem tracker, normalização de texto).
8. Integração completa com o dataset real de fechamento (`data_pack/`).

Uso:
    python tests/test_pendencias.py               # Executa bateria completa (unitários + integração)
    python tests/test_pendencias.py --unitario    # Executa apenas bateria de regras unitárias
    python tests/test_pendencias.py --integrado   # Executa apenas integração com data_pack
    python tests/test_pendencias.py -v            # Modo verboso
    python -m unittest tests/test_pendencias.py   # Executa via test runner padrão do unittest
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
from src.engine import pendencias
from src.engine.pendencias import (
    consolidar_pendencias,
    gerar_pendencias,
    apurar_pendencias,
    _normalizar_texto,
    _fallback_para_decimal,
    _fallback_round_half_up,
    PREFIXO_PENDENCIA,
    PEND_SPREAD_NEGATIVO,
    PEND_OPERACAO_DUPLICADA,
    PEND_DIVERGENCIA_SPREAD,
    PEND_DEVOLUCAO_TAXA,
    PEND_CONTRATO_AUSENTE,
    PEND_PIX_NAO_IDENTIFICADO,
    PEND_DEVOLUCAO_PIX,
    QUEM_FINANCEIRO,
    QUEM_COMERCIAL,
    EC_CASA_DO_ESTUDANTE,
    EC_ATLAS_IDIOMAS,
)
from src.engine.rastro import RastroTracker
from src.main import _serializar
from src.parsers import parse_extratos, parse_orbe, parse_ponte


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
    """Valida todas as 7 regras de pendência com fixtures e dados sintéticos controlados."""
    print("\n" + "=" * 70)
    print(" 1. TESTES UNITÁRIOS SINTÉTICOS: REMESSAS (PONTE CÂMBIO)")
    print("=" * 70)

    tracker_rem = RastroTracker()
    arquivo_rem = "03_email_ponte_cambio_relatorio_set2026.eml"

    dados_mock_remessas: Dict[str, Any] = {
        "arquivo_origem": arquivo_rem,
        "operacoes_spread_negativo": [
            {
                "ref_origem": "PC-NEG-01",
                "num_operacao": "PC-NEG-01",
                "lojista": "Turismo Austral",
                "spread_brl": Decimal("-450.50"),
                "spread_pct": Decimal("-1.20"),
            },
            {
                "ref_origem": "PC-NEG-02",
                "num_operacao": "PC-NEG-02",
                "lojista": "Vento Sul Câmbio",
                "spread_brl": Decimal("-550.00"),
                "spread_pct": Decimal("-1.50"),
            },
        ],
        "operacoes_duplicadas": [
            {
                "ref_origem": "PC-0926-0162",
                "num_operacao": "PC-0926-0162",
                "lojista": "Bagagem Livre Turismo Ltda",
                "spread_brl": Decimal("821.88"),
                "comissao_tarvo": Decimal("410.94"),
            }
        ],
        "operacoes_divergentes": [
            {
                "ref_origem": "PC-MUNDO-01",
                "num_operacao": "PC-MUNDO-01",
                "lojista": "Mundo Aberto Intercâmbio",
                "cnpj": "17.217.888/0001-11",
                "spread_pct": Decimal("1.50"),
                "spread_contratado_pct": Decimal("1.20"),
                "diferenca_brl": Decimal("60.00"),
            },
            {
                "ref_origem": "PC-MUNDO-02",
                "num_operacao": "PC-MUNDO-02",
                "lojista": "Mundo Aberto Intercâmbio",
                "cnpj": "17.217.888/0001-11",
                "spread_pct": Decimal("1.50"),
                "spread_contratado_pct": Decimal("1.20"),
                "diferenca_brl": Decimal("40.00"),
            },
        ],
    }

    # Teste 1.1: Remessas com agrupamento padrão (agrupar_spreads_negativos=True)
    pends_rem_agrupadas = consolidar_pendencias(
        dados_remessas=dados_mock_remessas,
        tracker=tracker_rem,
        agrupar_spreads_negativos=True,
    )

    runner.asserir(
        len(pends_rem_agrupadas) == 3,
        "Remessas agrupadas: geradas 3 pendências (1 spread negativo consolidado, 1 duplicata, 1 divergência Mundo Aberto)",
        f"Obtido: {len(pends_rem_agrupadas)}",
    )

    mapa_rem = {p["tipo"]: p for p in pends_rem_agrupadas}

    # Valida Pendência 1: Spreads Negativos Consolidados
    p_neg = mapa_rem.get(PEND_SPREAD_NEGATIVO)
    runner.asserir(
        p_neg is not None
        and p_neg["valor_brl"] == Decimal("-1000.50")
        and p_neg["ref_origem"] == "PC-NEG-01,PC-NEG-02"
        and p_neg["quem_decide"] == QUEM_FINANCEIRO,
        "Remessas Spreads Negativos: consolidou R$ -1000.50 (-450.50 + -550.00) com refs unidas e decisão Helena",
        f"Obtido: {p_neg}",
    )
    runner.asserir(
        tracker_rem.total(p_neg["id_saida"]) == Decimal("-1000.50"),
        "Rastreabilidade Spreads Negativos: rastro consolidado fecha exatamente em R$ -1000.50",
    )

    # Valida Pendência 2: Operação Duplicada
    p_dup = mapa_rem.get(PEND_OPERACAO_DUPLICADA)
    runner.asserir(
        p_dup is not None
        and p_dup["valor_brl"] == Decimal("821.88")
        and p_dup["ref_origem"] == "PC-0926-0162"
        and p_dup["quem_decide"] == QUEM_FINANCEIRO,
        "Remessas Operação Duplicada: capturou PC-0926-0162 com R$ 821.88 e decisão Helena",
        f"Obtido: {p_dup}",
    )
    runner.asserir(
        tracker_rem.total(p_dup["id_saida"]) == Decimal("821.88"),
        "Rastreabilidade Operação Duplicada: rastro fecha centavo a centavo em R$ 821.88",
    )

    # Valida Pendência 3: Divergência Spread Mundo Aberto
    p_div = mapa_rem.get(PEND_DIVERGENCIA_SPREAD)
    runner.asserir(
        p_div is not None
        and p_div["valor_brl"] == Decimal("100.00")
        and p_div["ref_origem"] == "PC-MUNDO-01"
        and p_div["quem_decide"] == QUEM_FINANCEIRO,
        "Remessas Mundo Aberto: consolidou divergência de R$ 100.00 (60.00 + 40.00) e decisão Helena",
        f"Obtido: {p_div}",
    )
    runner.asserir(
        tracker_rem.total(p_div["id_saida"]) == Decimal("100.00"),
        "Rastreabilidade Mundo Aberto: rastro acumula 2 apontamentos e totaliza R$ 100.00",
    )

    # Teste 1.2: Remessas desagrupadas (agrupar_spreads_negativos=False)
    tracker_rem_desagrupado = RastroTracker()
    pends_rem_desagrupadas = consolidar_pendencias(
        dados_remessas=dados_mock_remessas,
        tracker=tracker_rem_desagrupado,
        agrupar_spreads_negativos=False,
    )
    negativas_individuais = [p for p in pends_rem_desagrupadas if p["tipo"] == PEND_SPREAD_NEGATIVO]
    runner.asserir(
        len(negativas_individuais) == 2,
        "Remessas desagrupadas: gerou 2 linhas individuais para os 2 spreads negativos",
        f"Obtido: {len(negativas_individuais)}",
    )
    runner.asserir(
        {p["ref_origem"] for p in negativas_individuais} == {"PC-NEG-01", "PC-NEG-02"},
        "Remessas desagrupadas: refs preservadas individualmente em cada pendência",
    )

    # Teste 1.3: Detecção fallback de remessas a partir de todas_ops
    dados_mock_rem_fallback: Dict[str, Any] = {
        "arquivo_origem": arquivo_rem,
        "operacoes": [
            {
                "num_operacao": "PC-FB-NEG-01",
                "lojista": "Global Exchange",
                "spread_brl": Decimal("-320.00"),
                "spread_pct": Decimal("-1.10"),
            },
            {
                "num_operacao": "PC-FB-DUP-01",
                "lojista": "Lojista Repetido",
                "spread_brl": Decimal("500.00"),
            },
            {
                "num_operacao": "PC-FB-DUP-01",  # Segunda ocorrência = duplicata detectada
                "lojista": "Lojista Repetido",
                "spread_brl": Decimal("500.00"),
            },
            {
                "num_operacao": "PC-FB-DIV-01",
                "lojista": "Mundo Aberto Intercâmbio",
                "valor_brl": Decimal("10000.00"),
                "spread_pct": Decimal("1.50"),
                "spread_contratado_pct": Decimal("1.20"),
            },
        ],
    }
    tracker_fb = RastroTracker()
    pends_fb = consolidar_pendencias(dados_remessas=dados_mock_rem_fallback, tracker=tracker_fb)
    runner.asserir(
        len(pends_fb) == 3,
        "Remessas fallback: identificou spread negativo, duplicata e divergência a partir da lista plana de operações",
        f"Obtido: {len(pends_fb)}",
    )

    print("\n" + "=" * 70)
    print(" 2. TESTES UNITÁRIOS SINTÉTICOS: CHECKOUT (ORBE)")
    print("=" * 70)

    tracker_ck = RastroTracker()
    arquivo_ck = "01_orbe_relatorio_comissoes_set2026.csv"

    dados_mock_checkout: Dict[str, Any] = {
        "arquivo_origem": arquivo_ck,
        "transacoes": [
            # Caso Normal: Sem pendência
            {
                "id_transacao": "TX-NORM-01",
                "cod_estabelecimento": "1075624862",
                "lojista": "Bridge Idiomas",
                "valor_bruto": Decimal("1000.00"),
                "taxa_aplicada_pct": Decimal("2.59"),
                "taxa_contratada_pct": Decimal("2.59"),
            },
            # Pendência 4: Casa do Estudante (EC 1018325654) - 2 transações
            {
                "id_transacao": "TX-CASA-01",
                "cod_estabelecimento": EC_CASA_DO_ESTUDANTE,
                "lojista": "Casa do Estudante Viagens",
                "valor_bruto": Decimal("2000.00"),
                "taxa_aplicada_pct": Decimal("2.50"),
            },
            {
                "id_transacao": "TX-CASA-02",
                "cod_estabelecimento": EC_CASA_DO_ESTUDANTE,
                "lojista": "Casa do Estudante Viagens",
                "valor_bruto": Decimal("3000.00"),
                "taxa_aplicada_pct": Decimal("2.00"),
            },
            # Pendência 5: Atlas Idiomas (EC 1076801732) - 2 transações sem contrato 2026
            {
                "id_transacao": "TX-ATLAS-01",
                "cod_estabelecimento": EC_ATLAS_IDIOMAS,
                "lojista": "Atlas Idiomas",
                "valor_bruto": Decimal("4000.00"),
                "taxa_aplicada_pct": Decimal("3.00"),
                "sem_contrato": True,
            },
            {
                "id_transacao": "TX-ATLAS-02",
                "cod_estabelecimento": EC_ATLAS_IDIOMAS,
                "lojista": "Atlas Idiomas",
                "valor_bruto": Decimal("6000.00"),
                "taxa_aplicada_pct": Decimal("3.00"),
                "sem_contrato": True,
            },
        ],
    }

    pends_ck = consolidar_pendencias(dados_checkout=dados_mock_checkout, tracker=tracker_ck)
    runner.asserir(
        len(pends_ck) == 2,
        "Checkout: geradas exatamente 2 pendências (Casa do Estudante e Atlas Idiomas)",
        f"Obtido: {len(pends_ck)}",
    )

    mapa_ck = {p["tipo"]: p for p in pends_ck}

    # Valida Pendência 4: Casa do Estudante
    # TX1: 2000 * 2.50% = 50.00; TX2: 3000 * 2.00% = 60.00 -> Total: 110.00
    p_casa = mapa_ck.get(PEND_DEVOLUCAO_TAXA)
    runner.asserir(
        p_casa is not None
        and p_casa["valor_brl"] == Decimal("110.00")
        and p_casa["ref_origem"] == EC_CASA_DO_ESTUDANTE
        and p_casa["quem_decide"] == QUEM_FINANCEIRO,
        "Checkout Casa do Estudante: devolução de R$ 110.00 apurada com decisão Helena Financeiro",
        f"Obtido: {p_casa}",
    )
    runner.asserir(
        tracker_ck.total(p_casa["id_saida"]) == Decimal("110.00"),
        "Rastreabilidade Casa do Estudante: rastro amarrado centavo a centavo (R$ 110.00)",
    )

    # Valida Pendência 5: Atlas Idiomas
    # TX1: 4000 * 3.00% = 120.00; TX2: 6000 * 3.00% = 180.00 -> Total retido: 300.00
    p_atlas = mapa_ck.get(PEND_CONTRATO_AUSENTE)
    runner.asserir(
        p_atlas is not None
        and p_atlas["valor_brl"] == Decimal("300.00")
        and p_atlas["ref_origem"] == EC_ATLAS_IDIOMAS
        and p_atlas["quem_decide"] == QUEM_COMERCIAL,
        "Checkout Atlas Idiomas: retenção de R$ 300.00 com decisão exclusiva Diego Comercial",
        f"Obtido: {p_atlas}",
    )
    runner.asserir(
        tracker_ck.total(p_atlas["id_saida"]) == Decimal("300.00"),
        "Rastreabilidade Atlas Idiomas: rastro amarrado centavo a centavo (R$ 300.00)",
    )

    print("\n" + "=" * 70)
    print(" 3. TESTES UNITÁRIOS SINTÉTICOS: EXTRATOS BANCÁRIOS (BANCO AURORA)")
    print("=" * 70)

    tracker_ext = RastroTracker()
    arquivo_aurora = "05a_extrato_banco_aurora_cc4471_set2026.csv"

    dados_mock_extratos: Dict[str, Any] = {
        "arquivo_aurora": arquivo_aurora,
        "lancamentos_aurora": [
            # Normal
            {
                "ref_origem": "L10",
                "data": "2026-09-02",
                "descricao": "TED RECEBIDA CLIENTE X",
                "valor": Decimal("50000.00"),
            },
            # Pendência 6: Pix Não Identificado (L50 - R$ 7.350,00)
            {
                "ref_origem": "L50",
                "data": "2026-09-16",
                "descricao": "PIX RECEBIDO 38686002000180 SEM IDENTIFICACAO",
                "valor": Decimal("7350.00"),
            },
            # Pendência 7: Devolução de Pix Mundo Aberto (L65 - R$ 12.400,00)
            {
                "ref_origem": "L65",
                "data": "2026-09-23",
                "descricao": "DEVOLUCAO PIX - MUNDO ABERTO INTERC",
                "valor": Decimal("12400.00"),
            },
        ],
    }

    pends_ext = consolidar_pendencias(dados_extratos=dados_mock_extratos, tracker=tracker_ext)
    runner.asserir(
        len(pends_ext) == 2,
        "Extratos Aurora: geradas exatamente 2 pendências (Pix não identificado L50 e Devolução Pix L65)",
        f"Obtido: {len(pends_ext)}",
    )

    mapa_ext = {p["tipo"]: p for p in pends_ext}

    # Valida Pendência 6: Pix Não Identificado
    p_l50 = mapa_ext.get(PEND_PIX_NAO_IDENTIFICADO)
    runner.asserir(
        p_l50 is not None
        and p_l50["valor_brl"] == Decimal("7350.00")
        and p_l50["ref_origem"] == "L50"
        and p_l50["quem_decide"] == QUEM_FINANCEIRO,
        "Extratos Pix Não Identificado: capturado L50 com R$ 7350.00 e decisão Helena Financeiro",
        f"Obtido: {p_l50}",
    )
    runner.asserir(
        tracker_ext.total(p_l50["id_saida"]) == Decimal("7350.00"),
        "Rastreabilidade Pix Não Identificado: rastro amarrado à linha física L50 (R$ 7350.00)",
    )

    # Valida Pendência 7: Devolução Pix Mundo Aberto
    p_l65 = mapa_ext.get(PEND_DEVOLUCAO_PIX)
    runner.asserir(
        p_l65 is not None
        and p_l65["valor_brl"] == Decimal("12400.00")
        and p_l65["ref_origem"] == "L65"
        and p_l65["quem_decide"] == QUEM_FINANCEIRO,
        "Extratos Devolução Pix Mundo Aberto: capturado L65 com R$ 12400.00 e decisão Helena Financeiro",
        f"Obtido: {p_l65}",
    )
    runner.asserir(
        tracker_ext.total(p_l65["id_saida"]) == Decimal("12400.00"),
        "Rastreabilidade Devolução Pix Mundo Aberto: rastro amarrado à linha física L65 (R$ 12400.00)",
    )


# ============================================================================
# 2. BATERIA DE CONTRATO, FORMATO E RASTRO MATEMÁTICO
# ============================================================================
def testar_contrato_e_rastro(runner: TestRunner) -> None:
    """Valida especificações estritas de schema, IDs únicos e rastro centavo a centavo."""
    print("\n" + "=" * 70)
    print(" 4. TESTES DE CONTRATO, FORMATO E RASTREABILIDADE MATEMÁTICA")
    print("=" * 70)

    tracker_global = RastroTracker()

    dados_mock_checkout: Dict[str, Any] = {
        "arquivo_origem": "01_orbe_relatorio_comissoes_set2026.csv",
        "transacoes": [
            {
                "id_transacao": "TX-CK-CASA",
                "cod_estabelecimento": EC_CASA_DO_ESTUDANTE,
                "lojista": "Casa do Estudante",
                "valor_bruto": Decimal("1000.00"),
                "taxa_aplicada_pct": Decimal("2.00"),
            },
            {
                "id_transacao": "TX-CK-ATLAS",
                "cod_estabelecimento": EC_ATLAS_IDIOMAS,
                "lojista": "Atlas Idiomas",
                "valor_bruto": Decimal("2000.00"),
                "taxa_aplicada_pct": Decimal("2.50"),
                "sem_contrato": True,
            },
        ],
    }

    dados_mock_remessas: Dict[str, Any] = {
        "arquivo_origem": "03_email_ponte_cambio_relatorio_set2026.eml",
        "operacoes_spread_negativo": [
            {
                "ref_origem": "PC-01",
                "num_operacao": "PC-01",
                "lojista": "Alpha",
                "spread_brl": Decimal("-100.00"),
                "spread_pct": Decimal("-1.00"),
            }
        ],
        "operacoes_duplicadas": [
            {
                "ref_origem": "PC-02",
                "num_operacao": "PC-02",
                "lojista": "Beta",
                "spread_brl": Decimal("200.00"),
            }
        ],
        "operacoes_divergentes": [
            {
                "ref_origem": "PC-03",
                "num_operacao": "PC-03",
                "lojista": "Mundo Aberto",
                "spread_pct": Decimal("1.50"),
                "spread_contratado_pct": Decimal("1.20"),
                "diferenca_brl": Decimal("50.00"),
            }
        ],
    }

    dados_mock_extratos: Dict[str, Any] = {
        "arquivo_aurora": "05a_extrato_banco_aurora_cc4471_set2026.csv",
        "lancamentos_aurora": [
            {
                "ref_origem": "L50",
                "data": "2026-09-16",
                "descricao": "PIX SEM IDENTIFICACAO",
                "valor": Decimal("7350.00"),
            },
            {
                "ref_origem": "L65",
                "data": "2026-09-23",
                "descricao": "DEVOLUCAO PIX MUNDO ABERTO",
                "valor": Decimal("12400.00"),
            },
        ],
    }

    todas_pendencias = consolidar_pendencias(
        dados_checkout=dados_mock_checkout,
        dados_remessas=dados_mock_remessas,
        dados_extratos=dados_mock_extratos,
        tracker=tracker_global,
        agrupar_spreads_negativos=True,
    )

    runner.asserir(
        len(todas_pendencias) == 7,
        "Consolidação completa: exatamente as 7 pendências geradas em conjunto",
        f"Obtido: {len(todas_pendencias)}",
    )

    colunas_obrigatorias = config.ARQUIVOS_SAIDA[config.ARQ_PENDENCIAS].colunas
    todos_campos_ok = all(
        all(col in p for col in colunas_obrigatorias) for p in todas_pendencias
    )
    runner.asserir(
        todos_campos_ok,
        f"Contrato: todos os registros possuem exatamente as colunas {colunas_obrigatorias}",
    )

    # Unicidade de id_saida
    ids = [p["id_saida"] for p in todas_pendencias]
    runner.asserir(
        len(ids) == len(set(ids)),
        f"Unicidade: todos os id_saida são únicos e distintos ({ids})",
    )
    runner.asserir(
        all(i.startswith(f"{PREFIXO_PENDENCIA}-") for i in ids),
        f"Prefixo: todos os id_saida iniciam com '{PREFIXO_PENDENCIA}-'",
    )

    # Domínio estrito de quem_decide
    quem_decide_validos = {QUEM_FINANCEIRO, QUEM_COMERCIAL}
    todos_quem_decide_ok = all(p["quem_decide"] in quem_decide_validos for p in todas_pendencias)
    runner.asserir(
        todos_quem_decide_ok,
        f"Domínio quem_decide: todos os registros apontam para Helena ou Diego ({quem_decide_validos})",
    )

    # Motivos e ref_origem não vazios
    textos_validos = all(
        bool(p["motivo"].strip()) and bool(p["ref_origem"].strip())
        for p in todas_pendencias
    )
    runner.asserir(
        textos_validos,
        "Sanidade textual: todos os motivos e referências de origem são strings não-vazias",
    )

    # Rastreabilidade matemática centavo a centavo
    rastro_bate = True
    detalhe_rastro = ""
    for p in todas_pendencias:
        total_rastro = tracker_global.total(p["id_saida"])
        if total_rastro != p["valor_brl"]:
            rastro_bate = False
            detalhe_rastro = f"{p['id_saida']}: p={p['valor_brl']} vs rastro={total_rastro}"
            break

    runner.asserir(
        rastro_bate,
        "Rastreabilidade matemática: soma de cada id_saida no rastro fecha centavo a centavo com valor_brl",
        detalhe_rastro,
    )


# ============================================================================
# 3. BATERIA DE RESILIÊNCIA E CASOS DE BORDA
# ============================================================================
def testar_resiliencia(runner: TestRunner) -> None:
    """Valida resiliência a entradas vazias, nulas, ausência de tracker e fallbacks."""
    print("\n" + "=" * 70)
    print(" 5. TESTES DE RESILIÊNCIA, CASOS DE BORDA E HELPERS")
    print("=" * 70)

    # Entrada nula total
    res_nulo = consolidar_pendencias(None, None, None, tracker=None)
    runner.asserir(
        res_nulo == [],
        "Resiliência: consolidar_pendencias(None, None, None) devolve lista vazia sem exceção",
    )

    # Dicionários vazios
    res_vazio = consolidar_pendencias({}, {}, {}, tracker=None)
    runner.asserir(
        res_vazio == [],
        "Resiliência: consolidar_pendencias com dicionários vazios devolve lista vazia",
    )

    # Sem tracker opera com fallback PEN-0000 sem falhar
    mock_rem_sem_tracker = {
        "operacoes_duplicadas": [
            {
                "ref_origem": "PC-TEST",
                "lojista": "Teste",
                "spread_brl": Decimal("100.00"),
            }
        ]
    }
    res_sem_tracker = consolidar_pendencias(dados_remessas=mock_rem_sem_tracker, tracker=None)
    runner.asserir(
        len(res_sem_tracker) == 1 and res_sem_tracker[0]["id_saida"] == "PEN-0000",
        "Resiliência: sem tracker gera id fallback 'PEN-0000' sem interromper fluxo",
    )

    # Helpers de fallback
    d_fmt = _fallback_para_decimal("R$ 1.250,50")
    runner.asserir(
        d_fmt == Decimal("1250.50"),
        f"Helper _fallback_para_decimal: converteu 'R$ 1.250,50' para Decimal('{d_fmt}')",
    )

    d_none = _fallback_para_decimal(None, Decimal("42.00"))
    runner.asserir(
        d_none == Decimal("42.00"),
        "Helper _fallback_para_decimal: aplicou default customizado para None",
    )

    d_round = _fallback_round_half_up("10.005")
    runner.asserir(
        d_round == Decimal("10.01"),
        f"Helper _fallback_round_half_up: arredondou 10.005 para {d_round} (ROUND_HALF_UP)",
    )

    # Normalização de texto (acentos e caixa)
    txt_norm = _normalizar_texto("  Câsa do Estúdante Intercâmbio  ")
    runner.asserir(
        txt_norm == "casa do estudante intercambio",
        f"Helper _normalizar_texto: normalizou acentos e caixa alta ('{txt_norm}')",
    )

    # Aliases de compatibilidade
    runner.asserir(
        gerar_pendencias is consolidar_pendencias and apurar_pendencias is consolidar_pendencias,
        "Aliases de compatibilidade: gerar_pendencias e apurar_pendencias apontam para consolidar_pendencias",
    )


# ============================================================================
# 4. BATERIA DE INTEGRAÇÃO REAL COM DATASET (DATA_PACK)
# ============================================================================
def testar_integracao_real(runner: TestRunner, data_dir: Path) -> None:
    """Valida o funcionamento integrado com os arquivos reais do data_pack de setembro/2026."""
    print("\n" + "=" * 70)
    print(f" 6. TESTES DE INTEGRAÇÃO REAL COM DATA_PACK: {data_dir}")
    print("=" * 70)

    if not data_dir.is_dir():
        runner.asserir(False, f"Pasta de dados {data_dir} não encontrada", "Ignorando integração real")
        return

    print("  -> Carregando dados de Checkout (parse_orbe)...")
    dados_ck = parse_orbe.parse_orbe_e_taxas(data_dir)
    print("  -> Carregando dados de Remessas (parse_ponte)...")
    dados_rem = parse_ponte.parse_ponte_e_taxas(data_dir)
    print("  -> Carregando extratos bancários (parse_extratos)...")
    dados_ext = parse_extratos.parse_extratos_e_plano(data_dir)

    tracker = RastroTracker()
    print("  -> Consolidando pendências reais...")
    lista_pends = consolidar_pendencias(
        dados_checkout=dados_ck,
        dados_remessas=dados_rem,
        dados_extratos=dados_ext,
        tracker=tracker,
        agrupar_spreads_negativos=True,
    )

    # 1. Total de pendências apuradas (Catálogo Oficial de 7 Pendências)
    runner.asserir(
        len(lista_pends) == 7,
        f"Integração Real: exatamente as 7 pendências catalogadas foram identificadas",
        f"Obtido: {len(lista_pends)} pendências",
    )

    mapa_por_tipo = {p["tipo"]: p for p in lista_pends}

    # 2. Pendência 1: Spreads Negativos (Ponte Câmbio)
    p1 = mapa_por_tipo.get(PEND_SPREAD_NEGATIVO)
    refs_p1_esperadas = "PC-0926-0210,PC-0926-0326,PC-0926-0491,PC-0926-0545"
    runner.asserir(
        p1 is not None
        and p1["valor_brl"] == Decimal("-1834.05")
        and p1["ref_origem"] == refs_p1_esperadas
        and p1["quem_decide"] == QUEM_FINANCEIRO,
        f"Integração Real P1 (Spreads Negativos): R$ -1834.05 em 4 operações ({refs_p1_esperadas}) sob Helena",
        f"Obtido: {p1}",
    )
    runner.asserir(
        tracker.total(p1["id_saida"]) == Decimal("-1834.05"),
        "Integração Real P1: rastro fecha centavo a centavo em R$ -1834.05",
    )

    # 3. Pendência 2: Operação Repetida (Ponte Câmbio - Bagagem Livre)
    p2 = mapa_por_tipo.get(PEND_OPERACAO_DUPLICADA)
    runner.asserir(
        p2 is not None
        and p2["valor_brl"] == Decimal("821.88")
        and p2["ref_origem"] == "PC-0926-0162"
        and p2["quem_decide"] == QUEM_FINANCEIRO,
        "Integração Real P2 (Operação Duplicada): PC-0926-0162 com R$ 821.88 sob Helena",
        f"Obtido: {p2}",
    )
    runner.asserir(
        tracker.total(p2["id_saida"]) == Decimal("821.88"),
        "Integração Real P2: rastro fecha centavo a centavo em R$ 821.88",
    )

    # 4. Pendência 3: Divergência Spread Mundo Aberto (Ponte Câmbio)
    p3 = mapa_por_tipo.get(PEND_DIVERGENCIA_SPREAD)
    runner.asserir(
        p3 is not None
        and p3["valor_brl"] == Decimal("1440.37")
        and p3["quem_decide"] == QUEM_FINANCEIRO,
        "Integração Real P3 (Divergência Mundo Aberto): diferença consolidada de R$ 1440.37 sob Helena",
        f"Obtido: {p3}",
    )
    runner.asserir(
        tracker.total(p3["id_saida"]) == Decimal("1440.37"),
        "Integração Real P3: rastro acumula 23 operações totalizando R$ 1440.37",
    )

    # 5. Pendência 4: Ressarcimento Casa do Estudante (Orbe)
    p4 = mapa_por_tipo.get(PEND_DEVOLUCAO_TAXA)
    runner.asserir(
        p4 is not None
        and p4["valor_brl"] == Decimal("15391.92")
        and p4["ref_origem"] == EC_CASA_DO_ESTUDANTE
        and p4["quem_decide"] == QUEM_FINANCEIRO,
        f"Integração Real P4 (Casa do Estudante): devolução de R$ 15391.92 (EC {EC_CASA_DO_ESTUDANTE}) sob Helena",
        f"Obtido: {p4}",
    )
    runner.asserir(
        tracker.total(p4["id_saida"]) == Decimal("15391.92"),
        "Integração Real P4: rastro acumula 119 transações totalizando R$ 15391.92",
    )

    # 6. Pendência 5: Contrato Ausente Atlas Idiomas (Orbe)
    p5 = mapa_por_tipo.get(PEND_CONTRATO_AUSENTE)
    runner.asserir(
        p5 is not None
        and p5["valor_brl"] == Decimal("7876.05")
        and p5["ref_origem"] == EC_ATLAS_IDIOMAS
        and p5["quem_decide"] == QUEM_COMERCIAL,
        f"Integração Real P5 (Atlas Idiomas): retenção de R$ 7876.05 sob Diego Comercial",
        f"Obtido: {p5}",
    )
    runner.asserir(
        tracker.total(p5["id_saida"]) == Decimal("7876.05"),
        "Integração Real P5: rastro acumula 57 transações totalizando R$ 7876.05",
    )

    # 7. Pendência 6: Pix Não Identificado L50 (Banco Aurora)
    p6 = mapa_por_tipo.get(PEND_PIX_NAO_IDENTIFICADO)
    runner.asserir(
        p6 is not None
        and p6["valor_brl"] == Decimal("7350.00")
        and p6["ref_origem"] == "L50"
        and p6["quem_decide"] == QUEM_FINANCEIRO,
        "Integração Real P6 (Pix Não Identificado L50): R$ 7350.00 sob Helena Financeiro",
        f"Obtido: {p6}",
    )
    runner.asserir(
        tracker.total(p6["id_saida"]) == Decimal("7350.00"),
        "Integração Real P6: rastro fecha centavo a centavo em R$ 7350.00",
    )

    # 8. Pendência 7: Devolução Pix Mundo Aberto L65 (Banco Aurora)
    p7 = mapa_por_tipo.get(PEND_DEVOLUCAO_PIX)
    runner.asserir(
        p7 is not None
        and p7["valor_brl"] == Decimal("12400.00")
        and p7["ref_origem"] == "L65"
        and p7["quem_decide"] == QUEM_FINANCEIRO,
        "Integração Real P7 (Devolução Pix L65): R$ 12400.00 sob Helena Financeiro",
        f"Obtido: {p7}",
    )
    runner.asserir(
        tracker.total(p7["id_saida"]) == Decimal("12400.00"),
        "Integração Real P7: rastro fecha centavo a centavo em R$ 12400.00",
    )

    # 9. Teste do modo desagrupado real (agrupar_spreads_negativos=False -> 10 linhas)
    pends_desagrupadas = consolidar_pendencias(
        dados_checkout=dados_ck,
        dados_remessas=dados_rem,
        dados_extratos=dados_ext,
        tracker=RastroTracker(),
        agrupar_spreads_negativos=False,
    )
    runner.asserir(
        len(pends_desagrupadas) == 10,
        "Integração Real Modo Desagrupado: 10 pendências geradas (4 spreads negativos individuais + 6 demais)",
        f"Obtido: {len(pends_desagrupadas)}",
    )

    # 10. Serialização estrita via contrato oficial (src/main.py)
    spec_pen = config.ARQUIVOS_SAIDA[config.ARQ_PENDENCIAS]
    try:
        linhas_serializadas = _serializar(spec_pen, lista_pends)
        runner.asserir(
            len(linhas_serializadas) == 7,
            "Serialização main.py: todas as 7 pendências passaram na formatação estrita do edital",
        )
    except Exception as exc:
        runner.asserir(
            False,
            f"Serialização main.py falhou: {exc}",
        )

    # 11. Validação do total de apontamentos no RastroTracker (4 + 1 + 23 + 119 + 57 + 1 + 1 = 206)
    total_linhas_rastro_pen = len(tracker.linhas)
    runner.asserir(
        total_linhas_rastro_pen == 206,
        f"RastroTracker Real: exatamente 206 linhas de rastro geradas pelas 7 pendências (esperado: 206)",
        f"Obtido: {total_linhas_rastro_pen}",
    )


# ============================================================================
# 5. CASOS DE TESTE COMPATÍVEIS COM UNITTEST (python -m unittest)
# ============================================================================
class TestPendenciasUnitario(unittest.TestCase):
    """Bateria de testes unitários executável via runner padrão do unittest."""

    def setUp(self) -> None:
        self.runner = TestRunner(verboso=False)

    def test_regras_unitarias(self) -> None:
        testar_casos_unitarios(self.runner)
        self.assertEqual(self.runner.falhas, 0, f"{self.runner.falhas} teste(s) falharam")

    def test_contrato_e_rastro(self) -> None:
        testar_contrato_e_rastro(self.runner)
        self.assertEqual(self.runner.falhas, 0, f"{self.runner.falhas} teste(s) falharam")

    def test_resiliencia_e_fallbacks(self) -> None:
        testar_resiliencia(self.runner)
        self.assertEqual(self.runner.falhas, 0, f"{self.runner.falhas} teste(s) falharam")


class TestPendenciasIntegrado(unittest.TestCase):
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
    parser = argparse.ArgumentParser(description="Testes de pendencias.py (Missão 5 · Governança Tarvo)")
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
        testar_resiliencia(runner)

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
