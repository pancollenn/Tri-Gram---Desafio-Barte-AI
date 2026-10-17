"""Linha de negócio CHECKOUT (adquirência): Orbe x tabela de taxas contratadas.

RESPONSÁVEL: Pessoa 1. Arquivo EXCLUSIVO (ninguém mais edita).

Entradas (localizar com ``config.localizar_arquivo(data_dir, chave)``):
    - ``orbe``  -> 01_orbe_relatorio_comissoes_*.csv  (``;`` e vírgula decimal)
    - ``taxas`` -> 02_tabela_taxas_contratadas*.xlsx  (usar a aba "Taxas vigentes";
      ignorar "ANTIGO 2025 - nao usar")

Regras confirmadas (ver HIPOTESES.md):
    1. Comissão = ``round_half_up(valor_bruto * taxa_contratada_pct / 100)``, linha a
       linha. NUNCA pela taxa aplicada pela Orbe.
    2. Estorno abate a comissão pela taxa vigente na ``data_venda_original``
       (estornos de agosto abatem setembro). Reversão de antecipação anula a taxa
       da antecipação que ela reverte.
    3. Casa do Estudante (EC ``config.EC_CASA_DO_ESTUDANTE``): taxa contratada 0.00%.
       Tudo que a Orbe cobrou dela é divergência (devolver) e vai para pendências.
    4. ECs ``config.EC_FALTANTES_TABELA`` são mapeados por código (nunca por
       nome aproximado). ECs de ``config.EC_SEM_CONTRATO_2026`` (Atlas Idiomas) NÃO
       são faturados: vão para pendências (``PEND_CONTRATO_AUSENTE``).
    5. Divergência = ``taxa_aplicada != taxa_contratada`` além de
       ``config.TOLERANCIA_TAXA_PP``. A diferença de 1 centavo causada pelo
       truncamento da Orbe NÃO é divergência. ``diferenca_brl`` =
       ``valor_bruto * (aplicada - contratada) / 100``.
    6. Uma nota por lojista com comissão total > 0 (saldo zero/negativo não emite).
    7. ``ref_origem`` = ``id_transacao`` da Orbe.

Contrato de rastro:
    Para cada comissão consolidada por lojista, gerar ``id_saida`` com
    ``tracker.novo_id(PREFIXO_COMISSAO)`` e registrar UMA linha de rastro por
    transação, com a comissão da linha (negativa em estornos). A nota do lojista
    usa seu próprio ``id_saida`` (``PREFIXO_NOTA``) com o MESMO rastro.
"""
from __future__ import annotations

from pathlib import Path
from typing import Union

from src.config import ResultadoLinhaNegocio
from src.rastro_tracker import RastroTracker


def processar_checkout(
    data_dir: Union[str, Path], tracker: RastroTracker
) -> ResultadoLinhaNegocio:
    """Apura a linha CHECKOUT do mês.

    Args:
        data_dir: diretório com os arquivos brutos (já resolvido pelo ``main``).
        tracker: instância compartilhada; todo número retornado deve ter rastro.

    Returns:
        ``ResultadoLinhaNegocio`` com listas de ``Linha`` (dicts com as chaves dos
        cabeçalhos em ``config.ARQUIVOS_SAIDA``), todas com ``linha_negocio="CHECKOUT"``:

        - ``comissoes``: ``id_saida, cnpj, lojista, linha_negocio, comissao_brl``
        - ``divergencias``: ``id_saida, cnpj, linha_negocio, ref_origem,
          taxa_contratada_pct, taxa_aplicada_pct, diferenca_brl``
        - ``notas``: ``id_saida, tomador_cnpj, tomador, linha_negocio, valor_brl,
          discriminacao``
        - ``pendencias``: ``id_saida, tipo, ref_origem, valor_brl, motivo, quem_decide``

        Valores monetários/percentuais como ``Decimal`` (o ``main`` serializa).
    """
    # TODO(Pessoa 1): implementar. Esqueleto retorna vazio para o pipeline rodar.
    return ResultadoLinhaNegocio(comissoes=[], divergencias=[], notas=[], pendencias=[])
