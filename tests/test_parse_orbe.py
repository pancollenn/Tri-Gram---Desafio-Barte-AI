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

from src import config
from src.parsers.parse_orbe import parse_orbe_e_taxas


def main() -> None:
    parser = argparse.ArgumentParser(description="Teste interativo e de regressão de parse_orbe")
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

    # Validação geral de integridade da base
    assert len(transacoes) == 1957, f"Esperado 1957 transações consolidadas, obtido {len(transacoes)}"
    assert len(taxas) >= 20, f"Esperado ao menos 20 estabelecimentos no mapa de contratos, obtido {len(taxas)}"
    assert all(isinstance(t["valor_bruto"], Decimal) for t in transacoes), "Valor bruto deve ser Decimal"
    assert all(isinstance(t["valor_taxa"], Decimal) for t in transacoes), "Valor taxa deve ser Decimal"
    assert all(len(t["data_movimento"]) == 10 and t["data_movimento"][4] == "-" for t in transacoes), "Data deve ser ISO AAAA-MM-DD"

    def _val_caso_1(t: dict) -> None:
        assert t is not None, "Transação de Rota Global não encontrada"
        taxa = config.para_decimal(t["taxa_contratada_pct"]).quantize(config.CENTAVO)
        assert taxa == Decimal("2.49"), f"Taxa Rota Global esperada 2.49%, obtido {t['taxa_contratada_pct']}%"
        assert t["cnpj"] == "95927868000148", f"CNPJ Rota Global incorreto: {t['cnpj']}"
        assert t["sem_contrato"] is False

    def _val_caso_2(t: dict) -> None:
        assert t is not None, "Transação de Kiwi Experience não encontrada"
        assert t["cnpj"] == "07752116000126", f"CNPJ Kiwi Experience incorreto: {t['cnpj']}"
        taxa = config.para_decimal(t["taxa_contratada_pct"]).quantize(config.CENTAVO)
        assert taxa == Decimal("3.19"), f"Taxa crédito 2-6x esperada 3.19%, obtido {t['taxa_contratada_pct']}%"
        assert t["sem_contrato"] is False

    def _val_caso_3(t: dict) -> None:
        assert t is not None, "Transação de Casa do Estudante não encontrada"
        assert t["taxa_contratada_pct"] == Decimal("0.00"), f"Taxa esperada 0.00%, obtido {t['taxa_contratada_pct']}"
        assert t["sem_contrato"] is False
        assert t["cnpj"] == "00520815000100", f"CNPJ Casa do Estudante incorreto: {t['cnpj']}"

    def _val_caso_4(t: dict) -> None:
        assert t is not None, "Transação de Atlas Idiomas não encontrada"
        assert t["sem_contrato"] is True, "Atlas Idiomas deveria ser sem_contrato=True"
        assert t["taxa_contratada_pct"] is None, f"Atlas Idiomas não deve ter taxa contratada: {t['taxa_contratada_pct']}"
        assert t["cnpj"] is None, f"Atlas Idiomas não deve ter CNPJ: {t['cnpj']}"

    def _val_caso_5(t: dict) -> None:
        assert t is not None, "Transação Bridge Idiomas antiga não encontrada"
        taxa = config.para_decimal(t["taxa_contratada_pct"]).quantize(config.CENTAVO)
        assert taxa == Decimal("2.59"), f"Taxa esperada 2.59% até 14/09, obtido {t['taxa_contratada_pct']}%"
        assert t["cnpj"] == "22224579000109", f"CNPJ Bridge Idiomas incorreto: {t['cnpj']}"

    def _val_caso_6(t: dict) -> None:
        assert t is not None, "Transação Bridge Idiomas nova não encontrada"
        taxa = config.para_decimal(t["taxa_contratada_pct"]).quantize(config.CENTAVO)
        assert taxa == Decimal("2.19"), f"Taxa esperada 2.19% a partir de 15/09, obtido {t['taxa_contratada_pct']}%"
        assert t["cnpj"] == "22224579000109", f"CNPJ Bridge Idiomas incorreto: {t['cnpj']}"

    def _val_caso_7(t: dict) -> None:
        assert t is not None, "Estorno com data de venda original não encontrado"
        assert t["data_efetiva"] == t["data_venda_original"], "data_efetiva deve ser igual à data_venda_original"
        assert t["taxa_contratada_pct"] is not None, "Estorno deve possuir taxa contratada aplicável"

    def _val_caso_8(t: dict) -> None:
        assert t is not None, "Operação de antecipação não encontrada"
        taxa = config.para_decimal(t["taxa_contratada_pct"]).quantize(config.CENTAVO)
        assert taxa == Decimal("2.10"), f"Taxa de antecipação esperada 2.10%, obtido {t['taxa_contratada_pct']}%"
        assert t["modalidade_contrato"] == "antecipacao"

    def _val_caso_9(t: dict) -> None:
        assert t is not None, "Ajuste tardio não encontrado"
        assert t["tipo_lancamento"] == "ESTORNO", "Ajuste tardio deve ser ESTORNO"
        assert t["data_movimento"] == "2026-09-30", f"Data esperada 2026-09-30, obtido {t['data_movimento']}"
        assert t["taxa_contratada_pct"] is not None, "Ajuste tardio deve ter taxa contratada calculada"

    # Casos de validação representativos das regras de negócio
    casos = [
        (
            "1. Transação Regular (Rota Global - Crédito à vista)",
            lambda t: t["cod_estabelecimento"] == "1074504011" and t["tipo_lancamento"] == "VENDA" and t["modalidade"] == "CREDITO A VISTA",
            "Confere na planilha: Linha 10 (Rota Global) -> Crédito à vista = 2.49%",
            _val_caso_1,
        ),
        (
            "2. EC Faltante na Planilha (Kiwi Experience - EC mapeado em config.py)",
            lambda t: t["cod_estabelecimento"] == "1038867654" and t["tipo_lancamento"] == "VENDA" and t["modalidade"] == "CREDITO PARCELADO",
            "Confere na planilha: Linha 9 (Kiwi Experience tinha EC vazio, preenchido via mapeamento)",
            _val_caso_2,
        ),
        (
            "3. Casa do Estudante (Acordo Comercial: Taxa Contratada = 0.00%)",
            lambda t: t["cod_estabelecimento"] == "1018325654" and t["tipo_lancamento"] == "VENDA",
            "Confere regra RC-04: Orbe cobrou 2.69%, mas taxa contratada deve ser 0.00%",
            _val_caso_3,
        ),
        (
            "4. Atlas Idiomas (Sem Contrato 2026)",
            lambda t: t["cod_estabelecimento"] == "1076801732",
            "Confere regra RC-05: sem_contrato deve ser True, sem taxa nem CNPJ cadastrado",
            _val_caso_4,
        ),
        (
            "5. Bridge Idiomas - Antes de 15/09 (Vigência Antiga: 2.59%)",
            lambda t: t["cod_estabelecimento"] == "1075624862" and t["data_efetiva"] < "2026-09-15" and t["modalidade"] == "CREDITO A VISTA",
            "Confere na planilha: Linha 6 (até 14/09/2026) -> Crédito à vista = 2.59%",
            _val_caso_5,
        ),
        (
            "6. Bridge Idiomas - A partir de 15/09 (Vigência Nova: 2.19%)",
            lambda t: t["cod_estabelecimento"] == "1075624862" and t["data_efetiva"] >= "2026-09-15" and t["modalidade"] == "CREDITO A VISTA",
            "Confere na planilha: Linha 7 (a partir de 15/09/2026) -> taxa virou 2.19% (Orbe cobrou 2.59% indevido)",
            _val_caso_6,
        ),
        (
            "7. Estorno com Data da Venda Original (Regra RC-03)",
            lambda t: t["tipo_lancamento"] == "ESTORNO" and bool(t["data_venda_original"]),
            "Confere regra RC-03: taxa contratada buscada na data da venda original",
            _val_caso_7,
        ),
        (
            "8. Operação de Antecipação (Taxa da coluna Antecipação: 2.10%)",
            lambda t: t["tipo_lancamento"] == "ANTECIPACAO",
            "Confere na planilha: taxa de antecipação contratada de 2.10%",
            _val_caso_8,
        ),
        (
            "9. Ajuste Tardio (Estorno de fechamento em 30/09 via 06_orbe_ajustes)",
            lambda t: t.get("arquivo_origem", "").startswith("06_orbe_ajustes") and t["tipo_lancamento"] == "ESTORNO",
            "Confere integração do novo arquivo 06_orbe_ajustes_tardios_set2026.csv",
            _val_caso_9,
        ),
    ]

    print("\n" + "=" * 70)
    print(" COMPARAÇÃO DE CASOS DE NEGÓCIO COM AS PLANILHAS")
    print("=" * 70)

    for titulo, condicao, explicacao, validador in casos:
        print(f"\n--- {titulo} ---")
        print(f"Objetivo: {explicacao}")
        amostra = next((t for t in transacoes if condicao(t)), None)
        assert amostra is not None, f"Falha na asserção: nenhuma transação encontrada para '{titulo}'"
        validador(amostra)
        print("  [OK] Regra validada por assert!")
        _imprimir_transacao(amostra)

    print("\n" + "=" * 70)
    print(f" STATUS GERAL: Todas as {len(transacoes)} transações e os 9 cenários foram validados com sucesso!")
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
