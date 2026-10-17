"""Parser da linha de negócio CHECKOUT (Adquirência Orbe e Taxas Contratadas).

Responsabilidade:
    Ler o relatório de comissões da adquirente Orbe e cruzar com a tabela de taxas
    contratadas vigentes, entregando estruturas de dados normalizadas e tipadas (Decimal).

Entradas:
    - 01_orbe_relatorio_comissoes_*.csv (delimitador ';', vírgula decimal)
    - 02_tabela_taxas_contratadas*.xlsx (aba 'Taxas vigentes', ignorando aba antiga)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Union

from src import config


def parse_orbe_e_taxas(data_dir: Union[str, Path]) -> Dict[str, Any]:
    """Lê e normaliza o relatório da Orbe e a tabela de taxas vigentes.

    Args:
        data_dir: Diretório onde estão os arquivos brutos.

    Returns:
        Dicionário com:
            - 'transacoes': Lista de transações da Orbe com tipos convertidos.
            - 'taxas_contrato': Mapa de taxas contratadas por lojista / modalidade.
            - 'arquivo_origem': Nome exato do arquivo CSV lido.
    """
    caminho_orbe = config.localizar_arquivo(data_dir, "orbe")
    caminho_taxas = config.localizar_arquivo(data_dir, "taxas")

    # TODO: Implementar leitura via csv / pandas / openpyxl
    return {
        "transacoes": [],
        "taxas_contrato": {},
        "arquivo_origem": caminho_orbe.name,
    }
