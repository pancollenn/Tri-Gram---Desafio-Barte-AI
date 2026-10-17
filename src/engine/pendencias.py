"""Consolidação e triagem de pendências operacionais (``pendencias.csv``).

Responsabilidade:
    Catalogar formalmente todas as anomalias, disputas e transações ambíguas
    que não podem ser decididas automaticamente e exigem deliberação humana
    (Comercial, Financeiro ou Diretoria).

Colunas de saída:
    id_saida;tipo;ref_origem;valor_brl;motivo;quem_decide
"""
from __future__ import annotations

from typing import Any, Dict, List

from src import config
from src.engine.rastro import RastroTracker


def consolidar_pendencias(
    dados_checkout: Dict[str, Any],
    dados_remessas: Dict[str, Any],
    dados_bancos: Dict[str, Any],
    tracker: RastroTracker,
) -> List[config.Linha]:
    """Reúne todas as pendências identificadas no ciclo de fechamento.

    Catálogo de Pendências Esperadas:
        1. Atlas Idiomas: EC sem contrato assinado em 2026 (Comercial).
        2. Casa do Estudante: devolução de taxas cobradas indevidamente pela Orbe (Financeiro).
        3. Ponte Câmbio: operação duplicada PC-0926-0162 (Operações Ponte).
        4. Ponte Câmbio: 4 operações com spread negativo (Financeiro/Parcerias).
        5. Ponte Câmbio: divergência no spread cobrado da Mundo Aberto (Comercial).
        6. Banco Aurora: Pix de R$ 7.350,00 recebido sem identificação L50 (Financeiro).
        7. Banco Aurora: devolução de Pix de R$ 12.400,00 L65 (Operações).

    Returns:
        Lista de dicionários formatados para ``pendencias.csv``.
    """
    # TODO: Implementar agregação das anomalias
    return []
