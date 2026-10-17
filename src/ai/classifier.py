"""Classificação contábil inteligente dos extratos bancários (``lancamentos_classificados.csv``).

Responsabilidade:
    Ler os lançamentos bancários dos bancos Aurora e Meridiano e mapear cada um
    para uma conta analítica do plano de contas do ERP Fênix, informando método
    ('REGRA', 'IA' ou 'HUMANO') e índice de confiança (0 a 1.0).

Colunas de saída:
    id_saida;banco;ref_origem;data;descricao;valor;conta_codigo;metodo;confianca
"""
from __future__ import annotations

from typing import Any, Dict, List

from src import config
from src.engine.rastro import RastroTracker


def classificar_lancamentos(
    dados_extratos: Dict[str, Any],
    tracker: RastroTracker,
) -> List[config.Linha]:
    """Classifica 100% dos lançamentos dos bancos Aurora e Meridiano no ERP Fênix.

    Regras aplicadas:
        1. 'conta_codigo' é a contrapartida contábil do banco no plano de contas.
        2. Salários e tributos de agosto pagos em setembro BAIXAM passivos já provisionados
           (2.1.04.001, 2.1.03.xxx), não viram despesa nova do mês.
        3. Comissões de câmbio de agosto recebidas em 04/09 baixam 'CONTA_COMISSOES_A_RECEBER'.
        4. Despesas correntes entram no grupo 4.2.xxx.
        5. Lançamentos com regras determinísticas recebem 'metodo=REGRA' e 'confianca=1.0'.
        6. Casos atípicos utilizam a LLM para classificação com 'metodo=IA'.
        7. Casos irresolvíveis (ex.: Pix não identificado) usam conta transitória
           e geram registro no rastro.

    Returns:
        Lista de dicionários formatados para ``lancamentos_classificados.csv``.
    """
    # TODO: Implementar motor híbrido (Regex determinístico + LLM para exceções)
    return []
