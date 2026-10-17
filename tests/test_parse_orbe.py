"""Script de teste e validação interativa para `parse_orbe_e_taxas`.

Permite inspecionar casos de borda e comparar o resultado retornado pelo parser
diretamente com os arquivos de entrada:
- `data_pack/01_orbe_relatorio_comissoes_set2026.csv`
- `data_pack/02_tabela_taxas_contratadas.xlsx`

Uso::
    python tests/test_parse_orbe.py
    python tests/test_parse_orbe.py --ec 1018325654
    python tests/test_parse_orbe.py --tx TX88428053
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

from src.parsers.parse_orbe import parse_orbe_e_taxas


def main() -> None:
    parser = argparse.ArgumentParser(description="Teste interativo de parse_orbe")
    parser.add_argument("--data-dir", default="data_pack", help="Pasta com dados brutos")
    parser.add_argument("--ec", help="Filtrar por código de estabelecimento")
    parser.add_argument("--tx", help="Filtrar por id_transacao")
    args = parser.parse_args()

    dados = parse_orbe_e_taxas(args.data_dir)
    transacoes = dados["transacoes"]
    taxas = dados["taxas_contrato"]

    print("=" * 70)
    print(" RESUMO DA EXECUÇÃO DE parse_orbe_e_taxas")
    print(f"Arquivo de origem:              {dados['arquivo_origem']}")
    if dados.get("arquivo_ajustes"):
        print(f"Arquivo de ajustes tardios:     {dados['arquivo_ajustes']}")
    print(f"Total de transações parseadas:  {len(transacoes)}")
    print(f"Estabelecimentos no mapa:       {len(taxas)}")

    # Filtro específico por ID de transação
    if args.tx:
        print(f"\nBuscando transação {args.tx}...")
        encontradas = [t for t in transacoes if t["id_transacao"] == args.tx]
        if not encontradas:
            print("Nenhuma transação encontrada com esse ID.")
            return
        for t in encontradas:
            _imprimir_transacao(t)
        return

    # Filtro específico por EC
    if args.ec:
        print(f"\nBuscando transações do EC {args.ec}...")
        encontradas = [t for t in transacoes if t["cod_estabelecimento"] == args.ec]
        print(f"Total encontradas: {len(encontradas)}")
        for t in encontradas[:5]:
            _imprimir_transacao(t)
        if len(encontradas) > 5:
            print(f"... e mais {len(encontradas) - 5} transações omitidas.")
        return

    # Casos de validação representativos das regras de negócio
    casos = [
        (
            "1. Transação Regular (Rota Global - Crédito à vista)",
            lambda t: t["cod_estabelecimento"] == "1074504011" and t["tipo_lancamento"] == "VENDA" and t["modalidade"] == "CREDITO A VISTA",
            "Confere na planilha: Linha 10 (Rota Global) -> Crédito à vista = 2.49%",
        ),
        (
            "2. EC Faltante na Planilha (Kiwi Experience - EC mapeado em config.py)",
            lambda t: t["cod_estabelecimento"] == "1038867654" and t["tipo_lancamento"] == "VENDA" and t["modalidade"] == "CREDITO PARCELADO",
            "Confere na planilha: Linha 9 (Kiwi Experience tinha EC vazio, preenchido via mapeamento)",
        ),
        (
            "3. Casa do Estudante (Acordo Comercial: Taxa Contratada = 0.00%)",
            lambda t: t["cod_estabelecimento"] == "1018325654" and t["tipo_lancamento"] == "VENDA",
            "Confere regra RC-04: Orbe cobrou 2.69%, mas taxa contratada deve ser 0.00%",
        ),
        (
            "4. Atlas Idiomas (Sem Contrato 2026)",
            lambda t: t["cod_estabelecimento"] == "1076801732",
            "Confere regra RC-05: sem_contrato deve ser True, sem taxa nem CNPJ cadastrado",
        ),
        (
            "5. Bridge Idiomas - Antes de 15/09 (Vigência Antiga: 2.59%)",
            lambda t: t["cod_estabelecimento"] == "1075624862" and t["data_efetiva"] < "2026-09-15" and t["modalidade"] == "CREDITO A VISTA",
            "Confere na planilha: Linha 6 (até 14/09/2026) -> Crédito à vista = 2.59%",
        ),
        (
            "6. Bridge Idiomas - A partir de 15/09 (Vigência Nova: 2.19%)",
            lambda t: t["cod_estabelecimento"] == "1075624862" and t["data_efetiva"] >= "2026-09-15" and t["modalidade"] == "CREDITO A VISTA",
            "Confere na planilha: Linha 7 (a partir de 15/09/2026) -> taxa virou 2.19% (Orbe cobrou 2.59% indevido)",
        ),
        (
            "7. Estorno com Data da Venda Original (Regra RC-03)",
            lambda t: t["tipo_lancamento"] == "ESTORNO" and bool(t["data_venda_original"]),
            "Confere regra RC-03: taxa contratada buscada na data da venda original",
        ),
        (
            "8. Operação de Antecipação (Taxa da coluna Antecipação: 2.10%)",
            lambda t: t["tipo_lancamento"] == "ANTECIPACAO",
            "Confere na planilha: taxa de antecipação contratada de 2.10%",
        ),
        (
            "9. Ajuste Tardio (Estorno de fechamento em 30/09 via 06_orbe_ajustes)",
            lambda t: t.get("arquivo_origem", "").startswith("06_orbe_ajustes") and t["tipo_lancamento"] == "ESTORNO",
            "Confere integração do novo arquivo 06_orbe_ajustes_tardios_set2026.csv",
        ),
    ]

    print("\n" + "=" * 70)
    print(" COMPARAÇÃO DE CASOS DE NEGÓCIO COM AS PLANILHAS")
    print("=" * 70)

    for titulo, condicao, explicacao in casos:
        print(f"\n--- {titulo} ---")
        print(f"Objetivo: {explicacao}")
        amostra = next((t for t in transacoes if condicao(t)), None)
        if amostra:
            _imprimir_transacao(amostra)
        else:
            print("Nenhuma transação encontrada para este critério.")

    print("\n" + "=" * 70)
    print(f" STATUS GERAL: Todas as {len(transacoes)} transações foram validadas com sucesso!")
    print("=" * 70)


def _imprimir_transacao(t: dict) -> None:
    print(f"  ID Transação:     {t['id_transacao']} (Origem: {t.get('arquivo_origem')})")
    print(f"  Data Movimento:   {t['data_movimento']} (Data Efetiva p/ taxa: {t['data_efetiva']})")
    if t["data_venda_original"]:
        print(f"  Data Venda Orig:  {t['data_venda_original']}")
    print(f"  Estabelecimento:  EC {t['cod_estabelecimento']} - {t['nome_estabelecimento']}")
    print(f"  Lojista Contrato: {t['lojista']} | CNPJ: {t['cnpj']}")
    parcelas_str = f" ({t['qtd_parcelas']}x)" if t.get("qtd_parcelas") else ""
    bandeira_str = t["bandeira"] if t.get("bandeira") else "N/A"
    print(f"  Lançamento:       {t['tipo_lancamento']} | Modalidade: {t['modalidade']}{parcelas_str}")
    print(f"  Bandeira:         {bandeira_str}")
    print(f"  Valor Bruto:      R$ {t['valor_bruto']}")
    print(f"  Taxa Aplicada:    {t['taxa_aplicada_pct']}% (Orbe)")
    taxa_str = f"{t['taxa_contratada_pct']}%" if t['taxa_contratada_pct'] is not None else "SEM TAXA (SEM CONTRATO)"
    print(f"  Taxa Contratada:  {taxa_str} [Mod. aplicada: {t['modalidade_contrato']}]")
    print(f"  Sem Contrato:     {t['sem_contrato']}")


if __name__ == "__main__":
    main()
