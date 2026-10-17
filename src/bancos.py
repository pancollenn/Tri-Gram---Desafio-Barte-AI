"""Conciliação bancária: extratos Aurora (CSV) e Meridiano (OFX) -> plano de contas Fênix.

RESPONSÁVEL: Pessoa 2. Arquivo EXCLUSIVO (ninguém mais edita).

Entradas (localizar com ``config.localizar_arquivo(data_dir, chave)``):
    - ``aurora``       -> 05a_extrato_banco_aurora_*.csv. ``ref_origem`` = número da
      linha física do arquivo (``L8``, ``L9``, ...). Cuidado com cabeçalho/linhas de saldo.
    - ``meridiano``    -> 05b_extrato_banco_meridiano_*.ofx (OFX SGML 1.02, tags sem
      fechamento). ``ref_origem`` = ``<FITID>``.
    - ``plano_contas`` -> 04_plano_de_contas_fenix_erp*.csv.

Regras confirmadas (ver HIPOTESES.md):
    - ``conta_codigo`` é a CONTRAPARTIDA do banco no plano de contas.
    - Salários/tributos de agosto pagos em setembro BAIXAM passivos já provisionados
      (ex.: ``2.1.04.001``, ``2.1.03.xxx``), não viram despesa.
    - Comissão de câmbio de agosto recebida em 04/09 baixa ``CONTA_COMISSOES_A_RECEBER``.
    - Despesas correntes não provisionadas entram em ``4.2.xxx``.
    - Transferências entre Aurora e Meridiano: ``CONTA_TRANSITORIA_MUTUO``.
    - Crédito sem identificação (Aurora L50, R$ 7.350,00): conta
      ``CONTA_TRANSITORIA_NAO_IDENTIFICADO`` + pendência ``PEND_PIX_NAO_IDENTIFICADO``.
    - Devolução de Pix (Aurora L65, R$ 12.400,00): pendência ``PEND_DEVOLUCAO_PIX``.
    - ``metodo``: ``REGRA`` (confiança 1.0) para regras determinísticas; ``IA`` só
      para casos ambíguos, com ``confianca`` < 1 e justificativa em PROMPTS/.
    - Datas em ``AAAA-MM-DD`` (use ``config.parse_data_ptbr`` para o CSV).
    - ``banco``: ``config.BANCO_AURORA`` ou ``config.BANCO_MERIDIANO``.

Contrato de rastro:
    Cada lançamento classificado recebe seu ``id_saida`` (``PREFIXO_LANCAMENTO``) e
    UMA linha de rastro: ``(id_saida, arquivo do extrato, ref_origem, valor)``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Union

from src.config import ResultadoBancos
from src.rastro_tracker import RastroTracker


def processar_bancos(
    data_dir: Union[str, Path], tracker: RastroTracker
) -> ResultadoBancos:
    """Lê os dois extratos e classifica 100% dos lançamentos no plano de contas.

    Args:
        data_dir: diretório com os arquivos brutos (já resolvido pelo ``main``).
        tracker: instância compartilhada; cada lançamento deve ter rastro.

    Returns:
        ``ResultadoBancos``:

        - ``lancamentos``: ``id_saida, banco, ref_origem, data, descricao, valor,
          conta_codigo, metodo, confianca`` (``valor`` com sinal do extrato).
        - ``pendencias``: ``id_saida, tipo, ref_origem, valor_brl, motivo,
          quem_decide`` (ex.: Aurora L50 e L65).
    """
    # TODO(Pessoa 2): implementar. Esqueleto retorna vazio para o pipeline rodar.
    return ResultadoBancos(lancamentos=[], pendencias=[])
