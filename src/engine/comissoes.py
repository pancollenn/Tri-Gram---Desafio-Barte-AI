"""Cálculo das comissões devidas à Tarvo por lojista (``comissoes_por_lojista.csv``).

Responsabilidade:
    Consome os dados tratados de Checkout (Orbe) e Remessas (Ponte Câmbio) e calcula
    a comissão líquida de cada lojista por linha de negócio, registrando a contribuição
    de cada transação no RastroTracker.

Colunas de saída:
    id_saida;cnpj;lojista;linha_negocio;comissao_brl
"""
from __future__ import annotations

from typing import Any, Dict, List

from src import config
from src.engine.rastro import RastroTracker


def calcular_comissoes(
    dados_checkout: Dict[str, Any],
    dados_remessas: Dict[str, Any],
    tracker: RastroTracker,
) -> List[config.Linha]:
    """Calcula a comissão consolidada por lojista e linha de negócio.

    Regras aplicadas:
        1. Checkout: comissão calculada pela taxa contratada (não pela aplicada pela Orbe).
        2. Estornos abatem comissão pela taxa vigente na data da venda original.
        3. Casa do Estudante: taxa contratada 0.00% (comissão = R$ 0.00).
        4. Remessas: 50% de participação no spread de operações válidas da Ponte Câmbio.
        5. Expurgo da duplicata PC-0926-0162 e exclusão dos 4 spreads negativos.
        6. Rastro: cada transação/operação é registrada via ``tracker.registrar()``.

    Returns:
        Lista de dicionários formatados para ``comissoes_por_lojista.csv``.
    """
    # TODO: Implementar lógica de cálculo e agregação
    return []
