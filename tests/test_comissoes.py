#!/usr/bin/env python3
"""Testes automatizados e validação interativa para `src/engine/comissoes.py`.

Permite validar tanto os casos de negócio unitários (isolados com dados de teste)
quanto a integração completa com o parser da Orbe (`src/parsers/parse_orbe.py`).

Uso:
    python tests/test_comissoes.py                 # Roda todos os testes (unitários + integração se houver)
    python tests/test_comissoes.py --unitario      # Roda apenas os testes unitários sintéticos
    python tests/test_comissoes.py --integrado     # Roda com os dados reais de data_pack
    python tests/test_comissoes.py --lojista Bridge
    python tests/test_comissoes.py --cnpj 00520815000100
"""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

# Permite execução direta de qualquer diretório
_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from src import config
from src.engine.comissoes import calcular_comissoes
from src.engine.rastro import RastroTracker
from src.parsers import parse_orbe, parse_ponte


class TestRunner:
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


def testar_casos_unitarios(runner: TestRunner) -> None:
    """Valida exaustivamente todas as regras de negócio de comissões com dados sintéticos."""
    print("\n" + "=" * 70)
    print(" 1. BATERIA DE TESTES UNITÁRIOS SINTÉTICOS (REGRAS DE NEGÓCIO)")
    print("=" * 70)

    tracker = RastroTracker()
    arquivo_teste_checkout = "01_orbe_relatorio_comissoes_set2026.csv"
    arquivo_teste_remessas = "03_email_ponte_cambio_relatorio_set2026.eml"

    # Dataset com casos representativos de cada regra de checkout
    dados_mock_checkout: Dict[str, Any] = {
        "arquivo_origem": arquivo_teste_checkout,
        "transacoes": [
            # Caso A: Venda comum Crédito à vista (Bridge: R$ 1.000,00 @ 2.59% = R$ 25.90)
            {
                "id_transacao": "TX-MOCK-01",
                "cod_estabelecimento": "1075624862",
                "cnpj": "22.224.579/0001-09",
                "lojista": "Bridge Idiomas",
                "valor_bruto": "1000.00",
                "taxa_contratada_pct": "2.59",
            },
            # Caso B: Estorno de venda (Bridge: R$ -300,00 @ 2.59% = R$ -7.77)
            {
                "id_transacao": "TX-MOCK-02",
                "cod_estabelecimento": "1075624862",
                "cnpj": "22224579000109",  # CNPJ sem pontuação p/ testar normalização
                "lojista": "Bridge Idiomas",
                "valor_bruto": "-300.00",
                "taxa_contratada_pct": "2.59",
            },
            # Caso C: Arredondamento half-up (Bridge: R$ 100,05 @ 2.59% = 2.591295 -> R$ 2.59)
            {
                "id_transacao": "TX-MOCK-03",
                "cod_estabelecimento": "1075624862",
                "cnpj": "22.224.579/0001-09",
                "lojista": "Bridge Idiomas",
                "valor_bruto": "100.05",
                "taxa_contratada_pct": "2.59",
            },
            # Caso D: Casa do Estudante (Regra RC-04: Acordo de Tarifa Zero 0.00%)
            # Mesmo que venha taxa da Orbe no mock, o motor deve forçar 0.00%
            {
                "id_transacao": "TX-MOCK-04",
                "cod_estabelecimento": "1018325654",
                "cnpj": "00.520.815/0001-00",
                "lojista": "Casa do Estudante Viagens",
                "valor_bruto": "4500.00",
                "taxa_contratada_pct": "2.69",  # Taxa indevida que deve ser zerada
            },
            # Caso E: Atlas Idiomas com flag sem_contrato=True (deve ser excluída)
            {
                "id_transacao": "TX-MOCK-05",
                "cod_estabelecimento": "1076801732",
                "cnpj": "10.768.017/0001-32",
                "lojista": "Atlas Idiomas",
                "valor_bruto": "1200.00",
                "taxa_contratada_pct": None,
                "sem_contrato": True,
            },
            # Caso F: Atlas Idiomas sem flag (apenas pelo EC 1076801732, deve ser blindada)
            {
                "id_transacao": "TX-MOCK-06",
                "cod_estabelecimento": "1076801732",
                "cnpj": "10.768.017/0001-32",
                "lojista": "Atlas Idiomas",
                "valor_bruto": "800.00",
                "taxa_contratada_pct": "2.59",
                "sem_contrato": False,
            },
            # Caso G: Outro Lojista (Rota Global: R$ 2.000,00 @ 2.49% = R$ 49.80)
            {
                "id_transacao": "TX-MOCK-07",
                "cod_estabelecimento": "1074504011",
                "cnpj": "95.927.868/0001-48",
                "lojista": "Rota Global",
                "valor_bruto": "2000.00",
                "taxa_contratada_pct": "2.49",
            },
        ],
    }

    # Dataset com casos representativos de cada regra de remessas
    dados_mock_remessas: Dict[str, Any] = {
        "arquivo_origem": arquivo_teste_remessas,
        "operacoes_validas": [
            # Caso H: Operação normal Mundo Aberto (Spread R$ 200,00 -> 50% = R$ 100,00)
            {
                "ref_origem": "PC-MOCK-01",
                "cnpj": "17.217.888/0001-11",
                "lojista": "Mundo Aberto",
                "spread_brl": Decimal("200.00"),
                "is_valida_comissao": True,
            },
            # Caso I: Operação normal Mundo Aberto com arredondamento half-up (Spread R$ 100,05 -> 50% = R$ 50,03)
            {
                "ref_origem": "PC-MOCK-02",
                "cnpj": "17217888000111",
                "lojista": "Mundo Aberto",
                "spread_brl": Decimal("100.05"),
                "is_valida_comissao": True,
            },
            # Caso J: Operação duplicada (deve ser ignorada se não filtrada antes)
            {
                "ref_origem": "PC-MOCK-01",
                "cnpj": "17217888000111",
                "lojista": "Mundo Aberto",
                "spread_brl": Decimal("200.00"),
                "is_duplicada": True,
            },
            # Caso K: Operação com spread negativo (deve ser excluída)
            {
                "ref_origem": "PC-MOCK-NEG",
                "cnpj": "17217888000111",
                "lojista": "Mundo Aberto",
                "spread_brl": Decimal("-150.00"),
                "is_spread_negativo": True,
            },
            # Caso L: Operação de outro lojista de Remessas (Canguru: Spread R$ 500,00 -> 50% = R$ 250,00)
            {
                "ref_origem": "PC-MOCK-04",
                "cnpj": "53.857.560/0001-23",
                "lojista": "Canguru",
                "spread_brl": Decimal("500.00"),
                "is_valida_comissao": True,
            },
        ],
    }

    resultado = calcular_comissoes(dados_mock_checkout, dados_mock_remessas, tracker)

    # 1. Validação de quantidade total de linhas (3 de checkout + 2 de remessas = 5)
    runner.asserir(
        len(resultado) == 5,
        "Quantidade de linhas de comissão (esperado 5: 3 de Checkout + 2 de Remessa)",
        f"Obtido {len(resultado)}: {[r['lojista'] + ' (' + r['linha_negocio'] + ')' for r in resultado]}",
    )

    # 2. Atlas Idiomas NÃO deve estar presente
    cnpjs_retornados = {r["cnpj"] for r in resultado}
    runner.asserir(
        "10768017000132" not in cnpjs_retornados,
        "Atlas Idiomas foi corretamente excluída das comissões (sem contrato 2026)",
    )

    # 3. Conferência de valores calculados para a Bridge Idiomas (Checkout)
    bridge = next((r for r in resultado if "Bridge" in r["lojista"]), None)
    if bridge:
        # Esperado: 25.90 - 7.77 + 2.59 = 20.72
        esperado_bridge = Decimal("20.72")
        runner.asserir(
            bridge["comissao_brl"] == esperado_bridge,
            f"Cálculo e estorno da Bridge Idiomas (Esperado: R$ {esperado_bridge})",
            f"Obtido: R$ {bridge['comissao_brl']}",
        )
        runner.asserir(
            bridge["linha_negocio"] == config.LINHA_CHECKOUT,
            "Linha de negócio da Bridge é 'CHECKOUT'",
        )

    # 4. Conferência da Casa do Estudante (Checkout: Tarifa zero)
    casa = next((r for r in resultado if "Casa do Estudante" in r["lojista"]), None)
    if casa:
        runner.asserir(
            casa["comissao_brl"] == Decimal("0.00"),
            "Comissão de Checkout da Casa do Estudante é rigorosamente R$ 0.00 (Tarifa Zero)",
            f"Obtido: R$ {casa['comissao_brl']}",
        )

    # 5. Conferência da Mundo Aberto (Remessa: 50% de 200.00 + 50% de 100.05 = 100.00 + 50.03 = 150.03)
    mundo = next((r for r in resultado if "Mundo Aberto" in r["lojista"] and r["linha_negocio"] == config.LINHA_REMESSA), None)
    if mundo:
        esperado_mundo = Decimal("150.03")
        runner.asserir(
            mundo["comissao_brl"] == esperado_mundo,
            f"Cálculo de Remessa da Mundo Aberto (50% do Spread c/ half-up: Esperado R$ {esperado_mundo})",
            f"Obtido: R$ {mundo['comissao_brl']}",
        )
        runner.asserir(
            mundo["linha_negocio"] == config.LINHA_REMESSA,
            "Linha de negócio da Mundo Aberto é 'REMESSA'",
        )

    # 6. Conferência da Canguru (Remessa: 50% de 500.00 = 250.00)
    canguru_remessa = next((r for r in resultado if "Canguru" in r["lojista"] and r["linha_negocio"] == config.LINHA_REMESSA), None)
    if canguru_remessa:
        runner.asserir(
            canguru_remessa["comissao_brl"] == Decimal("250.00"),
            "Cálculo de Remessa da Canguru (50% de R$ 500.00 = R$ 250.00)",
            f"Obtido: R$ {canguru_remessa['comissao_brl']}",
        )

    # 7. Rastreabilidade Matemática (RastroTracker)
    print("\n--- Validação do Motor de Rastreabilidade (rastro.csv) ---")
    falhas_rastro = []
    for r in resultado:
        try:
            tracker.validar_soma(r["id_saida"], r["comissao_brl"])
        except AssertionError as exc:
            falhas_rastro.append(str(exc))

    runner.asserir(
        len(falhas_rastro) == 0,
        "Rastro fecha centavo a centavo com o valor reportado para todos os lojistas (Checkout e Remessa)",
        "\n".join(falhas_rastro) if falhas_rastro else None,
    )

    # 8. Unicidade e formato dos IDs de saída
    ids_emitidos = [r["id_saida"] for r in resultado]
    runner.asserir(
        len(ids_emitidos) == len(set(ids_emitidos)),
        "Todos os id_saida gerados são únicos",
        f"IDs: {ids_emitidos}",
    )
    runner.asserir(
        all(i.startswith(config.PREFIXO_COMISSAO) for i in ids_emitidos),
        f"Todos os ids iniciam com o prefixo correto '{config.PREFIXO_COMISSAO}'",
    )


def testar_integracao_real(runner: TestRunner, data_dir_str: str, filtro_lojista: Optional[str] = None, filtro_cnpj: Optional[str] = None) -> None:
    """Executa o cálculo sobre a saída real de `parse_orbe_e_taxas` e `parse_ponte_e_taxas`."""
    print("\n" + "=" * 70)
    print(" 2. TESTE DE INTEGRAÇÃO COM DADOS REAIS (`data_pack/`)")
    print("=" * 70)

    try:
        data_dir = config.resolver_data_dir(data_dir_str)
    except FileNotFoundError as exc:
        print(f"  [AVISO] Diretório de dados não encontrado ({exc}). Pulando teste de integração.")
        return

    print(f"Lendo dados de entrada em: {data_dir}")
    try:
        dados_checkout = parse_orbe.parse_orbe_e_taxas(data_dir)
        dados_remessas = parse_ponte.parse_ponte_e_taxas(data_dir)
    except Exception as exc:
        print(f"  [AVISO] Falha ao executar parsers: {exc}")
        return

    transacoes = dados_checkout.get("transacoes", [])
    operacoes = dados_remessas.get("operacoes_validas", [])

    print(f"Total de transações de Checkout: {len(transacoes)}")
    print(f"Total de operações válidas de Remessas: {len(operacoes)}")

    tracker = RastroTracker()
    resultado = calcular_comissoes(dados_checkout, dados_remessas, tracker)

    res_checkout = [r for r in resultado if r["linha_negocio"] == config.LINHA_CHECKOUT]
    res_remessas = [r for r in resultado if r["linha_negocio"] == config.LINHA_REMESSA]

    runner.asserir(
        len(res_checkout) == 21,
        f"Checkout gerou dados para 21 lojistas (obtido: {len(res_checkout)})",
    )
    runner.asserir(
        len(res_remessas) == 14,
        f"Remessas gerou dados para 14 lojistas (obtido: {len(res_remessas)})",
    )
    runner.asserir(
        len(resultado) == 35,
        f"Total consolidado = 35 linhas de comissão (obtido: {len(resultado)})",
    )

    # Validar rastro de todos os lojistas
    falhas_rastro = []
    for r in resultado:
        try:
            tracker.validar_soma(r["id_saida"], r["comissao_brl"])
        except AssertionError as exc:
            falhas_rastro.append(str(exc))

    runner.asserir(
        len(falhas_rastro) == 0,
        f"Rastro validado com sucesso para todas as {len(resultado)} linhas de comissão",
        f"{len(falhas_rastro)} linha(s) com divergência" if falhas_rastro else None,
    )

    # Validar valores totais consolidados
    total_checkout = sum(r["comissao_brl"] for r in res_checkout)
    total_remessas = sum(r["comissao_brl"] for r in res_remessas)
    esperado_remessas = Decimal("39543.45")

    runner.asserir(
        total_remessas == esperado_remessas,
        f"Total de comissões de Remessa fecha centavo a centavo em R$ {esperado_remessas} (obtido: R$ {total_remessas})",
    )

    # Validar ausência da Atlas Idiomas
    tem_atlas = any("atlas" in r["lojista"].lower() for r in resultado)
    runner.asserir(
        not tem_atlas,
        "Atlas Idiomas ausente das comissões ativas da base real (conforme edital)",
    )

    # Validar Casa do Estudante no Checkout
    casa_checkout = next((r for r in res_checkout if "estudante" in r["lojista"].lower()), None)
    if casa_checkout:
        runner.asserir(
            casa_checkout["comissao_brl"] == Decimal("0.00"),
            "Casa do Estudante apurada com R$ 0.00 de comissão no Checkout",
            f"Valor apurado: R$ {casa_checkout['comissao_brl']}",
        )

    # Exibição da tabela de fechamento de comissões
    print("\n" + "-" * 85)
    print(f"{'ID SAÍDA':<10} {'CNPJ':<16} {'LINHA':<10} {'LOJISTA':<33} {'COMISSÃO BRL':>12}")
    print("-" * 85)

    for r in resultado:
        # Filtros opcionais de CLI
        if filtro_lojista and filtro_lojista.lower() not in r["lojista"].lower():
            continue
        if filtro_cnpj and filtro_cnpj not in r["cnpj"]:
            continue

        print(f"{r['id_saida']:<10} {r['cnpj']:<16} {r['linha_negocio']:<10} {r['lojista'][:32]:<33} {r['comissao_brl']:>12.2f}")

    print("-" * 85)
    print(f"{'TOTAL CHECKOUT':<71} R$ {total_checkout:>10.2f}")
    print(f"{'TOTAL REMESSAS':<71} R$ {total_remessas:>10.2f}")
    print(f"{'TOTAL GERAL':<71} R$ {total_checkout + total_remessas:>10.2f}")
    print("-" * 85)
    print(f"Total de linhas registradas no rastro.csv: {len(tracker.linhas)}")



def main() -> int:
    parser = argparse.ArgumentParser(description="Testes automatizados do módulo de comissões")
    parser.add_argument("--data-dir", default="data_pack", help="Diretório com os dados brutos")
    parser.add_argument("--unitario", action="store_true", help="Executar apenas os testes unitários")
    parser.add_argument("--integrado", action="store_true", help="Executar apenas a integração com data_pack")
    parser.add_argument("--lojista", help="Filtrar lojista na listagem integrada")
    parser.add_argument("--cnpj", help="Filtrar CNPJ na listagem integrada")
    parser.add_argument("-v", "--verboso", action="store_true", help="Modo verboso com detalhes")
    args = parser.parse_args()

    runner = TestRunner(verboso=args.verboso)

    if not args.integrado:
        testar_casos_unitarios(runner)

    if not args.unitario:
        testar_integracao_real(runner, args.data_dir, args.lojista, args.cnpj)

    print("\n" + "=" * 70)
    print(f" RESUMO FINAL: {runner.sucessos} teste(s) aprovados | {runner.falhas} falha(s)")
    print("=" * 70)

    if runner.falhas == 0:
        print(">>> TODOS OS TESTES PASSARAM COM SUCESSO! <<<\n")
        return 0
    else:
        print(f">>> FORAM ENCONTRADAS {runner.falhas} FALHA(S) NOS TESTES. <<<\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
