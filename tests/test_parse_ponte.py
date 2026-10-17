#!/usr/bin/env python3
"""Script de testes automatizados e validação interativa para `src/parsers/parse_ponte.py`.

Valida todas as regras de negócio e contratos de dados de Remessas (Ponte Câmbio):
- Extração do anexo .xlsx do e-mail .eml em memória;
- Leitura correta do cabeçalho na linha 5 e 233 operações totais;
- Detecção e sinalização da operação duplicada PC-0926-0162;
- Detecção e exclusão dos 4 spreads negativos (travas D-1 expiradas);
- Apuração das 228 operações válidas e cálculo de comissão Tarvo (R$ 39.543,45);
- Detecção das 23 divergências contratuais da Mundo Aberto (1.50% vs 1.20%);
- Aplicação do spread padrão (1.50%) para células vazias ou 'padrão' (Kiwi, Canguru, Ponte Aérea);
- Sanitização de CNPJs para 14 dígitos e tipagem rigorosa com Decimal e datas ISO.

Uso::
    python tests/test_parse_ponte.py               # Roda toda a bateria de testes automatizados
    python tests/test_parse_ponte.py --op PC-0926-0002   # Inspeciona uma operação específica
    python tests/test_parse_ponte.py --cnpj 17217888000111 # Filtra por CNPJ (ex: Mundo Aberto)
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
from src.parsers.parse_ponte import parse_ponte_e_taxas, SpreadContratado


class TestRunner:
    """Coletor e formatador de asserções de teste."""

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


def _imprimir_operacao(op: Dict[str, Any]) -> None:
    """Imprime os campos de uma operação de câmbio de forma estruturada."""
    print(f"  Nº Operação:       {op['ref_origem']} (Linha {op.get('linha_planilha')})")
    print(f"  Data Contratação:  {op.get('data_contratacao')} | Data Liq: {op.get('data_liquidacao')}")
    print(f"  Lojista:           {op['lojista']} | CNPJ: {op['cnpj']}")
    print(f"  Cliente Planilha:  {op.get('cliente')}")
    print(f"  Moeda:             {op['moeda']} | Valor ME: {op['valor_moeda']}")
    print(f"  Taxa Câmbio:       {op['taxa_cambio']} | PTAX: {op['taxa_ptax']}")
    print(f"  Valor R$:          R$ {op['valor_brl']}")
    print(f"  Spread R$:         R$ {op['spread_brl']} ({op['spread_pct']}%)")
    print(f"  Spread Contrato:   {op['spread_contratado_pct']}%")
    print(f"  Comissão Tarvo:    R$ {op['comissao_tarvo_brl']}")
    print(f"  Status:            {op['status']} | Obs: {op.get('observacao') or 'N/A'}")
    print(f"  Flags:             valida_comissao={op['is_valida_comissao']}, duplicada={op['is_duplicada']}, spread_negativo={op['is_spread_negativo']}, divergente={op['is_divergente_taxa']}")


def executar_bateria_testes(dados: Dict[str, Any], runner: TestRunner) -> None:
    """Executa todas as asserções de regras de negócio contra a base parseada."""
    ops: List[Dict[str, Any]] = dados["operacoes"]
    validas: List[Dict[str, Any]] = dados["operacoes_validas"]
    duplicadas: List[Dict[str, Any]] = dados["operacoes_duplicadas"]
    negativas: List[Dict[str, Any]] = dados["operacoes_spread_negativo"]
    divergentes: List[Dict[str, Any]] = dados["operacoes_divergentes"]
    spreads_contrato: Dict[str, Any] = dados["spreads_contrato"]

    print("\n" + "=" * 70)
    print(" 1. ESTRUTURA GERAL E METADADOS DO E-MAIL")
    print("=" * 70)

    runner.asserir(
        dados["arquivo_origem"].startswith("03_email_ponte_cambio"),
        f"Arquivo de origem é o .eml esperado ({dados['arquivo_origem']})",
    )
    runner.asserir(
        dados["nome_anexo_xlsx"].endswith(".xlsx"),
        f"Anexo extraído em memória é um arquivo .xlsx ({dados['nome_anexo_xlsx']})",
    )
    runner.asserir(
        "Subject" in dados["email_metadata"].get("assunto", "") or len(dados["email_metadata"].get("assunto", "")) > 0,
        f"Metadados de cabeçalho do e-mail extraídos (Assunto: '{dados['email_metadata'].get('assunto')}')",
    )
    runner.asserir(
        len(ops) == 233,
        f"Total de operações extraídas da aba Operações = 233 (obtido: {len(ops)})",
    )

    print("\n" + "=" * 70)
    print(" 2. EXPURGO DE DUPLICATA E EXCLUSÃO DE SPREADS NEGATIVOS")
    print("=" * 70)

    runner.asserir(
        len(duplicadas) == 1,
        f"Exatamente 1 operação duplicada detectada (obtido: {len(duplicadas)})",
    )
    if duplicadas:
        id_dup = duplicadas[0]["ref_origem"]
        runner.asserir(
            id_dup == config.OPERACAO_DUPLICADA_SET2026,
            f"Operação duplicada é '{config.OPERACAO_DUPLICADA_SET2026}' (obtido: {id_dup})",
        )
        runner.asserir(
            duplicadas[0]["is_valida_comissao"] is False,
            "Operação duplicada marcada com is_valida_comissao=False",
        )

    runner.asserir(
        len(negativas) == 4,
        f"Exatamente 4 operações com spread negativo detectadas (obtido: {len(negativas)})",
    )
    ids_neg_obtidos = {n["ref_origem"] for n in negativas}
    ids_neg_esperados = set(config.SPREADS_NEGATIVOS_SET2026)
    runner.asserir(
        ids_neg_obtidos == ids_neg_esperados,
        f"IDs dos spreads negativos batem com a especificação ({sorted(ids_neg_obtidos)})",
    )
    for n in negativas:
        runner.asserir(
            n["is_valida_comissao"] is False and n["comissao_tarvo_brl"] == Decimal("0.00"),
            f"Spread negativo {n['ref_origem']} excluído de comissão (R$ 0.00)",
        )

    print("\n" + "=" * 70)
    print(" 3. OPERAÇÕES VÁLIDAS E CÁLCULO DE COMISSÃO TARVO (50%)")
    print("=" * 70)

    runner.asserir(
        len(validas) == 228,
        f"Operações válidas para faturamento = 228 (233 - 1 dup - 4 neg) (obtido: {len(validas)})",
    )

    # Soma de comissão linha a linha
    comissao_calculada = sum(op["comissao_tarvo_brl"] for op in validas)
    comissao_esperada = Decimal("39543.45")
    runner.asserir(
        comissao_calculada == comissao_esperada,
        f"Comissão Tarvo consolidada fecha centavo a centavo em R$ {comissao_esperada} (obtido: {comissao_calculada})",
        detalhe=f"Diferença: {comissao_calculada - comissao_esperada}",
    )

    # Confere que nenhuma válida tem flag negativa ou duplicada
    runner.asserir(
        all(not op["is_duplicada"] and not op["is_spread_negativo"] for op in validas),
        "Todas as operações na lista 'operacoes_validas' estão limpas de duplicatas e spreads negativos",
    )

    print("\n" + "=" * 70)
    print(" 4. CONFERÊNCIA DE SPREADS CONTRATUAIS E DIVERGÊNCIAS (MUNDO ABERTO)")
    print("=" * 70)

    runner.asserir(
        len(divergentes) == 23,
        f"Total de operações divergentes identificadas = 23 (obtido: {len(divergentes)})",
    )

    # Todas as divergentes devem ser da Mundo Aberto (CNPJ 17.217.888/0001-11)
    cnpj_mundo_aberto = "17217888000111"
    todas_mundo_aberto = all(op["cnpj"] == cnpj_mundo_aberto for op in divergentes)
    runner.asserir(
        todas_mundo_aberto,
        "Todas as operações divergentes pertencem à Mundo Aberto Intercâmbio",
    )
    if divergentes:
        op_amostra = divergentes[0]
        runner.asserir(
            op_amostra["spread_contratado_pct"] == Decimal("1.20"),
            f"Taxa contratada da Mundo Aberto é 1.20% (obtido: {op_amostra['spread_contratado_pct']}%)",
        )
        runner.asserir(
            op_amostra["spread_pct"] > Decimal("1.45"),
            f"Taxa cobrada pela Ponte foi ~1.50% (obtido: {op_amostra['spread_pct']}%)",
        )
        runner.asserir(
            op_amostra["diferenca_brl"] > Decimal("0.00"),
            f"Diferença financeira em reais é positiva (amostra {op_amostra['ref_origem']}: R$ {op_amostra['diferenca_brl']})",
        )

    print("\n" + "=" * 70)
    print(" 5. SPREAD PADRÃO (1.50%) PARA CÉLULAS EM BRANCO OU 'PADRÃO'")
    print("=" * 70)

    # Kiwi Experience (07752116000126): spread vazio na tabela -> deve ser 1.50%
    cnpj_kiwi = "07752116000126"
    spread_kiwi = spreads_contrato.get(cnpj_kiwi)
    runner.asserir(
        spread_kiwi is not None and spread_kiwi.spread_pct == Decimal("1.50"),
        f"Kiwi Experience (spread em branco) assumiu taxa padrão de 1.50% (obtido: {spread_kiwi})",
    )

    # Ponte Aérea Estudantil (95739378000118): spread vazio na tabela -> deve ser 1.50%
    cnpj_ponte_aerea = "95739378000118"
    spread_ponte_aerea = spreads_contrato.get(cnpj_ponte_aerea)
    runner.asserir(
        spread_ponte_aerea is not None and spread_ponte_aerea.spread_pct == Decimal("1.50"),
        f"Ponte Aérea Estudantil (spread em branco) assumiu taxa padrão de 1.50% (obtido: {spread_ponte_aerea})",
    )

    # Canguru (53857560000123): spread com texto 'padrão' -> deve ser 1.50%
    cnpj_canguru = "53857560000123"
    spread_canguru = spreads_contrato.get(cnpj_canguru)
    runner.asserir(
        spread_canguru is not None and spread_canguru.spread_pct == Decimal("1.50"),
        f"Canguru (texto 'padrão' na célula) assumiu taxa padrão de 1.50% (obtido: {spread_canguru})",
    )

    # Nenhuma operação da Kiwi ou Canguru pode estar em divergentes (exceto as negativas de trava)
    kiwi_canguru_em_div = [
        op["ref_origem"] for op in divergentes if op["cnpj"] in (cnpj_kiwi, cnpj_canguru)
    ]
    runner.asserir(
        len(kiwi_canguru_em_div) == 0,
        "Nenhuma operação normal da Kiwi ou Canguru foi falsamente classificada como divergente",
    )

    print("\n" + "=" * 70)
    print(" 6. INTEGRIDADE DOS DADOS, SANITIZAÇÃO DE CNPJ E TIPAGEM")
    print("=" * 70)

    runner.asserir(
        all(len(op["cnpj"]) == 14 and op["cnpj"].isdigit() for op in ops),
        "100% dos CNPJs possuem exatamente 14 dígitos numéricos",
    )
    runner.asserir(
        all(isinstance(op["valor_brl"], Decimal) for op in ops),
        "100% dos valores em reais (valor_brl) são instâncias de Decimal",
    )
    runner.asserir(
        all(isinstance(op["spread_brl"], Decimal) for op in ops),
        "100% dos spreads em reais (spread_brl) são instâncias de Decimal",
    )
    runner.asserir(
        all(isinstance(op["comissao_tarvo_brl"], Decimal) for op in ops),
        "100% das comissões calculadas são instâncias de Decimal",
    )
    runner.asserir(
        all(len(op["data"]) == 10 and op["data"][4] == "-" and op["data"][7] == "-" for op in ops),
        "100% das datas estão estritamente no padrão ISO 'AAAA-MM-DD'",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Teste automatizado e validação de parse_ponte")
    parser.add_argument("--data-dir", help="Diretório onde estão os arquivos brutos (padrão: auto-detectado)")
    parser.add_argument("--op", help="Filtrar e inspecionar uma operação específica por Nº Operação (ex: PC-0926-0002)")
    parser.add_argument("--cnpj", help="Filtrar e inspecionar operações de um CNPJ (ex: 17217888000111)")
    args = parser.parse_args()

    print("=" * 70)
    print(" INICIANDO TESTES DO PARSER DE REMESSAS (Ponte Câmbio)")
    print("=" * 70)

    # Executa o parser
    dados = parse_ponte_e_taxas(args.data_dir)
    ops = dados["operacoes"]

    # Modo 1: Filtro por Operação Específica
    if args.op:
        print(f"\nBuscando operação '{args.op}'...")
        encontradas = [o for o in ops if o["ref_origem"] == args.op]
        if not encontradas:
            print(f"Nenhuma operação encontrada com o ID '{args.op}'.")
            sys.exit(1)
        for op in encontradas:
            _imprimir_operacao(op)
        return

    # Modo 2: Filtro por CNPJ Específico
    if args.cnpj:
        cnpj_limpo = config.clean_cnpj(args.cnpj)
        print(f"\nBuscando operações do CNPJ '{cnpj_limpo}'...")
        encontradas = [o for o in ops if o["cnpj"] == cnpj_limpo]
        print(f"Total encontradas: {len(encontradas)}")
        for op in encontradas[:5]:
            print("-" * 50)
            _imprimir_operacao(op)
        if len(encontradas) > 5:
            print(f"... e mais {len(encontradas) - 5} operações omitidas.")
        return

    # Modo 3: Bateria Completa de Testes
    runner = TestRunner()
    executar_bateria_testes(dados, runner)

    print("\n" + "=" * 70)
    print(f" RESUMO FINAL: {runner.sucessos} teste(s) aprovado(s) | {runner.falhas} falha(s)")
    print("=" * 70)

    if runner.falhas > 0:
        print(">>> ATENÇÃO: ALGUNS TESTES FALHARAM! <<<", file=sys.stderr)
        sys.exit(1)
    else:
        print(">>> TODOS OS TESTES PASSARAM COM SUCESSO! O PARSER ESTÁ 100% FUNCIONAL. <<<")


if __name__ == "__main__":
    main()
