"""Parser da linha de negócio REMESSAS (Ponte Câmbio).

Responsabilidade:
    Extrair o anexo Excel (.xlsx) contido no e-mail (.eml) da Ponte Câmbio,
    processar o borderô de remessas internacionais e cruzar com os spreads contratados.

Entradas:
    - 03_email_ponte_cambio_relatorio_*.eml: anexo .xlsx extraído via módulo 'email'.
    - 02_tabela_taxas_contratadas*.xlsx: spread contratado por CNPJ.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Union

from src import config


def parse_ponte_e_taxas(data_dir: Union[str, Path]) -> Dict[str, Any]:
    """Extrai e normaliza o borderô da Ponte Câmbio e os spreads contratuais.

    Args:
        data_dir: Diretório onde estão os arquivos brutos.

    Returns:
        Dicionário com:
            - 'operacoes': Lista de operações de remessa (Nº Operação, lojista, spread, status).
            - 'spreads_contrato': Mapa de spread contratado por CNPJ da agência.
            - 'arquivo_origem': Nome do anexo Excel / arquivo de e-mail de origem.
    """
    caminho_email = config.localizar_arquivo(data_dir, "ponte_email")
    caminho_taxas = config.localizar_arquivo(data_dir, "taxas")

    # TODO: Implementar extração do .xlsx do .eml e leitura do borderô
    return {
        "operacoes": [],
        "spreads_contrato": {},
        "arquivo_origem": caminho_email.name,
    }
