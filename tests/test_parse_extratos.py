"""Script de teste e validação interativa para `parse_extratos_e_plano`.

Permite inspecionar casos de borda e validar os lançamentos bancários parseados:
- `data_pack/05a_extrato_banco_aurora_cc4471_set2026.csv`
- `data_pack/05b_extrato_banco_meridiano_cc90233_set2026.ofx`
- `data_pack/04_plano_de_contas_fenix_erp.csv`

Uso::
    python tests/test_parse_extratos.py
    python tests/test_parse_extratos.py --ref L50
    python tests/test_parse_extratos.py --ref MRD2026090132
    python tests/test_parse_extratos.py --banco AURORA
"""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

# Permite execução direta de qualquer diretório
_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from src import config
from src.parsers.parse_extratos import parse_extratos_e_plano


def main() -> None:
    parser = argparse.ArgumentParser(description="Teste interativo de parse_extratos")
    parser.add_argument("--data-dir", default="data_pack", help="Pasta com dados brutos")
    parser.add_argument("--ref", help="Filtrar por ref_origem (ex: L50, MRD2026090132)")
    parser.add_argument("--banco", help="Filtrar por banco (AURORA ou MERIDIANO)")
    args = parser.parse_args()

    dados = parse_extratos_e_plano(args.data_dir)
    aurora_txs = dados["lancamentos_aurora"]
    meridiano_txs = dados["lancamentos_meridiano"]
    plano = dados["plano_contas"]
    arquivos = dados["arquivos"]

    todos_lancamentos = aurora_txs + meridiano_txs

    print("=" * 70)
    print(" RESUMO DA EXECUÇÃO DE parse_extratos_e_plano")
    print(f"Arquivo Aurora:                 {arquivos['aurora']}")
    print(f"Arquivo Meridiano:              {arquivos['meridiano']}")
    print(f"Arquivo Plano ERP:              {arquivos['plano']}")
    print(f"Lançamentos Aurora (CC 4471):   {len(aurora_txs)}")
    print(f"Lançamentos Meridiano (CC 9023):{len(meridiano_txs)}")
    print(f"Total de Lançamentos:           {len(todos_lancamentos)}")
    print(f"Total de Contas no Plano ERP:   {len(plano['contas'])}")
    print(f"Contas Analíticas (Lançamento): {len(plano['analiticas'])}")

    # Filtro específico por ref_origem
    if args.ref:
        print(f"\nBuscando lançamento com ref_origem = {args.ref}...")
        encontrados = [t for t in todos_lancamentos if t["ref_origem"].upper() == args.ref.upper()]
        if not encontrados:
            print("Nenhum lançamento encontrado com essa referência.")
            return
        for t in encontrados:
            _imprimir_lancamento(t)
        return

    # Filtro por banco
    if args.banco:
        banco_upper = args.banco.upper()
        filtrados = [t for t in todos_lancamentos if t["banco"].upper() == banco_upper]
        print(f"\nLançamentos do banco {banco_upper} ({len(filtrados)} encontrados):")
        for t in filtrados[:15]:
            _imprimir_lancamento(t)
        if len(filtrados) > 15:
            print(f"... e mais {len(filtrados) - 15} lançamentos.")
        return

    # Execução padrão: bateria de validações de regras de negócio
    print("\n" + "=" * 70)
    print(" BATERIA DE VALIDAÇÕES DE INTEGRIDADE E REGRAS DE NEGÓCIO")
    print("=" * 70)

    # 1. Validação de contagem
    assert len(aurora_txs) == 84, f"Esperado 84 lançamentos no Aurora, obtido {len(aurora_txs)}"
    assert len(meridiano_txs) == 100, f"Esperado 100 lançamentos no Meridiano, obtido {len(meridiano_txs)}"
    assert len(plano["analiticas"]) == 32, f"Esperado 32 contas analíticas, obtido {len(plano['analiticas'])}"
    print("  [OK] Contagens exatas de extratos e contas analíticas batem com os arquivos físicos.")

    # 2. Aurora L50 (Pix não identificado)
    l50 = next((t for t in aurora_txs if t["ref_origem"] == "L50"), None)
    assert l50 is not None, "Aurora L50 não encontrado"
    assert l50["valor"] == Decimal("7350.00"), f"Valor de L50 incorreto: {l50['valor']}"
    assert "SEM IDENTIFICACAO" in l50["descricao"], f"Descrição de L50 incorreta: {l50['descricao']}"
    print("  [OK] Aurora L50 (Pix R$ 7.350,00 sem identificação) parseado com sucesso.")

    # 3. Aurora L65 (Devolução Mundo Aberto)
    l65 = next((t for t in aurora_txs if t["ref_origem"] == "L65"), None)
    assert l65 is not None, "Aurora L65 não encontrado"
    assert l65["valor"] == Decimal("12400.00"), f"Valor de L65 incorreto: {l65['valor']}"
    assert "DEVOLUCAO PIX" in l65["descricao"], f"Descrição de L65 incorreta: {l65['descricao']}"
    print("  [OK] Aurora L65 (Devolução Pix R$ 12.400,00 Mundo Aberto) parseado com sucesso.")

    # 4. Meridiano Repasse Comissão Câmbio (MRD2026090132)
    mrd_comissao = next((t for t in meridiano_txs if t["ref_origem"] == "MRD2026090132"), None)
    assert mrd_comissao is not None, "Meridiano MRD2026090132 não encontrado"
    assert mrd_comissao["valor"] == Decimal("61884.12"), f"Valor incorreto: {mrd_comissao['valor']}"
    assert "REPASSE COMISSAO" in mrd_comissao["descricao"], f"Descrição incorreta: {mrd_comissao['descricao']}"
    print("  [OK] Meridiano MRD2026090132 (Repasse Comissão Câmbio R$ 61.884,12) parseado com sucesso.")

    # 5. Mútuo entre contas (Transferências próprias)
    # No Aurora: descrição menciona "MERIDIANO"
    # No Meridiano: a contra-entrada aparece como "TARVO PAGAMENTOS LTDA - MESMA TITULARIDADE"
    mutuos_aurora = [t for t in aurora_txs if "MERIDIANO" in t["descricao"].upper()]
    mutuos_meridiano = [t for t in meridiano_txs if "MESMA TITULARIDADE" in t["descricao"].upper()]
    assert len(mutuos_aurora) == 4, f"Esperado 4 transferências para Meridiano no Aurora, obtido {len(mutuos_aurora)}"
    assert len(mutuos_meridiano) == 3, f"Esperado 3 entradas de mesma titularidade no Meridiano, obtido {len(mutuos_meridiano)}"
    total_mutuo_aurora = sum(t["valor"] for t in mutuos_aurora)
    total_mutuo_meridiano = sum(t["valor"] for t in mutuos_meridiano)
    # Os 3 TEDs com "MESMA TITULARIDADE" no Meridiano batem com 3 das 4 transferências do Aurora.
    # A 4ª (30/09, R$ -300.000) entra em outubro (liquidação D+1), por isso não aparece no Meridiano de setembro.
    assert total_mutuo_meridiano == Decimal("1150000.00"), (
        f"Soma das TEDs de mútuo no Meridiano incorreta: {total_mutuo_meridiano}"
    )
    print(f"  [OK] Mútuos Aurora→Meridiano: Aurora debitou R$ {abs(total_mutuo_aurora):,.2f}; "
          f"Meridiano creditou R$ {total_mutuo_meridiano:,.2f} em 3 TEDs (4ª liquida em out).")

    # 6. Plano de contas: contas essenciais para o classificador
    contas_essenciais = [
        config.CONTA_COMISSOES_A_RECEBER,
        config.CONTA_TRANSITORIA_MUTUO,
        config.CONTA_TRANSITORIA_NAO_IDENTIFICADO,
        "1.1.01.001",  # Aurora
        "1.1.01.002",  # Meridiano
        "2.1.04.001",  # Salários a pagar
        "2.1.03.001",  # PIS
        "2.1.03.002",  # COFINS
        "2.1.03.003",  # ISS
        "4.2.01",      # Tarifas bancárias
    ]
    for c in contas_essenciais:
        assert c in plano["analiticas"], f"Conta essencial {c} não encontrada nas contas analíticas do ERP!"
    print(f"  [OK] Todas as {len(contas_essenciais)} contas essenciais confirmadas no Plano Fênix.")

    print("\n" + "=" * 70)
    print(" AMOSTRAS DE LANÇAMENTOS CHAVE")
    print("=" * 70)
    _imprimir_lancamento(l50)
    _imprimir_lancamento(l65)
    _imprimir_lancamento(mrd_comissao)

    print("\n" + "=" * 70)
    print(f" STATUS GERAL: Todos os {len(todos_lancamentos)} lançamentos bancários validados com sucesso!")
    print("=" * 70)


def _imprimir_lancamento(t: dict) -> None:
    print(f"  Banco:            {t['banco']} | Ref Origem: {t['ref_origem']}")
    print(f"  Data:             {t['data']}")
    print(f"  Descrição:        {t['descricao']}")
    if t.get("documento"):
        print(f"  Documento:        {t['documento']}")
    print(f"  Valor:            R$ {t['valor']}")
    print(f"  Arquivo Origem:   {t['arquivo_origem']}")
    print("-" * 50)


if __name__ == "__main__":
    main()
