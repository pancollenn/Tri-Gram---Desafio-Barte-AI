"""Linha de negócio REMESSA (câmbio): relatório da Ponte Câmbio x taxas contratadas.

RESPONSÁVEL: Pessoa 2. Arquivo EXCLUSIVO (ninguém mais edita).

Entradas (localizar com ``config.localizar_arquivo(data_dir, chave)``):
    - ``ponte_email`` -> 03_email_ponte_cambio_relatorio_*.eml: extrair o anexo
      ``.xlsx`` com o módulo ``email`` da biblioteca padrão e lê-lo com ``openpyxl``
      (em memória, sem gravar arquivo intermediário).
    - ``taxas`` -> 02_tabela_taxas_contratadas*.xlsx (spread contratado por CNPJ;
      célula vazia ou "padrão" = ``config.SPREAD_PADRAO_PCT``).

Regras confirmadas (ver HIPOTESES.md):
    1. Comissão da Tarvo = ``round_half_up(PARTICIPACAO_TARVO_SPREAD * Spread R$)``
       POR OPERAÇÃO (arredonda antes de somar).
    2. Vale a Data de Contratação para a competência.
    3. Operação repetida (ex.: ``config.OPERACAO_DUPLICADA_SET2026``): conta UMA vez;
       a linha extra vira pendência ``PEND_OPERACAO_DUPLICADA`` (retificação da
       Ponte). Detectar pelos dados (mesmo ``Nº Operação``), não por ID fixo.
    4. Spread negativo (trava D-1 expirada >2h): fora da comissão e da nota;
       pendência ``PEND_SPREAD_NEGATIVO`` + divergência. Detectar por spread < 0.
    5. Divergência de spread (ex.: Mundo Aberto, 1.50% cobrado vs 1.20% contratado):
       nota sai pelo realizado; divergência reportada pelo valor CHEIO =
       ``(spread_aplicado - spread_contratado) * PTAX * Valor ME`` e pendência
       ``PEND_DIVERGENCIA_SPREAD`` para contestar com a Ponte.
    6. "Aprovado com ressalva" NÃO altera liquidação nem comissão.
    7. UMA única nota contra ``config.PONTE_CAMBIO_CNPJ`` pelo total das comissões
       válidas (``linha_negocio="REMESSA"``).
    8. ``ref_origem`` = ``Nº Operação``. Ignorar linhas de resumo/rodapé do relatório.

Contrato de rastro:
    Uma linha de rastro por operação válida (comissão da operação) para cada
    ``id_saida`` de comissão (por lojista) e para o ``id_saida`` da nota única.
"""
from __future__ import annotations

from pathlib import Path
from typing import Union

from src.config import ResultadoLinhaNegocio
from src.rastro_tracker import RastroTracker


def processar_remessas(
    data_dir: Union[str, Path], tracker: RastroTracker
) -> ResultadoLinhaNegocio:
    """Apura a linha REMESSA do mês.

    Args:
        data_dir: diretório com os arquivos brutos (já resolvido pelo ``main``).
        tracker: instância compartilhada; todo número retornado deve ter rastro.

    Returns:
        ``ResultadoLinhaNegocio`` com ``linha_negocio="REMESSA"``:

        - ``comissoes``: uma linha por lojista com a soma das comissões válidas.
        - ``divergencias``: spread contratado x aplicado (Mundo Aberto, negativos).
        - ``notas``: exatamente UMA nota contra a Ponte Câmbio (lista vazia se não
          houver comissão a faturar).
        - ``pendencias``: duplicata, spreads negativos e contestações cambiais.

        Chaves/colunas idênticas às descritas em ``config.ARQUIVOS_SAIDA``.
    """
    # TODO(Pessoa 2): implementar. Esqueleto retorna vazio para o pipeline rodar.
    return ResultadoLinhaNegocio(comissoes=[], divergencias=[], notas=[], pendencias=[])
