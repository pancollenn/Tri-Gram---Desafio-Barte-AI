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

import csv
import re
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from src import config


def _ler_arquivo_texto(caminho: Path, encodings: Sequence[str] = ("utf-8", "cp1252", "latin1")) -> str:
    """Lê o conteúdo de um arquivo de texto testando múltiplos encodings."""
    ultimo_erro: Optional[Exception] = None
    for enc in encodings:
        try:
            return caminho.read_text(encoding=enc)
        except UnicodeDecodeError as exc:
            ultimo_erro = exc
            continue
    raise RuntimeError(f"Falha ao decodificar arquivo {caminho} com encodings {encodings}: {ultimo_erro}")


def parse_aurora_csv(caminho_aurora: Path) -> List[Dict[str, Any]]:
    """Lê o extrato do Banco Aurora (CSV) preservando o número da linha física.

    Regra do edital:
        - ref_origem obrigatório é o número da linha física do arquivo (L9, L10, L50...).
        - Primeiras 6 linhas são metadados; linha 7 é cabeçalho.
        - Linhas de saldo (ex.: SALDO ANTERIOR, SALDO FINAL) não possuem movimentação
          e são desconsideradas.
    """
    conteudo = _ler_arquivo_texto(caminho_aurora, encodings=("utf-8", "cp1252", "latin1"))
    linhas = conteudo.splitlines()

    lancamentos: List[Dict[str, Any]] = []

    for indice, linha in enumerate(linhas, start=1):
        if indice <= 7:
            continue  # Pula metadados (1 a 6) e cabeçalho (7)

        linha_strip = linha.strip()
        if not linha_strip:
            continue

        partes = [p.strip() for p in linha.split(";")]
        if len(partes) < 4:
            continue

        data_str, desc_str, doc_str, val_str = partes[0], partes[1], partes[2], partes[3]

        # Ignora linhas sem valor monetário (ex.: SALDO ANTERIOR, SALDO FINAL, avisos de rodapé)
        if not val_str:
            continue

        desc_upper = desc_str.upper()
        if "SALDO ANTERIOR" in desc_upper or "SALDO FINAL" in desc_upper:
            continue

        data_iso = config.parse_data_ptbr(data_str)
        valor_dec = config.parse_decimal_ptbr(val_str)
        ref_origem = f"L{indice}"

        lancamentos.append(
            {
                "banco": config.BANCO_AURORA,
                "ref_origem": ref_origem,
                "linha_arquivo": indice,
                "linha_fisica": indice,
                "data": data_iso,
                "descricao": desc_str,
                "documento": doc_str,
                "valor": valor_dec,
                "arquivo_origem": caminho_aurora.name,
            }
        )

    return lancamentos


def parse_meridiano_ofx(caminho_meridiano: Path) -> List[Dict[str, Any]]:
    """Lê o extrato do Banco Meridiano (OFX SGML 1.02) extraindo transações STMTTRN.

    Regra do edital:
        - ref_origem obrigatório é a tag <FITID> da transação.
        - Valores negativos indicam débitos e positivos indicam créditos.
        - Datas no formato YYYYMMDD são normalizadas para AAAA-MM-DD.
    """
    conteudo = _ler_arquivo_texto(caminho_meridiano, encodings=("cp1252", "latin1", "utf-8"))

    blocos_trn = re.findall(r"<STMTTRN>(.*?)</STMTTRN>", conteudo, re.DOTALL | re.IGNORECASE)
    lancamentos: List[Dict[str, Any]] = []

    for bloco in blocos_trn:
        def _extrair_tag(tag: str) -> str:
            m = re.search(rf"<{tag}>(.*?)(?:\r?\n|<)", bloco, re.IGNORECASE)
            return m.group(1).strip() if m else ""

        trntype = _extrair_tag("TRNTYPE")
        dtposted = _extrair_tag("DTPOSTED")
        trnamt = _extrair_tag("TRNAMT")
        fitid = _extrair_tag("FITID")
        checknum = _extrair_tag("CHECKNUM")
        memo = _extrair_tag("MEMO")

        if not fitid:
            raise ValueError(f"Transação OFX sem <FITID> no arquivo {caminho_meridiano.name}")

        # Normalização da data (YYYYMMDD... -> AAAA-MM-DD)
        if len(dtposted) >= 8 and dtposted[:8].isdigit():
            data_iso = f"{dtposted[:4]}-{dtposted[4:6]}-{dtposted[6:8]}"
        else:
            raise ValueError(f"Data inválida em DTPOSTED ({dtposted}) para FITID {fitid}")

        valor_dec = config.para_decimal(trnamt)

        lancamentos.append(
            {
                "banco": config.BANCO_MERIDIANO,
                "ref_origem": fitid,
                "fitid": fitid,
                "data": data_iso,
                "descricao": memo,
                "documento": checknum,
                "valor": valor_dec,
                "tipo": trntype,
                "tipo_transacao": trntype,
                "arquivo_origem": caminho_meridiano.name,
            }
        )

    return lancamentos


def parse_plano_contas(caminho_plano: Path) -> Dict[str, Any]:
    """Carrega o Plano de Contas Analítico e Sintético do ERP Fênix."""
    conteudo = _ler_arquivo_texto(caminho_plano, encodings=("latin1", "cp1252", "utf-8"))
    linhas = conteudo.splitlines()

    leitor = csv.DictReader(linhas, delimiter=";")
    contas_lista: List[Dict[str, str]] = []
    contas_map: Dict[str, Dict[str, str]] = {}
    analiticas: Dict[str, Dict[str, str]] = {}

    for linha in leitor:
        limpo = {k.strip(): (v.strip() if v else "") for k, v in linha.items() if k}
        cod_conta = limpo.get("COD_CONTA")
        if not cod_conta:
            continue

        limpo["conta_codigo"] = cod_conta
        limpo["descricao"] = limpo.get("DESCRICAO", "")
        limpo["natureza"] = limpo.get("NATUREZA", "")
        limpo["grupo"] = limpo.get("GRUPO_CONTA", "")

        contas_lista.append(limpo)
        contas_map[cod_conta] = limpo
        if limpo.get("ACEITA_LANCTO", "").upper() == "S":
            analiticas[cod_conta] = limpo

    resultado = dict(contas_map)
    resultado.update({
        "contas": contas_map,
        "lista": contas_lista,
        "analiticas": analiticas,
        "arquivo_origem": caminho_plano.name,
    })
    return resultado


def parse_extratos_e_plano(data_dir: Union[str, Path]) -> Dict[str, Any]:
    """Lê os extratos Aurora, Meridiano e o plano de contas do ERP Fênix.

    Args:
        data_dir: Diretório onde estão os arquivos brutos.

    Returns:
        Dicionário com:
            - 'lancamentos_aurora': Lista de movimentações da CC 4471.
            - 'lancamentos_meridiano': Lista de movimentações da CC 90233.
            - 'plano_contas': Mapa/Tabela de contas contábeis do ERP.
            - 'arquivos': Nomes dos arquivos de origem processados.
    """
    caminho_aurora = config.localizar_arquivo(data_dir, "aurora")
    caminho_meridiano = config.localizar_arquivo(data_dir, "meridiano")
    caminho_plano = config.localizar_arquivo(data_dir, "plano_contas")

    lancamentos_aurora = parse_aurora_csv(caminho_aurora)
    lancamentos_meridiano = parse_meridiano_ofx(caminho_meridiano)
    plano_contas = parse_plano_contas(caminho_plano)

    return {
        "lancamentos_aurora": lancamentos_aurora,
        "lancamentos_meridiano": lancamentos_meridiano,
        "plano_contas": plano_contas,
        "arquivos": {
            "aurora": caminho_aurora.name,
            "meridiano": caminho_meridiano.name,
            "plano": caminho_plano.name,
        },
    }
