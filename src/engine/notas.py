"""Geração de faturamento e Notas Fiscais de Serviços (``notas_a_emitir.csv``).

Responsabilidade:
    Determinar a lista formal de Notas Fiscais (NFS-e) que a Tarvo deve emitir
    no fechamento de competência:
    - Checkout: uma nota para cada lojista ativo com comissão líquida > R$ 0.00.
    - Remessas: exatamente UMA ÚNICA NOTA FISCAL contra a Ponte Câmbio S.A.
      (CNPJ 75.374.179/0001-46) pelo total da comissão de câmbio do mês.

Colunas de saída:
    id_saida;tomador_cnpj;tomador;linha_negocio;valor_brl;discriminacao
"""
from __future__ import annotations

from typing import Any, Dict, List

from src import config
from src.engine.rastro import RastroTracker


def gerar_notas_a_emitir(
    comissoes: List[config.Linha],
    dados_checkout: Dict[str, Any],
    dados_remessas: Dict[str, Any],
    tracker: RastroTracker,
) -> List[config.Linha]:
    """Gera o arquivo de notas fiscais a emitir pela Tarvo.

    Regras aplicadas:
        1. Lojistas com saldo de comissão zero ou negativo NÃO emitem nota fiscal.
        2. Atlas Idiomas (sem contrato assinado em 2026) NÃO emite nota fiscal.
        3. A Ponte Câmbio recebe UMA nota única consolidada pela participação nos spreads.
        4. O rastro de cada nota fiscal aponta para as mesmas operações que geraram a receita.

    Returns:
        Lista de dicionários formatados para ``notas_a_emitir.csv``.
    """
    # TODO: Implementar agregação e emissão de notas fiscais
    return []
