"""Parser de Extratos Bancários (Aurora CSV, Meridiano OFX) e Plano de Contas ERP.

Responsabilidade:
    Ler e normalizar os extratos das duas contas correntes da Tarvo e carregar
    o plano de contas analítico do ERP Fênix.

Entradas:
    - 05a_extrato_banco_aurora_*.csv (ref_origem = número da linha física L8, L9...)
    - 05b_extrato_banco_meridiano_*.ofx (OFX SGML 1.02, ref_origem = <FITID>)
    - 04_plano_de_contas_fenix_erp*.csv (conta_codigo, descricao, natureza)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Union

from src import config


def parse_extratos_e_plano(data_dir: Union[str, Path]) -> Dict[str, Any]:
    """Lê os extratos Aurora, Meridiano e o plano de contas do ERP Fênix.

    Args:
        data_dir: Diretório onde estão os arquivos brutos.

    Returns:
        Dicionário com:
            - 'lancamentos_aurora': Lista de movimentações da CC 4471.
            - 'lancamentos_meridiano': Lista de movimentações da CC 90233.
            - 'plano_contas': Mapa/Tabela de contas contábeis do ERP.
    """
    caminho_aurora = config.localizar_arquivo(data_dir, "aurora")
    caminho_meridiano = config.localizar_arquivo(data_dir, "meridiano")
    caminho_plano = config.localizar_arquivo(data_dir, "plano_contas")

    # TODO: Implementar leitura dos extratos (CSV e OFX) e do plano de contas
    return {
        "lancamentos_aurora": [],
        "lancamentos_meridiano": [],
        "plano_contas": {},
        "arquivos": {
            "aurora": caminho_aurora.name,
            "meridiano": caminho_meridiano.name,
            "plano": caminho_plano.name,
        },
    }
