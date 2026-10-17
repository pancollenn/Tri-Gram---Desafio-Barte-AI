#!/usr/bin/env python3
"""Testes automatizados e validação completa para `src/engine/divergencias.py`.

Missão 2:
    Cruzar taxas contratadas contra taxas efetivamente aplicadas pela adquirente (Orbe)
    e pela parceira de câmbio (Ponte), calculando a diferença financeira em reais.

Este script valida exaustivamente:
1. Regras unitárias de Checkout (tolerância de 0.01 p.p., truncamento, Casa do Estudante 0.00%, Atlas sem contrato).
2. Regras unitárias de Remessas (Mundo Aberto ~1.50% vs 1.20%, 4 spreads negativos, expurgo de duplicata PC-0926-0162).
3. Contrato de saída de `divergencias_taxa.csv` (7 colunas exatas, tipos, CNPJ 14 dígitos, id_saida único).
4. Rastreabilidade matemática absoluta (cada divergência amarrada centavo a centavo no RastroTracker).
5. Casos de borda e resiliência (entradas vazias, CNPJs nulos, tracker opcional).
6. Integração completa com o dataset real de fechamento (`data_pack/`).

Uso:
    python tests/test_divergencias.py               # Executa bateria completa (unitários + integração)
    python tests/test_divergencias.py --unitario    # Executa apenas bateria de regras unitárias
    python tests/test_divergencias.py --integrado   # Executa apenas integração com data_pack
    python tests/test_divergencias.py -v            # Modo verboso
"""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

# Permite execução direta a partir de qualquer diretório de trabalho
_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from src import config
from src.engine import divergencias
from src.engine.rastro import RastroTracker
from src.main import _serializar
from src.parsers import parse_orbe, parse_ponte


class TestRunner:
    """Coletor e formatador de resultados de testes."""

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
    """Valida todas as regras de apuração de divergências com dados sintéticos controlados."""
    print("\n" + "=" * 70)
    print(" 1. TESTES UNITÁRIOS SINTÉTICOS: CHECKOUT (ORBE)")
    print("=" * 70)

    tracker = RastroTracker()
    arquivo_ck = "01_orbe_relatorio_comissoes_set2026.csv"
    arquivo_rem = "03_email_ponte_cambio_relatorio_set2026.eml"

    dados_mock_checkout: Dict[str, Any] = {
        "arquivo_origem": arquivo_ck,
        "transacoes": [
            # Caso 1: Taxa normal sem divergência (Bridge: R$ 1.000,00 @ 2.59% contratada vs 2.59% aplicada)
            {
                "id_transacao": "TX-CK-01",
                "cod_estabelecimento": "1075624862",
                "cnpj": "22.224.579/0001-09",
                "lojista": "Bridge Idiomas",
                "valor_bruto": Decimal("1000.00"),
                "taxa_contratada_pct": Decimal("2.59"),
                "taxa_aplicada_pct": Decimal("2.59"),
                "tipo_lancamento": "VENDA",
            },
            # Caso 2: Truncamento de 1 centavo da Orbe (dentro da tolerância de 0.01 p.p., NÃO é divergência)
            {
                "id_transacao": "TX-CK-02",
                "cod_estabelecimento": "1075624862",
                "cnpj": "22224579000109",
                "lojista": "Bridge Idiomas",
                "valor_bruto": Decimal("1000.00"),
                "taxa_contratada_pct": Decimal("2.59"),
                "taxa_aplicada_pct": Decimal("2.59"),
                "tipo_lancamento": "VENDA",
            },
            # Caso 3: Divergência real Checkout (Rota Global: contratada 2.49% vs aplicada 2.99% -> +0.50 p.p.)
            # R$ 2.000,00 * 0.50% = R$ 10.00
            {
                "id_transacao": "TX-CK-03",
                "cod_estabelecimento": "1074504011",
                "cnpj": "95.927.868/0001-48",
                "lojista": "Rota Global",
                "valor_bruto": Decimal("2000.00"),
                "taxa_contratada_pct": Decimal("2.49"),
                "taxa_aplicada_pct": Decimal("2.99"),
                "tipo_lancamento": "VENDA",
            },
            # Caso 4: Casa do Estudante (Regra RC-04: taxa contratada 0.00% -> toda retenção é divergência)
            # R$ 5.000,00 @ 2.69% aplicada vs 0.00% contratada = R$ 134.50
            {
                "id_transacao": "TX-CK-04",
                "cod_estabelecimento": "1018325654",
                "cnpj": "00.520.815/0001-00",
                "lojista": "Casa do Estudante Viagens",
                "valor_bruto": Decimal("5000.00"),
                "taxa_contratada_pct": Decimal("0.00"),
                "taxa_aplicada_pct": Decimal("2.69"),
                "tipo_lancamento": "VENDA",
            },
            # Caso 5: Estorno com divergência (valor negativo deduz do montante)
            # R$ -1.000,00 @ 3.49% aplicada vs 2.99% contratada (+0.50 p.p.) = R$ -5.00
            {
                "id_transacao": "TX-CK-05",
                "cod_estabelecimento": "1074504011",
                "cnpj": "95927868000148",
                "lojista": "Rota Global",
                "valor_bruto": Decimal("-1000.00"),
                "taxa_contratada_pct": Decimal("2.99"),
                "taxa_aplicada_pct": Decimal("3.49"),
                "tipo_lancamento": "ESTORNO",
            },
            # Caso 6: Atlas Idiomas (sem contrato assinado em 2026 -> NÃO gera divergência, vai p/ pendências)
            {
                "id_transacao": "TX-CK-06",
                "cod_estabelecimento": "1076801732",
                "cnpj": "10.768.017/0001-32",
                "lojista": "Atlas Idiomas",
                "valor_bruto": Decimal("1500.00"),
                "taxa_contratada_pct": None,
                "taxa_aplicada_pct": Decimal("2.69"),
                "sem_contrato": True,
            },
            # Caso 7: Transação com CNPJ ausente ou inválido (deve ser ignorada sem travar)
            {
                "id_transacao": "TX-CK-07",
                "cod_estabelecimento": "9999999999",
                "cnpj": None,
                "lojista": "Lojista Desconhecido",
                "valor_bruto": Decimal("500.00"),
                "taxa_contratada_pct": Decimal("2.00"),
                "taxa_aplicada_pct": Decimal("3.00"),
            },
        ],
    }

    divs_ck = divergencias.apurar_divergencias(dados_checkout=dados_mock_checkout, tracker=tracker)

    runner.asserir(
        len(divs_ck) == 3,
        "Checkout: apenas as 3 transações divergentes (TX-CK-03, 04, 05) foram capturadas",
        f"Capturadas: {len(divs_ck)} (esperado: 3)",
    )

    mapa_ck = {d["ref_origem"]: d for d in divs_ck}

    # Valida Caso 3 (Rota Global)
    d3 = mapa_ck.get("TX-CK-03")
    runner.asserir(
        d3 is not None and d3["diferenca_brl"] == Decimal("10.00"),
        "Checkout Rota Global: diferenca_brl calculada corretamente (R$ 10.00)",
        f"Obtido: {d3.get('diferenca_brl') if d3 else 'None'}",
    )
    runner.asserir(
        d3 is not None and d3["taxa_contratada_pct"] == Decimal("2.49") and d3["taxa_aplicada_pct"] == Decimal("2.99"),
        "Checkout Rota Global: taxas contratada (2.49%) e aplicada (2.99%) preservadas",
    )

    # Valida Caso 4 (Casa do Estudante)
    d4 = mapa_ck.get("TX-CK-04")
    runner.asserir(
        d4 is not None and d4["diferenca_brl"] == Decimal("134.50") and d4["taxa_contratada_pct"] == Decimal("0.00"),
        "Checkout Casa do Estudante: taxa contratada forçada a 0.00% e impacto R$ 134.50",
        f"Obtido: {d4}",
    )

    # Valida Caso 5 (Estorno com divergência)
    d5 = mapa_ck.get("TX-CK-05")
    runner.asserir(
        d5 is not None and d5["diferenca_brl"] == Decimal("-5.00"),
        "Checkout Estorno: diferenca_brl negativa gerada com simetria financeira (R$ -5.00)",
        f"Obtido: {d5.get('diferenca_brl') if d5 else 'None'}",
    )

    # Valida Caso 6 (Atlas Idiomas excluída de divergências)
    runner.asserir(
        "TX-CK-06" not in mapa_ck,
        "Checkout Atlas Idiomas: transação sem contrato não entra em divergencias_taxa.csv",
    )

    print("\n" + "=" * 70)
    print(" 2. TESTES UNITÁRIOS SINTÉTICOS: REMESSAS (PONTE CÂMBIO)")
    print("=" * 70)

    tracker_rem = RastroTracker()
    dados_mock_remessas: Dict[str, Any] = {
        "arquivo_origem": arquivo_rem,
        "operacoes_divergentes": [
            # Caso 8: Mundo Aberto cobrada a maior (1.50% aplicada vs 1.20% contratada sobre R$ 20.000,00)
            # R$ 20.000,00 * 0.30% = R$ 60.00
            {
                "ref_origem": "PC-REM-01",
                "num_operacao": "PC-REM-01",
                "cnpj": "17.217.888/0001-11",
                "lojista": "Mundo Aberto Intercâmbio",
                "valor_brl": Decimal("20000.00"),
                "spread_brl": Decimal("300.00"),
                "spread_pct": Decimal("1.50"),
                "taxa_aplicada_pct": Decimal("1.50"),
                "spread_contratado_pct": Decimal("1.20"),
                "taxa_contratada_pct": Decimal("1.20"),
                "is_divergente_taxa": True,
                "diferenca_brl": Decimal("60.00"),
                "linha_planilha": 10,
            },
        ],
        "operacoes_spread_negativo": [
            # Caso 9: Operação com spread negativo decorrente de trava expirada
            {
                "ref_origem": "PC-REM-NEG-01",
                "num_operacao": "PC-REM-NEG-01",
                "cnpj": "95.739.378/0001-18",
                "lojista": "Turismo Austral",
                "valor_brl": Decimal("44356.12"),
                "spread_brl": Decimal("-687.52"),
                "spread_pct": Decimal("-1.55"),
                "taxa_aplicada_pct": Decimal("-1.55"),
                "spread_contratado_pct": Decimal("1.50"),
                "taxa_contratada_pct": Decimal("1.50"),
                "is_spread_negativo": True,
                "diferenca_brl": Decimal("-687.52"),
                "linha_planilha": 15,
            },
        ],
        "operacoes_duplicadas": [
            # Caso 10: Operação duplicada que deve ser expurgada
            {
                "ref_origem": "PC-0926-0162",
                "num_operacao": "PC-0926-0162",
                "cnpj": "77.123.456/0001-88",
                "is_duplicada": True,
            }
        ],
    }

    divs_rem = divergencias.apurar_divergencias(dados_remessas=dados_mock_remessas, tracker=tracker_rem)

    runner.asserir(
        len(divs_rem) == 2,
        "Remessas: exatamente 2 operações divergentes registradas (Mundo Aberto + Negativo)",
        f"Capturadas: {len(divs_rem)} (esperado: 2)",
    )

    mapa_rem = {d["ref_origem"]: d for d in divs_rem}

    # Valida Mundo Aberto
    d_ma = mapa_rem.get("PC-REM-01")
    runner.asserir(
        d_ma is not None and d_ma["diferenca_brl"] == Decimal("60.00") and d_ma["linha_negocio"] == "REMESSA",
        "Remessas Mundo Aberto: diferenca_brl R$ 60.00 na linha REMESSA",
        f"Obtido: {d_ma}",
    )
    runner.asserir(
        d_ma is not None and d_ma["cnpj"] == "17217888000111",
        "Remessas Mundo Aberto: CNPJ sanitizado com 14 dígitos (17217888000111)",
    )

    # Valida Spread Negativo
    d_neg = mapa_rem.get("PC-REM-NEG-01")
    runner.asserir(
        d_neg is not None and d_neg["diferenca_brl"] == Decimal("-687.52") and d_neg["taxa_aplicada_pct"] == Decimal("-1.55"),
        "Remessas Spread Negativo: reportado integralmente com valor negativo (R$ -687.52)",
        f"Obtido: {d_neg}",
    )

    print("\n" + "=" * 70)
    print(" 3. TESTES DE CONTRATO, FORMATO E RASTRO MATEMÁTICO")
    print("=" * 70)

    # Combina Checkout + Remessas e valida conformidade total com o contrato do edital
    tracker_global = RastroTracker()
    todas_divs = divergencias.apurar_divergencias(
        dados_checkout=dados_mock_checkout,
        dados_remessas=dados_mock_remessas,
        tracker=tracker_global,
    )

    runner.asserir(
        len(todas_divs) == 5,
        "Consolidação: 5 divergências sintéticas geradas no total (3 checkout + 2 remessas)",
        f"Obtido: {len(todas_divs)}",
    )

    colunas_obrigatorias = config.ARQUIVOS_SAIDA[config.ARQ_DIVERGENCIAS].colunas
    todos_campos_ok = all(
        all(col in d for col in colunas_obrigatorias)
        for d in todas_divs
    )
    runner.asserir(
        todos_campos_ok,
        f"Contrato: todos os registros possuem exatamente as colunas {colunas_obrigatorias}",
    )

    # Unicidade de id_saida
    ids = [d["id_saida"] for d in todas_divs]
    runner.asserir(
        len(ids) == len(set(ids)),
        f"Unicidade: todos os id_saida são distintos ({ids})",
    )
    runner.asserir(
        all(i.startswith("DIV-") for i in ids),
        "Prefixo: todos os id_saida iniciam com 'DIV-'",
    )

    # RastroTracker: cada id_saida foi registrado e a soma bate centavo a centavo
    linhas_rastro = tracker_global.linhas
    runner.asserir(
        len(linhas_rastro) == len(todas_divs),
        f"Rastreabilidade: {len(linhas_rastro)} apontamentos criados no RastroTracker",
    )

    rastro_bate = True
    for d in todas_divs:
        total_rastro = tracker_global.total(d["id_saida"])
        if total_rastro != d["diferenca_brl"]:
            rastro_bate = False
            break
    runner.asserir(
        rastro_bate,
        "Rastreabilidade: soma de cada id_saida no rastro fecha centavo a centavo com diferenca_brl",
    )

    print("\n" + "=" * 70)
    print(" 4. TESTES DE RESILIÊNCIA E CASOS DE BORDA")
    print("=" * 70)

    # Entrada nula ou vazia não deve quebrar
    divs_vazias = divergencias.apurar_divergencias(None, None, tracker=None)
    runner.asserir(
        divs_vazias == [],
        "Resiliência: apurar_divergencias(None, None, None) devolve lista vazia sem exceção",
    )

    # Sem tracker não quebra e gera id_saida fallback
    divs_sem_tracker = divergencias.apurar_divergencias(dados_mock_checkout, tracker=None)
    runner.asserir(
        len(divs_sem_tracker) == 3 and divs_sem_tracker[0]["id_saida"] == "DIV-0000",
        "Resiliência: apurar_divergencias sem tracker opera normalmente com id fallback",
    )


# ============================================================================
# 2. BATERIA DE INTEGRAÇÃO COM DATASET REAL (DATA_PACK)
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
    print("  -> Apurando divergências reais...")
    lista_divs = divergencias.apurar_divergencias(dados_ck, dados_rem, tracker)

    # 1. Total de divergências apuradas (esperado: 238 registros)
    total_esperado = 238
    runner.asserir(
        len(lista_divs) == total_esperado,
        f"Integração Real: total de {len(lista_divs)} divergências identificadas (esperado: {total_esperado})",
        f"Obtido: {len(lista_divs)} divergências",
    )

    # 2. Separação por linha de negócio
    divs_checkout = [d for d in lista_divs if d["linha_negocio"] == config.LINHA_CHECKOUT]
    divs_remessas = [d for d in lista_divs if d["linha_negocio"] == config.LINHA_REMESSA]

    runner.asserir(
        len(divs_checkout) == 211,
        f"Integração Real Checkout: 211 divergências na adquirente Orbe (Casa do Estudante, Rota Global, Bridge)",
        f"Obtido: {len(divs_checkout)} (esperado: 211)",
    )
    runner.asserir(
        len(divs_remessas) == 27,
        f"Integração Real Remessas: 27 divergências na Ponte Câmbio (23 Mundo Aberto + 4 Spreads Negativos)",
        f"Obtido: {len(divs_remessas)} (esperado: 27)",
    )

    # 3. Conferência das 4 operações de spread negativo (trava D-1)
    refs_negativas_esperadas = {"PC-0926-0210", "PC-0926-0326", "PC-0926-0491", "PC-0926-0545"}
    refs_negativas_encontradas = {
        d["ref_origem"] for d in divs_remessas if d["diferenca_brl"] < Decimal("0.00")
    }
    runner.asserir(
        refs_negativas_encontradas == refs_negativas_esperadas,
        f"Integração Real: as 4 operações de spread negativo foram apuradas ({refs_negativas_esperadas})",
        f"Encontradas: {refs_negativas_encontradas}",
    )

    # 4. Conferência dos 23 casos da Mundo Aberto
    cnpj_mundo_aberto = "17217888000111"
    mundo_aberto_divs = [d for d in divs_remessas if d["cnpj"] == cnpj_mundo_aberto]
    runner.asserir(
        len(mundo_aberto_divs) == 23,
        f"Integração Real Mundo Aberto: exatamente 23 operações com spread cobrado a maior (1.50% vs 1.20%)",
        f"Obtido: {len(mundo_aberto_divs)} (esperado: 23)",
    )
    todas_ma_positivas = all(
        d["taxa_contratada_pct"] == Decimal("1.20")
        and d["taxa_aplicada_pct"] == Decimal("1.50")
        and d["diferenca_brl"] > Decimal("0.00")
        for d in mundo_aberto_divs
    )
    runner.asserir(
        todas_ma_positivas,
        "Integração Real Mundo Aberto: taxas 1.20% x 1.50% e diferenca_brl positiva em todas as 23 operações",
    )

    # 5. Exclusão da Atlas Idiomas (sem contrato assinado em 2026)
    cnpj_atlas = "10768017000132"
    atlas_em_divs = [d for d in lista_divs if d["cnpj"] == cnpj_atlas]
    runner.asserir(
        len(atlas_em_divs) == 0,
        "Integração Real Atlas Idiomas: zero registros em divergencias_taxa.csv (isolada para pendencias.csv)",
    )

    # 6. Expurgo da duplicata PC-0926-0162
    duplicatas_no_resultado = [d for d in lista_divs if d["ref_origem"] == "PC-0926-0162"]
    runner.asserir(
        len(duplicatas_no_resultado) <= 1,
        "Integração Real: operação duplicada PC-0926-0162 não gerou linhas repetidas",
        f"Ocorrências: {len(duplicatas_no_resultado)}",
    )

    # 7. Serialização estrita via contrato oficial (src/main.py)
    spec_div = config.ARQUIVOS_SAIDA[config.ARQ_DIVERGENCIAS]
    try:
        linhas_serializadas = _serializar(spec_div, lista_divs)
        runner.asserir(
            len(linhas_serializadas) == total_esperado,
            f"Serialização main.py: todas as {total_esperado} linhas passaram na formatação estrita do edital",
        )
    except Exception as exc:
        runner.asserir(
            False,
            f"Serialização main.py falhou: {exc}",
        )

    # 8. RastroTracker acumulou exatamente 238 linhas de rastro
    runner.asserir(
        len(tracker.linhas) == total_esperado,
        f"RastroTracker Real: exatamente {total_esperado} linhas registradas para rastro.csv",
    )


# ============================================================================
# 3. PONTO DE ENTRADA CLI
# ============================================================================
def main() -> int:
    parser = argparse.ArgumentParser(description="Testes de divergencias.py (Missão 2 · Caso Tarvo)")
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
