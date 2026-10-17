#!/usr/bin/env python3
"""Testes automatizados e validação completa para `src/ai/classifier.py`.

Missão 4: Classificação Contábil Inteligente dos Extratos Bancários (ERP Fênix)
Regras de Classificação Contábil:
1. Contrapartida Bancária (RC-17): Cada lançamento mapeia para a contrapartida contábil
   adequada no plano de contas do ERP Fênix (Aurora CC 4471 e Meridiano CC 90233).
2. Passivos Provisionados (RC-18): Salários e tributos de agosto pagos em setembro
   BAIXAM passivos já provisionados (2.1.04.xxx e 2.1.03.xxx), não gerando despesa nova do mês.
3. Comissão de Câmbio de Agosto (RC-19): O crédito recebido em 04/09 (MRD2026090132) baixa
   a conta de ativo circulante `1.1.03.002` (Comissões de Câmbio a Receber).
4. Despesas Correntes (RC-20): Despesas operacionais do mês são alocadas no grupo 4.2.xxx
   (aluguel, condomínio, telecom, utilidades, tarifas bancárias, IOF, juros, fornecedores).
5. Transferências Próprias (RC-21): Movimentações internas entre Aurora e Meridiano
   alocam na conta transitória de mútuo `1.1.09.001`.
6. Motor Híbrido:
   - `REGRA` (confiança 1.0): lançamentos determinísticos por ref_origem ou padrões contratuais estritos.
   - `IA` (confiança < 1.0): classificação heurística por regex / padrões de mercado.
   - `HUMANO` (confiança 0.50): fallback para conta transitória `1.1.09.002`.
7. Rastreabilidade (`rastro.csv`): Amarrar cada `id_saida` (`LAN-xxxx`) ao lançamento
   físico de origem, garantindo que a soma feche centavo a centavo com o valor reportado.

Este script valida exaustivamente:
1. Regras determinísticas por ref_origem (baixa de comissão agosto MRD2026090132).
2. Regras determinísticas por descrição (baixa de folha, FGTS, GPS/INSS, IRRF, ISS, mútuo, aluguel, telecom, tarifas).
3. Classificação heurística IA (fornecedores com NF, recebimentos de câmbio, Pix enviados/recebidos).
4. Fallback humano para conta transitória (1.1.09.002 com confiança 0.50).
5. Contrato estrito de saída (`id_saida;banco;ref_origem;data;descricao;valor;conta_codigo;metodo;confianca`).
6. Rastreabilidade matemática absoluta (cada lançamento amarrado centavo a centavo no `RastroTracker`).
7. Casos de borda e resiliência (entradas vazias/nulas, descrições ausentes, valores com diferentes tipos numéricos).
8. Integração completa com os dados reais de setembro/2026 (`data_pack/`).

Uso:
    python tests/test_classifier.py               # Executa bateria completa (unitários + integração)
    python tests/test_classifier.py --unitario    # Executa apenas bateria de regras unitárias
    python tests/test_classifier.py --integrado   # Executa apenas integração com data_pack
    python tests/test_classifier.py -v            # Modo verboso
    python -m unittest tests/test_classifier.py   # Executa via runner padrão do unittest
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
from src.ai import classifier
from src.ai.classifier import (
    classificar_lancamentos,
    _classificar_lancamento,
    _aplicar_regra_ref_origem,
    _aplicar_regras_descricao,
    CONTA_BANCO,
    REGRAS_REF_ORIGEM,
    PENDENCIAS_CONHECIDAS,
)
from src.config import (
    BANCO_AURORA,
    BANCO_MERIDIANO,
    CONTA_COMISSOES_A_RECEBER,
    CONTA_TRANSITORIA_MUTUO,
    CONTA_TRANSITORIA_NAO_IDENTIFICADO,
    METODO_REGRA,
    METODO_IA,
    METODO_HUMANO,
    PREFIXO_LANCAMENTO,
    PEND_PIX_NAO_IDENTIFICADO,
    PEND_DEVOLUCAO_PIX,
)
from src.engine.rastro import RastroTracker
from src.main import _serializar
from src.parsers import parse_extratos


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
# 1. BATERIA DE TESTES UNITÁRIOS SINTÉTICOS: REGRAS DETERMINÍSTICAS (REGRA)
# ============================================================================
def testar_regras_deterministicas(runner: TestRunner) -> None:
    """Valida as regras fixas de negócio (RC-17, RC-18, RC-19, RC-21) com confiança 1.0 e método REGRA."""
    print("\n" + "=" * 70)
    print(" 1. TESTES UNITÁRIOS: REGRAS DETERMINÍSTICAS (MÉTODO REGRA / CONFIANÇA 1.0)")
    print("=" * 70)

    # 1. Regra RC-19 por ref_origem: Baixa de comissão de câmbio de agosto em 04/09
    lanc_comissao_agosto = {
        "banco": BANCO_MERIDIANO,
        "ref_origem": "MRD2026090132",
        "data": "2026-09-04",
        "descricao": "CREDITO COMISSAO CAMBIO 08/2026",
        "valor": Decimal("38200.00"),
    }
    conta, confianca, metodo = _classificar_lancamento(lanc_comissao_agosto, plano_contas={})
    runner.asserir(
        conta == CONTA_COMISSOES_A_RECEBER and confianca == Decimal("1.0") and metodo == METODO_REGRA,
        f"RC-19 (ref_origem): MRD2026090132 classificado em {CONTA_COMISSOES_A_RECEBER} (baixa comissões a receber) com REGRA e 1.0",
        f"Obtido: conta={conta}, confianca={confianca}, metodo={metodo}",
    )

    # 2. Regra RC-18 por descrição: Baixa de passivos de folha de pagamento (agosto pago em setembro)
    casos_passivos_folha = [
        # (descricao_teste, conta_esperada, label)
        ("PAGTO SALARIOS - FOLHA 08/2026", "2.1.04.001", "Folha de Pagamento / Salários"),
        ("DEBITO GRF FGTS 08/2026", "2.1.04.002", "FGTS"),
        ("GPS INSS COMPETENCIA 08/2026", "2.1.03.001", "INSS / GPS"),
        ("PAGAMENTO DARF IRRF FOLHA 08/2026", "2.1.03.002", "IRRF sobre Folha"),
        ("GUIA ISS SERVICOS TOMADOS", "2.1.03.003", "ISS"),
        ("DARF PIS E COFINS COMPETENCIA AGOSTO", "2.1.03.004", "PIS/COFINS"),
        ("DARF IRPJ E CSLL 08/2026", "2.1.03.005", "CSLL/IRPJ"),
        ("DARF CODIGO 0561 RETENCOES", "2.1.03.009", "DARF Genérico"),
    ]

    for desc, conta_esperada, label in casos_passivos_folha:
        lanc = {"banco": BANCO_AURORA, "ref_origem": "LX", "data": "2026-09-05", "descricao": desc, "valor": Decimal("-5000.00")}
        c, conf, m = _classificar_lancamento(lanc, plano_contas={})
        runner.asserir(
            c == conta_esperada and conf == Decimal("1.0") and m == METODO_REGRA,
            f"RC-18 (Passivo Provisionado): {label} -> {conta_esperada} (REGRA, 1.0)",
            f"Descrição: '{desc}' -> conta={c}, confianca={conf}, metodo={m}",
        )

    # 3. Regra RC-21 por descrição: Transferências entre contas próprias (Mútuo Aurora <-> Meridiano)
    casos_mutuo = [
        "TRANSFERENCIA INTERNA AURORA",
        "TRANSFERENCIA ENTRE CONTAS",
        "TED PROPRIA ENTRE BANCOS",
        "TED MERIDIANO CC 90233",
    ]
    for desc in casos_mutuo:
        lanc = {"banco": BANCO_AURORA, "ref_origem": "LM", "data": "2026-09-02", "descricao": desc, "valor": Decimal("-350000.00")}
        c, conf, m = _classificar_lancamento(lanc, plano_contas={})
        runner.asserir(
            c == CONTA_TRANSITORIA_MUTUO and conf == Decimal("1.0") and m == METODO_REGRA,
            f"RC-21 (Mútuo Próprio): '{desc}' -> {CONTA_TRANSITORIA_MUTUO} (REGRA, 1.0)",
            f"Obtido: conta={c}, metodo={m}",
        )

    # 4. Regra RC-20 por descrição: Despesas correntes administrativas e financeiras
    casos_despesas_correntes = [
        ("BOLETO ALUGUEL SEDE FARIA LIMA", "4.2.01.001", "Aluguel / Locação"),
        ("CONDOMINIO EDIFICIO FARIA LIMA 3311", "4.2.01.001", "Condomínio"),
        ("PAGTO VIVO TELECOM INTERNET FIBRA", "4.2.02.001", "Telecom / Internet"),
        ("ENEL DISTRIBUICAO ENERGIA ELETRICA", "4.2.02.002", "Utilidades (Energia/Água)"),
        ("TARIFA BANCARIA PACOTE SERVICOS PJ", "4.2.03.001", "Tarifas Bancárias"),
        ("DEBITO IOF CONTRATO CAMBIO", "4.2.03.002", "IOF"),
        ("DEBITO JUROS DEVEDORES CONTA", "4.2.03.003", "Juros e Encargos"),
    ]

    for desc, conta_esperada, label in casos_despesas_correntes:
        lanc = {"banco": BANCO_AURORA, "ref_origem": "LD", "data": "2026-09-05", "descricao": desc, "valor": Decimal("-1200.00")}
        c, conf, m = _classificar_lancamento(lanc, plano_contas={})
        runner.asserir(
            c == conta_esperada and conf == Decimal("1.0") and m == METODO_REGRA,
            f"RC-20 (Despesa Corrente): {label} -> {conta_esperada} (REGRA, 1.0)",
            f"Descrição: '{desc}' -> conta={c}, metodo={m}",
        )


# ============================================================================
# 2. BATERIA DE TESTES UNITÁRIOS SINTÉTICOS: HEURÍSTICA IA E FALLBACK HUMANO
# ============================================================================
def testar_heuristicas_ia_e_humano(runner: TestRunner) -> None:
    """Valida classificações heurísticas de mercado (IA) e o fallback humano de auditoria."""
    print("\n" + "=" * 70)
    print(" 2. TESTES UNITÁRIOS: HEURÍSTICAS DE IA E FALLBACK HUMANO")
    print("=" * 70)

    # 1. Pagamento de Fornecedor com NF expressa -> 4.2.04.001, IA, 0.90
    lanc_fornecedor = {
        "banco": BANCO_AURORA,
        "ref_origem": "LNF",
        "data": "2026-09-11",
        "descricao": "PAGAMENTO NF 8842 CONSULTORIA DE TI",
        "valor": Decimal("-8500.00"),
    }
    c_fn, conf_fn, m_fn = _classificar_lancamento(lanc_fornecedor, plano_contas={})
    runner.asserir(
        c_fn == "4.2.04.001" and conf_fn == Decimal("0.90") and m_fn == METODO_IA,
        "Heurística IA (Fornecedores NF): 'NF 8842' classificado em 4.2.04.001 com IA e 0.90",
        f"Obtido: conta={c_fn}, confianca={conf_fn}, metodo={m_fn}",
    )

    # 2. Liquidação de Checkout da Orbe -> 1.1.02.001, IA, 0.95
    lanc_checkout = {
        "banco": BANCO_AURORA,
        "ref_origem": "LORBE",
        "data": "2026-09-01",
        "descricao": "LIQUIDACAO CHECKOUT ORBE SETEMBRO",
        "valor": Decimal("66026.00"),
    }
    c_ck, conf_ck, m_ck = _classificar_lancamento(lanc_checkout, plano_contas={})
    runner.asserir(
        c_ck == "1.1.02.001" and conf_ck == Decimal("0.95") and m_ck == METODO_IA,
        "Heurística IA (Checkout Orbe): 'LIQUIDACAO CHECKOUT' classificado em 1.1.02.001 com IA e 0.95",
        f"Obtido: conta={c_ck}, confianca={conf_ck}, metodo={m_ck}",
    )

    # 3. Pix Recebido Genérico -> 1.1.09.002, IA, 0.70
    lanc_pix_rec = {
        "banco": BANCO_AURORA,
        "ref_origem": "LPIXR",
        "data": "2026-09-16",
        "descricao": "PIX RECEBIDO CLIENTE INDEFINIDO",
        "valor": Decimal("7350.00"),
    }
    c_pr, conf_pr, m_pr = _classificar_lancamento(lanc_pix_rec, plano_contas={})
    runner.asserir(
        c_pr == CONTA_TRANSITORIA_NAO_IDENTIFICADO and conf_pr == Decimal("0.70") and m_pr == METODO_IA,
        f"Heurística IA (Pix Recebido): 'PIX RECEBIDO' direcionado para {CONTA_TRANSITORIA_NAO_IDENTIFICADO} com IA e 0.70",
        f"Obtido: conta={c_pr}, confianca={conf_pr}, metodo={m_pr}",
    )

    # 4. Pix Enviado / Pagamento Lojistas -> 4.2.05.001, IA, 0.70
    lanc_pix_env = {
        "banco": BANCO_AURORA,
        "ref_origem": "LPIXE",
        "data": "2026-09-08",
        "descricao": "PIX ENVIADO ROTA GLOBAL INTERCAMBIO LT",
        "valor": Decimal("-77106.46"),
    }
    c_pe, conf_pe, m_pe = _classificar_lancamento(lanc_pix_env, plano_contas={})
    runner.asserir(
        c_pe == "4.2.05.001" and conf_pe == Decimal("0.70") and m_pe == METODO_IA,
        "Heurística IA (Pix Enviado): repasses e pagamentos via Pix classificados em 4.2.05.001 com IA e 0.70",
        f"Obtido: conta={c_pe}, confianca={conf_pe}, metodo={m_pe}",
    )

    # 5. Fallback Humano: Descrição ininteligível / sem regra correspondente
    lanc_desconhecido = {
        "banco": BANCO_AURORA,
        "ref_origem": "LUNK",
        "data": "2026-09-29",
        "descricao": "XYZ RANDOM UNRECOGNIZED MOVIMENTO 9999",
        "valor": Decimal("-150.00"),
    }
    c_un, conf_un, m_un = _classificar_lancamento(lanc_desconhecido, plano_contas={})
    runner.asserir(
        c_un == CONTA_TRANSITORIA_NAO_IDENTIFICADO and conf_un == Decimal("0.50") and m_un == METODO_HUMANO,
        f"Fallback Humano: lançamento sem padrão vai para {CONTA_TRANSITORIA_NAO_IDENTIFICADO} com HUMANO e 0.50",
        f"Obtido: conta={c_un}, confianca={conf_un}, metodo={m_un}",
    )

    # 6. Dicionários de configuração constantes
    runner.asserir(
        CONTA_BANCO[BANCO_AURORA] == "1.1.01.001" and CONTA_BANCO[BANCO_MERIDIANO] == "1.1.01.002",
        "Configuração Bancária: contas-correntes analíticas mapeadas corretamente no plano Fênix",
    )
    runner.asserir(
        (BANCO_AURORA, "L50") in PENDENCIAS_CONHECIDAS and (BANCO_AURORA, "L65") in PENDENCIAS_CONHECIDAS,
        "Pendências Bancárias Conhecidas: L50 (Pix não identificado) e L65 (Devolução Mundo Aberto) mapeados",
    )


# ============================================================================
# 3. BATERIA DE TESTES DE CONTRATO, FORMATO E RASTRO MATEMÁTICO
# ============================================================================
def testar_contrato_e_rastro(runner: TestRunner) -> None:
    """Valida conformidade com o edital (9 colunas, tipos, unicidade e rastro centavo a centavo)."""
    print("\n" + "=" * 70)
    print(" 3. TESTES DE CONTRATO, FORMATO E RASTREABILIDADE MATEMÁTICA")
    print("=" * 70)

    tracker = RastroTracker()

    dados_mock: Dict[str, Any] = {
        "lancamentos_aurora": [
            {
                "banco": BANCO_AURORA,
                "ref_origem": "L9",
                "data": "2026-09-01",
                "descricao": "TED RECEBIDA ORBE",
                "valor": Decimal("66026.00"),
                "arquivo_origem": "05a_extrato_banco_aurora_cc4471_set2026.csv",
            },
            {
                "banco": BANCO_AURORA,
                "ref_origem": "L15",
                "data": "2026-09-04",
                "descricao": "PAGTO SALARIOS - FOLHA 08/2026",
                "valor": Decimal("-184732.18"),
                "arquivo_origem": "05a_extrato_banco_aurora_cc4471_set2026.csv",
            },
        ],
        "lancamentos_meridiano": [
            {
                "banco": BANCO_MERIDIANO,
                "ref_origem": "MRD2026090132",
                "data": "2026-09-04",
                "descricao": "CREDITO COMISSAO CAMBIO 08/2026",
                "valor": Decimal("38200.00"),
                "arquivo_origem": "05b_extrato_banco_meridiano_cc90233_set2026.ofx",
            }
        ],
        "plano_contas": {},
    }

    linhas_saida = classificar_lancamentos(dados_mock, tracker)

    # 1. Total de saídas: 3 lançamentos
    runner.asserir(
        len(linhas_saida) == 3,
        "Consolidação Sintética: exatamente 3 lançamentos processados",
        f"Obtido: {len(linhas_saida)}",
    )

    # 2. Contrato de colunas
    colunas_obrigatorias = config.ARQUIVOS_SAIDA[config.ARQ_LANCAMENTOS].colunas
    todos_campos_ok = all(
        all(col in linha for col in colunas_obrigatorias) for linha in linhas_saida
    )
    runner.asserir(
        todos_campos_ok,
        f"Contrato: todos os registros possuem exatamente as colunas {colunas_obrigatorias}",
    )

    # 3. Unicidade de id_saida e prefixo LAN-
    ids = [linha["id_saida"] for linha in linhas_saida]
    runner.asserir(
        len(ids) == len(set(ids)),
        f"Unicidade: todos os id_saida são únicos ({ids})",
    )
    runner.asserir(
        all(i.startswith(f"{PREFIXO_LANCAMENTO}-") for i in ids),
        f"Prefixo: todos os id_saida iniciam com '{PREFIXO_LANCAMENTO}-'",
    )

    # 4. Domínios estritos
    bancos_validos = {BANCO_AURORA, BANCO_MERIDIANO}
    metodos_validos = {METODO_REGRA, METODO_IA, METODO_HUMANO}

    runner.asserir(
        all(l["banco"] in bancos_validos for l in linhas_saida),
        f"Domínio banco: todos os registros são {bancos_validos}",
    )
    runner.asserir(
        all(l["metodo"] in metodos_validos for l in linhas_saida),
        f"Domínio método: todos os registros são {metodos_validos}",
    )
    runner.asserir(
        all(Decimal("0.0") <= l["confianca"] <= Decimal("1.0") for l in linhas_saida),
        "Domínio confiança: todas as razões de confiança estão no intervalo [0.0, 1.0]",
    )

    # 5. Formato de datas (AAAA-MM-DD)
    runner.asserir(
        all(len(l["data"]) == 10 and l["data"][4] == "-" and l["data"][7] == "-" for l in linhas_saida),
        "Formato data: todas as datas estão no padrão ISO AAAA-MM-DD",
    )

    # 6. Rastreabilidade matemática centavo a centavo
    rastro_bate = True
    detalhe_rastro = ""
    for linha in linhas_saida:
        total_rastro = tracker.total(linha["id_saida"])
        if total_rastro != linha["valor"]:
            rastro_bate = False
            detalhe_rastro = f"{linha['id_saida']}: valor={linha['valor']} vs rastro={total_rastro}"
            break

    runner.asserir(
        rastro_bate,
        "Rastreabilidade matemática: soma de cada id_saida no rastro fecha centavo a centavo com valor",
        detalhe_rastro,
    )


# ============================================================================
# 4. BATERIA DE TESTES DE RESILIÊNCIA E CASOS DE BORDA
# ============================================================================
def testar_resiliencia_e_casos_borda(runner: TestRunner) -> None:
    """Valida resiliência a entradas vazias, nulas, campos faltantes e formatos numéricos."""
    print("\n" + "=" * 70)
    print(" 4. TESTES DE RESILIÊNCIA E CASOS DE BORDA")
    print("=" * 70)

    tracker = RastroTracker()

    # 1. Entrada nula total
    res_nulo = classificar_lancamentos({}, tracker)
    runner.asserir(
        res_nulo == [],
        "Resiliência: classificar_lancamentos com dicionário vazio devolve lista vazia sem erro",
    )

    # 2. Dicionário sem chaves
    res_sem_chaves = classificar_lancamentos({"outra_chave": 123}, tracker)
    runner.asserir(
        res_sem_chaves == [],
        "Resiliência: dicionário sem listas bancárias devolve lista vazia",
    )

    # 3. Lançamento com descrição None ou vazia
    lanc_sem_desc = {
        "lancamentos_aurora": [
            {
                "banco": BANCO_AURORA,
                "ref_origem": "L999",
                "data": "2026-09-30",
                "descricao": None,
                "valor": Decimal("100.00"),
            }
        ]
    }
    saida_sem_desc = classificar_lancamentos(lanc_sem_desc, tracker)
    runner.asserir(
        len(saida_sem_desc) == 1 and saida_sem_desc[0]["metodo"] == METODO_HUMANO,
        "Resiliência: lançamento com descrição None é tratado suavemente e cai no fallback HUMANO",
    )

    # 4. Lançamento com valor float ou int (garante quantização Decimal)
    lanc_tipos_num = {
        "lancamentos_aurora": [
            {
                "banco": BANCO_AURORA,
                "ref_origem": "L_FLOAT",
                "data": "2026-09-01",
                "descricao": "TARIFA TED",
                "valor": -15.5,
            }
        ]
    }
    saida_num = classificar_lancamentos(lanc_tipos_num, tracker)
    runner.asserir(
        len(saida_num) == 1 and saida_num[0]["valor"] == Decimal("-15.50"),
        f"Resiliência: valor float -15.5 quantizado corretamente para Decimal('-15.50')",
        f"Obtido: {saida_num[0]['valor'] if saida_num else 'None'}",
    )


# ============================================================================
# 5. BATERIA DE INTEGRAÇÃO REAL COM DATASET (DATA_PACK)
# ============================================================================
def testar_integracao_real(runner: TestRunner, data_dir: Path) -> None:
    """Valida o funcionamento integrado com os arquivos reais do data_pack de setembro/2026."""
    print("\n" + "=" * 70)
    print(f" 5. TESTES DE INTEGRAÇÃO REAL COM DATA_PACK: {data_dir}")
    print("=" * 70)

    if not data_dir.is_dir():
        runner.asserir(False, f"Pasta de dados {data_dir} não encontrada", "Ignorando integração real")
        return

    print("  -> Carregando extratos bancários e plano Fênix ERP (parse_extratos)...")
    dados_extratos = parse_extratos.parse_extratos_e_plano(data_dir)

    tracker = RastroTracker()
    print("  -> Executando classificação contábil inteligente (classifier.py)...")
    lista_classificados = classificar_lancamentos(dados_extratos, tracker)

    # 1. Total de lançamentos classificados (esperado: 184 linhas de dados)
    total_esperado = 184
    runner.asserir(
        len(lista_classificados) == total_esperado,
        f"Integração Real: exatamente {total_esperado} lançamentos bancários classificados no ERP",
        f"Obtido: {len(lista_classificados)} lançamentos",
    )

    # 2. Distribuição por banco (Aurora vs Meridiano)
    aurora_linhas = [l for l in lista_classificados if l["banco"] == BANCO_AURORA]
    meridiano_linhas = [l for l in lista_classificados if l["banco"] == BANCO_MERIDIANO]

    total_aurora_esperado = len(dados_extratos["lancamentos_aurora"])
    total_meridiano_esperado = len(dados_extratos["lancamentos_meridiano"])

    runner.asserir(
        len(aurora_linhas) == total_aurora_esperado,
        f"Integração Real Banco Aurora: todos os {total_aurora_esperado} lançamentos foram processados",
        f"Obtido: {len(aurora_linhas)}",
    )
    runner.asserir(
        len(meridiano_linhas) == total_meridiano_esperado,
        f"Integração Real Banco Meridiano: todos os {total_meridiano_esperado} lançamentos foram processados",
        f"Obtido: {len(meridiano_linhas)}",
    )

    # 3. Conferência da regra determinística RC-19 no dataset real (MRD2026090132)
    lanc_mrd = next((l for l in meridiano_linhas if l["ref_origem"] == "MRD2026090132"), None)
    runner.asserir(
        lanc_mrd is not None
        and lanc_mrd["conta_codigo"] == CONTA_COMISSOES_A_RECEBER
        and lanc_mrd["metodo"] == METODO_REGRA
        and lanc_mrd["confianca"] == Decimal("1.0"),
        f"Integração Real RC-19: MRD2026090132 classificado com sucesso em {CONTA_COMISSOES_A_RECEBER} (REGRA, 1.0)",
        f"Obtido: {lanc_mrd}",
    )

    # 4. Conferência dos lançamentos do Aurora correspondentes a pendências (L50 e L65)
    lanc_l50 = next((l for l in aurora_linhas if l["ref_origem"] == "L50"), None)
    runner.asserir(
        lanc_l50 is not None and lanc_l50["valor"] == Decimal("7350.00"),
        "Integração Real L50 (Pix sem identificação): capturado com valor exato de R$ 7350.00",
        f"Obtido: {lanc_l50.get('valor') if lanc_l50 else 'None'}",
    )

    lanc_l65 = next((l for l in aurora_linhas if l["ref_origem"] == "L65"), None)
    runner.asserir(
        lanc_l65 is not None and lanc_l65["valor"] == Decimal("12400.00"),
        "Integração Real L65 (Devolução Mundo Aberto): capturado com valor exato de R$ 12400.00",
        f"Obtido: {lanc_l65.get('valor') if lanc_l65 else 'None'}",
    )

    # 5. Serialização estrita via contrato oficial (src/main.py)
    spec_lancamentos = config.ARQUIVOS_SAIDA[config.ARQ_LANCAMENTOS]
    try:
        linhas_serializadas = _serializar(spec_lancamentos, lista_classificados)
        runner.asserir(
            len(linhas_serializadas) == total_esperado,
            f"Serialização main.py: todas as {total_esperado} linhas passaram na validação estrita do edital",
        )
    except Exception as exc:
        runner.asserir(
            False,
            f"Serialização main.py falhou: {exc}",
        )

    # 6. Rastreabilidade matemática completa (184 linhas amarradas no tracker)
    todos_com_rastro = all(
        tracker.possui_rastro(l["id_saida"]) and tracker.total(l["id_saida"]) == l["valor"]
        for l in lista_classificados
    )
    runner.asserir(
        todos_com_rastro,
        "RastroTracker Real: todos os 184 lançamentos fecham centavo a centavo no rastro.csv",
    )

    linhas_rastro_lan = [r for r in tracker.linhas if r["id_saida"].startswith(f"{PREFIXO_LANCAMENTO}-")]
    runner.asserir(
        len(linhas_rastro_lan) == total_esperado,
        f"RastroTracker Real: exatamente {total_esperado} apontamentos de rastro registrados para lançamentos",
        f"Obtido: {len(linhas_rastro_lan)}",
    )


# ============================================================================
# 6. CASOS DE TESTE COMPATÍVEIS COM UNITTEST (python -m unittest)
# ============================================================================
class TestClassifierUnitario(unittest.TestCase):
    """Bateria de testes unitários executável via runner padrão do unittest."""

    def setUp(self) -> None:
        self.runner = TestRunner(verboso=False)

    def test_regras_deterministicas(self) -> None:
        testar_regras_deterministicas(self.runner)
        self.assertEqual(self.runner.falhas, 0, f"{self.runner.falhas} teste(s) falharam")

    def test_heuristicas_ia_e_humano(self) -> None:
        testar_heuristicas_ia_e_humano(self.runner)
        self.assertEqual(self.runner.falhas, 0, f"{self.runner.falhas} teste(s) falharam")

    def test_contrato_e_rastro(self) -> None:
        testar_contrato_e_rastro(self.runner)
        self.assertEqual(self.runner.falhas, 0, f"{self.runner.falhas} teste(s) falharam")

    def test_resiliencia_e_casos_borda(self) -> None:
        testar_resiliencia_e_casos_borda(self.runner)
        self.assertEqual(self.runner.falhas, 0, f"{self.runner.falhas} teste(s) falharam")


class TestClassifierIntegrado(unittest.TestCase):
    """Bateria de integração real com data_pack executável via runner padrão do unittest."""

    def test_integracao_real_dataset(self) -> None:
        runner = TestRunner(verboso=False)
        data_dir = _RAIZ / "data_pack"
        if data_dir.is_dir():
            testar_integracao_real(runner, data_dir)
            self.assertEqual(runner.falhas, 0, f"{runner.falhas} teste(s) falharam")


# ============================================================================
# 7. PONTO DE ENTRADA CLI
# ============================================================================
def main() -> int:
    parser = argparse.ArgumentParser(description="Testes de classifier.py (Missão 4 · Classificação Contábil ERP Fênix)")
    parser.add_argument("--unitario", action="store_true", help="Executa apenas a bateria sintética")
    parser.add_argument("--integrado", action="store_true", help="Executa apenas a integração com data_pack")
    parser.add_argument("--data-dir", default=str(_RAIZ / "data_pack"), help="Pasta com dados brutos")
    parser.add_argument("-v", "--verboso", action="store_true", help="Imprime detalhes dos testes")
    args = parser.parse_args()

    runner = TestRunner(verboso=args.verboso)
    data_dir = Path(args.data_dir)

    executar_todos = not args.unitario and not args.integrado

    if executar_todos or args.unitario:
        testar_regras_deterministicas(runner)
        testar_heuristicas_ia_e_humano(runner)
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
