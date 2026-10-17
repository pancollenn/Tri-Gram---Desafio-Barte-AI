"""Apuração de divergências de taxas e spreads (``divergencias_taxa.csv``).

Responsabilidade:
    Cruzar taxas contratadas contra taxas efetivamente aplicadas pela adquirente (Orbe)
    e pela parceira de câmbio (Ponte), calculando a diferença financeira em reais.

Colunas de saída:
    id_saida;cnpj;linha_negocio;ref_origem;taxa_contratada_pct;taxa_aplicada_pct;diferenca_brl
"""
from __future__ import annotations

from typing import Any, Dict, List

from src import config
from src.engine.rastro import RastroTracker


def apurar_divergencias(
    dados_checkout: Dict[str, Any],
    dados_remessas: Dict[str, Any],
    tracker: RastroTracker,
) -> List[config.Linha]:
    """Apura transações e operações com divergência de taxas.

    Regras aplicadas:
        1. Divergência = taxa_aplicada != taxa_contratada além da tolerância.
        2. Truncamento de 1 centavo da Orbe NÃO é divergência de taxa.
        3. Casa do Estudante: taxa 0.00% -> toda cobrança da Orbe é divergência.
        4. Ponte Câmbio: Mundo Aberto cobrada a 1.50% vs 1.20% contratado.
        5. Spreads negativos da Ponte Câmbio são reportados como divergência.

    Returns:
        Lista de dicionários formatados para ``divergencias_taxa.csv``.
    """
    # TODO: Implementar lógica de conferência de taxas e cálculo financeiro
    return []
