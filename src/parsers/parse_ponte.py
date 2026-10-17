"""Parser da linha de negócio REMESSAS (Ponte Câmbio e Spreads Contratados).

Responsabilidade:
    1. Extrair o anexo Excel (.xlsx) contido na mensagem MIME (.eml) enviada pela parceira
       Ponte Câmbio utilizando exclusivamente a biblioteca nativa 'email'.
    2. Ler a tabela de taxas contratuais (02_tabela_taxas_contratadas.xlsx), aba 'Taxas vigentes',
       extraindo os spreads contratados de remessa por CNPJ e tratando o spread padrão (1.50%).
    3. Processar a aba 'Operações' da planilha da Ponte Câmbio (ignorando a aba 'Resumo'):
       - Pular o cabeçalho institucional e mapear dinamicamente as colunas;
       - Converter datas para ISO 'AAAA-MM-DD' e valores monetários para Decimal;
       - Sanitizar CNPJs para 14 dígitos com zeros à esquerda;
       - Cruzar cada operação com o spread contratado do lojista;
       - Identificar e sinalizar a duplicata (PC-0926-0162);
       - Identificar e sinalizar operações com spread negativo (trava expirada D-1);
       - Isolar as operações válidas para cálculo de comissão (50% do Spread R$);
       - Identificar operações com divergência entre spread aplicado e contratado (ex: Mundo Aberto).

Entradas:
    - 03_email_ponte_cambio_relatorio_*.eml (mensagem MIME com anexo .xlsx)
    - 02_tabela_taxas_contratadas*.xlsx (aba 'Taxas vigentes')
"""
from __future__ import annotations

import email
from email import policy
import io
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
import sys
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from typing import Any, Dict, List, Optional, Tuple, Union

import openpyxl

from src import config


# ============================================================================
# 1. ESTRUTURA HÍBRIDA DE SPREAD CONTRATADO (DECIMAL + DICT)
# ============================================================================
class SpreadContratado(Decimal):
    """Representação híbrida do spread contratado de um lojista.

    Permite utilização direta em operações aritméticas::

        diferenca = spread_aplicado - spreads_contratados[cnpj]

    E também acesso a metadados cadastrais indexados como dicionário ou atributos::

        taxa = spreads_contratados[cnpj]['spread_pct']
        lojista = spreads_contratados[cnpj].lojista
    """

    spread_pct: Decimal
    taxa_contratada_pct: Decimal
    lojista: str
    cnpj: str
    ec: Optional[str]
    vigencia_inicio: Optional[str]
    vigencia_fim: Optional[str]
    observacao: str

    def __new__(
        cls,
        valor: Any,
        lojista: str = "",
        cnpj: str = "",
        ec: Optional[str] = None,
        vigencia_inicio: Optional[str] = None,
        vigencia_fim: Optional[str] = None,
        observacao: str = "",
    ) -> SpreadContratado:
        dec_val = config.para_decimal(valor).quantize(config.CENTAVO, rounding=ROUND_HALF_UP)
        obj = super().__new__(cls, str(dec_val))
        obj.spread_pct = dec_val
        obj.taxa_contratada_pct = dec_val
        obj.lojista = lojista
        obj.cnpj = cnpj
        obj.ec = ec
        obj.vigencia_inicio = vigencia_inicio
        obj.vigencia_fim = vigencia_fim
        obj.observacao = observacao
        return obj

    def __getitem__(self, key: str) -> Any:
        if key in ("spread_pct", "taxa_contratada_pct", "spread_remessa_pct", "spread", "taxa", "valor"):
            return self.spread_pct
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cnpj": self.cnpj,
            "lojista": self.lojista,
            "ec": self.ec,
            "spread_pct": self.spread_pct,
            "taxa_contratada_pct": self.taxa_contratada_pct,
            "vigencia_inicio": self.vigencia_inicio,
            "vigencia_fim": self.vigencia_fim,
            "observacao": self.observacao,
        }

    def __repr__(self) -> str:
        return f"SpreadContratado({self.spread_pct}%, lojista='{self.lojista}', cnpj='{self.cnpj}')"


# ============================================================================
# 2. FUNÇÕES AUXILIARES DE NORMALIZAÇÃO E LIMPEZA
# ============================================================================
def _strip_accents(texto: Any) -> str:
    """Remove acentos, pontuação e converte para minúsculas normalizadas."""
    if texto is None:
        return ""
    norm = "".join(
        c for c in unicodedata.normalize("NFD", str(texto).strip())
        if unicodedata.category(c) != "Mn"
    ).lower()
    return re.sub(r"\s+", " ", norm).strip()


def _normalizar_chave(texto: Any) -> str:
    """Normaliza nomes de colunas ou chaves removendo símbolos e espaços."""
    s = _strip_accents(texto)
    s = s.replace("º", "o").replace("°", "o").replace("$", "s").replace("%", "pct")
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def _normalizar_data(valor: Any) -> str:
    """Converte date, datetime, número de série do Excel ou string pt-BR para 'AAAA-MM-DD'."""
    if valor is None:
        return ""
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    # Se for número de série do Excel (ex: 46295)
    if isinstance(valor, (int, float, Decimal)):
        dias = int(float(valor))
        if 20000 <= dias <= 80000:
            epoch = date(1899, 12, 30)
            from datetime import timedelta
            return (epoch + timedelta(days=dias)).isoformat()
    texto = str(valor).strip()
    if not texto:
        return ""
    try:
        return config.parse_data_ptbr(texto)
    except Exception:
        # Tenta casar formato ISO YYYY-MM-DD
        m = re.match(r"^(\d{4}-\d{2}-\d{2})", texto)
        if m:
            return m.group(1)
        return texto


def _converter_percentual(valor_raw: Any) -> Decimal:
    """Converte percentuais da planilha para pontos percentuais com precisão Decimal.

    Exemplos:
        - 0.01501 (fração decimal Excel) -> Decimal('1.50')
        - 0.012 (fração decimal Excel) -> Decimal('1.20')
        - '1,50%' ou '1.50' -> Decimal('1.50')
        - -0.015523 (spread negativo) -> Decimal('-1.55')
    """
    if valor_raw is None or str(valor_raw).strip() == "":
        return Decimal("0.00")

    if isinstance(valor_raw, (int, float)):
        dec = Decimal(str(valor_raw))
        # Se for fração decimal (< 1 ou > -1, diferente de zero), multiplica por 100
        if dec != Decimal("0") and abs(dec) < Decimal("1"):
            dec = dec * Decimal("100")
        return dec.quantize(config.CENTAVO, rounding=ROUND_HALF_UP)

    texto = str(valor_raw).strip()
    texto = texto.replace("%", "").strip()
    dec = config.parse_decimal_ptbr(texto)
    if dec != Decimal("0") and abs(dec) < Decimal("0.10"):
        dec = dec * Decimal("100")
    return dec.quantize(config.CENTAVO, rounding=ROUND_HALF_UP)


# ============================================================================
# 3. EXTRAÇÃO DO ANEXO .XLSX A PARTIR DO .EML
# ============================================================================
def extrair_anexo_xlsx_de_eml(caminho_eml: Union[str, Path]) -> Dict[str, Any]:
    """Extrai os bytes do anexo Excel e os metadados do e-mail (.eml).

    Args:
        caminho_eml: Caminho para o arquivo .eml da Ponte Câmbio.

    Returns:
        Dicionário com:
            - 'xlsx_bytes': Conteúdo binário decodificado do arquivo .xlsx.
            - 'nome_anexo': Nome do anexo original (ex: 'PonteCambio_Relatorio_TARVO_092026.xlsx').
            - 'email_metadata': Metadados do cabeçalho (assunto, remetente, data, corpo).
    """
    caminho = Path(caminho_eml)
    if not caminho.is_file():
        raise FileNotFoundError(f"Arquivo de e-mail não encontrado: {caminho}")

    raw_bytes = caminho.read_bytes()
    msg = email.message_from_bytes(raw_bytes, policy=policy.default)

    assunto = str(msg.get("Subject", "")).strip()
    remetente = str(msg.get("From", "")).strip()
    destinatario = str(msg.get("To", "")).strip()
    data_envio = str(msg.get("Date", "")).strip()

    corpo_texto = ""
    xlsx_bytes: Optional[bytes] = None
    nome_anexo: str = ""

    for part in msg.walk():
        if part.is_multipart():
            continue

        filename = part.get_filename() or ""
        content_type = (part.get_content_type() or "").lower()

        if (
            filename.lower().endswith(".xlsx")
            or "spreadsheetml" in content_type
            or "excel" in content_type
        ):
            payload = part.get_payload(decode=True)
            if payload:
                xlsx_bytes = bytes(payload)
                nome_anexo = filename or "PonteCambio_Relatorio_TARVO_092026.xlsx"
        elif content_type == "text/plain" and not filename:
            try:
                content = part.get_content()
                if isinstance(content, str):
                    corpo_texto = content.strip()
            except Exception:
                payload = part.get_payload(decode=True)
                if payload:
                    corpo_texto = payload.decode("utf-8", errors="replace").strip()

    if xlsx_bytes is None:
        raise ValueError(f"Nenhum anexo .xlsx foi encontrado dentro do e-mail '{caminho.name}'.")

    return {
        "xlsx_bytes": xlsx_bytes,
        "nome_anexo": nome_anexo,
        "email_metadata": {
            "assunto": assunto,
            "remetente": remetente,
            "destinatario": destinatario,
            "data_envio": data_envio,
            "corpo_texto": corpo_texto,
        },
    }


# ============================================================================
# 4. CARREGAMENTO DOS SPREADS CONTRATADOS (02_tabela_taxas_contratadas.xlsx)
# ============================================================================
def carregar_spreads_contratados(
    caminho_taxas: Union[str, Path],
) -> Tuple[Dict[str, SpreadContratado], Dict[str, SpreadContratado], Dict[str, Dict[str, Any]]]:
    """Lê a aba 'Taxas vigentes' e constrói o mapa de spreads de remessa contratados.

    Regras aplicadas:
        - Ignora abas históricas antigas (ex: 'ANTIGO 2025').
        - Ignora notas de rodapé iniciadas com '*' na coluna de lojistas.
        - Célula de spread em branco, None ou com texto 'padrão' assume config.SPREAD_PADRAO_PCT (1.50%).
        - Sanitiza os CNPJs para exatamente 14 dígitos numéricos com zeros à esquerda.

    Returns:
        Tupla com:
            - spreads_por_cnpj: Mapa {cnpj: SpreadContratado}
            - spreads_por_nome: Mapa {nome_normalizado: SpreadContratado}
            - cadastro_por_cnpj: Dicionário serializável com cadastro dos lojistas
    """
    caminho = Path(caminho_taxas)
    wb = openpyxl.load_workbook(caminho, data_only=True)

    nome_aba = "Taxas vigentes"
    if nome_aba not in wb.sheetnames:
        for s in wb.sheetnames:
            if "vigente" in s.lower():
                nome_aba = s
                break
    ws = wb[nome_aba]

    spreads_por_cnpj: Dict[str, SpreadContratado] = {}
    spreads_por_nome: Dict[str, SpreadContratado] = {}
    cadastro_por_cnpj: Dict[str, Dict[str, Any]] = {}

    # O cabeçalho está na linha 5 e os dados iniciam na linha 6
    for row in ws.iter_rows(min_row=6, values_only=True):
        lojista_raw = row[0]
        if not lojista_raw or str(lojista_raw).strip().startswith("*"):
            continue

        lojista = str(lojista_raw).strip()
        cnpj_raw = row[1]
        ec_raw = row[2]
        spread_raw = row[9] if len(row) > 9 else None
        vigencia_raw = row[10] if len(row) > 10 else None
        obs_raw = row[11] if len(row) > 11 else ""

        cnpj = config.clean_cnpj(cnpj_raw) if cnpj_raw else ""
        ec = str(ec_raw).strip() if ec_raw is not None else None

        # Trata spread de remessa contratado
        if (
            spread_raw is None
            or str(spread_raw).strip() == ""
            or "padr" in str(spread_raw).lower()
        ):
            spread_pct = config.SPREAD_PADRAO_PCT
        elif isinstance(spread_raw, (int, float)):
            dec = Decimal(str(spread_raw))
            if abs(dec) < Decimal("1") and dec != Decimal("0"):
                dec = dec * Decimal("100")
            spread_pct = dec.quantize(config.CENTAVO, rounding=ROUND_HALF_UP)
        else:
            txt_spread = str(spread_raw).replace("%", "").strip()
            spread_pct = config.parse_decimal_ptbr(txt_spread).quantize(
                config.CENTAVO, rounding=ROUND_HALF_UP
            )

        vigencia_str = str(vigencia_raw).strip() if vigencia_raw else None
        obs_str = str(obs_raw).strip() if obs_raw else ""

        obj = SpreadContratado(
            valor=spread_pct,
            lojista=lojista,
            cnpj=cnpj,
            ec=ec,
            vigencia_inicio=vigencia_str,
            observacao=obs_str,
        )

        if cnpj:
            spreads_por_cnpj[cnpj] = obj
            cadastro_por_cnpj[cnpj] = obj.to_dict()

        spreads_por_nome[_strip_accents(lojista)] = obj

    return spreads_por_cnpj, spreads_por_nome, cadastro_por_cnpj


# ============================================================================
# 5. PARSE DA ABA 'OPERAÇÕES' DA PONTE CÂMBIO
# ============================================================================
def _ler_planilha_operacoes(
    xlsx_bytes: bytes,
    spreads_por_cnpj: Dict[str, SpreadContratado],
    spreads_por_nome: Dict[str, SpreadContratado],
    arquivo_origem: str,
) -> Dict[str, Any]:
    """Processa a aba 'Operações' da planilha da Ponte Câmbio em memória."""
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=True)

    # 1. Localiza a aba 'Operações' (ignora a aba 'Resumo' para o fechamento)
    nome_aba_operacoes = None
    nome_aba_resumo = None
    for s in wb.sheetnames:
        norm = _strip_accents(s)
        if "operac" in norm:
            nome_aba_operacoes = s
        elif "resumo" in norm:
            nome_aba_resumo = s

    if nome_aba_operacoes is None:
        nome_aba_operacoes = wb.sheetnames[0]

    ws = wb[nome_aba_operacoes]

    # 2. Localiza dinamicamente a linha de cabeçalho
    idx_header = None
    for r in range(1, min(15, ws.max_row + 1)):
        vals = [_strip_accents(ws.cell(row=r, column=c).value) for c in range(1, ws.max_column + 1)]
        if any("operac" in v for v in vals) and any("cnpj" in v for v in vals):
            idx_header = r
            break

    if idx_header is None:
        raise ValueError(
            f"Não foi possível localizar o cabeçalho das operações na aba '{nome_aba_operacoes}'."
        )

    # Mapeamento dinâmico de colunas
    col_map: Dict[str, int] = {}
    for c in range(1, ws.max_column + 1):
        val = ws.cell(row=idx_header, column=c).value
        h = _normalizar_chave(val)
        if not h:
            continue
        if "operac" in h:
            col_map["num_op"] = c
        elif "contrat" in h:
            col_map["dt_contrat"] = c
        elif "liquid" in h:
            col_map["dt_liquid"] = c
        elif "cnpj" in h:
            col_map["cnpj"] = c
        elif "cliente" in h and "cnpj" not in h and "taxa" not in h:
            col_map["cliente"] = c
        elif "moeda" in h and "valor" not in h:
            col_map["moeda"] = c
        elif "valor_me" in h or ("valor" in h and ("me" in h or "moeda" in h or "estrangeiro" in h)):
            col_map["valor_me"] = c
        elif ("taxa" in h or "cambio" in h) and "ptax" not in h:
            col_map["taxa_cliente"] = c
        elif "ptax" in h:
            col_map["ptax"] = c
        elif ("valor_r" in h or "valor_brl" in h or "total" in h) and "spread" not in h and "iof" not in h:
            col_map["valor_brl"] = c
        elif "spread_pct" in h or ("spread" in h and "pct" in h):
            col_map["spread_pct"] = c
        elif "spread" in h and ("r" in h or "brl" in h) and "estimado" not in h:
            col_map["spread_brl"] = c
        elif "status" in h:
            col_map["status"] = c
        elif "obs" in h or "motivo" in h:
            col_map["observacao"] = c

    # Estruturas para classificação e auditoria
    operacoes: List[Dict[str, Any]] = []
    operacoes_validas: List[Dict[str, Any]] = []
    operacoes_duplicadas: List[Dict[str, Any]] = []
    operacoes_spread_negativo: List[Dict[str, Any]] = []
    operacoes_divergentes: List[Dict[str, Any]] = []

    operacoes_vistas: Dict[str, int] = {}

    for r in range(idx_header + 1, ws.max_row + 1):
        num_op_raw = ws.cell(row=r, column=col_map.get("num_op", 1)).value
        if not num_op_raw:
            continue
        ref_origem = str(num_op_raw).strip()
        # Filtra eventuais linhas de rodapé ou totalização
        if not ref_origem.startswith("PC-") and not re.match(r"^[A-Za-z]{2}-\d+", ref_origem):
            continue

        dt_contrat_raw = ws.cell(row=r, column=col_map["dt_contrat"]).value if "dt_contrat" in col_map else None
        dt_liquid_raw = ws.cell(row=r, column=col_map["dt_liquid"]).value if "dt_liquid" in col_map else None
        data_contratacao = _normalizar_data(dt_contrat_raw)
        data_liquidacao = _normalizar_data(dt_liquid_raw)
        data_efetiva = data_contratacao or data_liquidacao

        cnpj_raw = ws.cell(row=r, column=col_map["cnpj"]).value if "cnpj" in col_map else None
        cnpj = config.clean_cnpj(cnpj_raw) if cnpj_raw else ""

        cliente_planilha = str(
            ws.cell(row=r, column=col_map["cliente"]).value or ""
        ).strip() if "cliente" in col_map else ""

        # Enriquecimento com os dados de contrato
        info_contrato = spreads_por_cnpj.get(cnpj)
        if info_contrato is None and cliente_planilha:
            info_contrato = spreads_por_nome.get(_strip_accents(cliente_planilha))
            if info_contrato is not None and not cnpj:
                cnpj = info_contrato.cnpj

        lojista = (
            info_contrato.lojista
            if (info_contrato is not None and info_contrato.lojista)
            else cliente_planilha
        )
        spread_contratado_pct = (
            info_contrato.spread_pct if info_contrato is not None else config.SPREAD_PADRAO_PCT
        )

        moeda = str(
            ws.cell(row=r, column=col_map["moeda"]).value or ""
        ).strip().upper() if "moeda" in col_map else ""

        val_me_raw = ws.cell(row=r, column=col_map["valor_me"]).value if "valor_me" in col_map else None
        valor_moeda = config.para_decimal(str(val_me_raw)) if val_me_raw is not None else Decimal("0.00")

        taxa_cli_raw = ws.cell(row=r, column=col_map["taxa_cliente"]).value if "taxa_cliente" in col_map else None
        taxa_cambio = config.para_decimal(str(taxa_cli_raw)) if taxa_cli_raw is not None else Decimal("0.00")

        ptax_raw = ws.cell(row=r, column=col_map["ptax"]).value if "ptax" in col_map else None
        taxa_ptax = config.para_decimal(str(ptax_raw)) if ptax_raw is not None else Decimal("0.00")

        val_brl_raw = ws.cell(row=r, column=col_map["valor_brl"]).value if "valor_brl" in col_map else None
        valor_brl = config.round_half_up(str(val_brl_raw)) if val_brl_raw is not None else Decimal("0.00")

        spread_brl_raw = ws.cell(row=r, column=col_map["spread_brl"]).value if "spread_brl" in col_map else None
        spread_brl = config.round_half_up(str(spread_brl_raw)) if spread_brl_raw is not None else Decimal("0.00")

        spread_pct_raw = ws.cell(row=r, column=col_map["spread_pct"]).value if "spread_pct" in col_map else None
        spread_aplicado_pct = _converter_percentual(spread_pct_raw)

        status = str(
            ws.cell(row=r, column=col_map["status"]).value or "APROVADO"
        ).strip() if "status" in col_map else "APROVADO"

        observacao = str(
            ws.cell(row=r, column=col_map["observacao"]).value or ""
        ).strip() if "observacao" in col_map else ""

        # Verificação de duplicidade por Nº Operação (ex: PC-0926-0162)
        ocorrencias = operacoes_vistas.get(ref_origem, 0)
        operacoes_vistas[ref_origem] = ocorrencias + 1
        is_duplicada = ocorrencias >= 1

        # Verificação de spread negativo (ex: PC-0926-0210, -0326, -0491, -0545)
        is_spread_negativo = (spread_brl < Decimal("0.00")) or (spread_aplicado_pct < Decimal("0.00"))

        # Operação válida para comissão (exclui duplicatas e spreads negativos)
        is_valida_comissao = not is_duplicada and not is_spread_negativo

        # Comissão devida à Tarvo (50% do Spread R$)
        comissao_tarvo_brl = (
            config.round_half_up(spread_brl * config.PARTICIPACAO_TARVO_SPREAD)
            if is_valida_comissao
            else Decimal("0.00")
        )

        # Apuração de divergência de taxas (tolerância de 0.01 p.p.)
        diferenca_pct = spread_aplicado_pct - spread_contratado_pct
        is_divergente_taxa = (
            not is_duplicada
            and not is_spread_negativo
            and abs(diferenca_pct) > config.TOLERANCIA_TAXA_PP
        )

        if is_spread_negativo:
            diferenca_brl = spread_brl
        elif is_divergente_taxa:
            diferenca_brl = config.round_half_up(valor_brl * diferenca_pct / Decimal("100"))
        else:
            diferenca_brl = Decimal("0.00")

        op_dict: Dict[str, Any] = {
            # Identificadores de referência e rastreabilidade
            "ref_origem": ref_origem,
            "num_operacao": ref_origem,
            "arquivo_origem": arquivo_origem,
            "linha_planilha": r,
            "linha_negocio": config.LINHA_REMESSA,
            # Dados cadastrais e temporais
            "data": data_efetiva,
            "data_contratacao": data_contratacao,
            "data_liquidacao": data_liquidacao,
            "cnpj": cnpj,
            "lojista": lojista,
            "cliente": cliente_planilha or lojista,
            # Dados cambiais e financeiros
            "moeda": moeda,
            "valor_moeda": valor_moeda,
            "taxa_cambio": taxa_cambio,
            "taxa_ptax": taxa_ptax,
            "valor_brl": valor_brl,
            "valor_operacao_brl": valor_brl,
            "spread_brl": spread_brl,
            "spread_pct": spread_aplicado_pct,
            "taxa_aplicada_pct": spread_aplicado_pct,
            "spread_contratado_pct": spread_contratado_pct,
            "taxa_contratada_pct": spread_contratado_pct,
            "comissao_tarvo_brl": comissao_tarvo_brl,
            "diferenca_pct": diferenca_pct,
            "diferenca_brl": diferenca_brl,
            # Flags de controle e auditoria
            "status": status,
            "observacao": observacao,
            "is_duplicada": is_duplicada,
            "is_spread_negativo": is_spread_negativo,
            "is_valida_comissao": is_valida_comissao,
            "is_divergente_taxa": is_divergente_taxa,
        }

        operacoes.append(op_dict)
        if is_duplicada:
            operacoes_duplicadas.append(op_dict)
        elif is_spread_negativo:
            operacoes_spread_negativo.append(op_dict)
        else:
            if is_valida_comissao:
                operacoes_validas.append(op_dict)
            if is_divergente_taxa:
                operacoes_divergentes.append(op_dict)

    # Coleta a aba 'Resumo' se presente (apenas para metadados/auditoria)
    resumo_linhas: List[List[Any]] = []
    if nome_aba_resumo and nome_aba_resumo in wb.sheetnames:
        ws_res = wb[nome_aba_resumo]
        for row_vals in ws_res.iter_rows(values_only=True):
            if any(v is not None for v in row_vals):
                resumo_linhas.append(list(row_vals))

    return {
        "operacoes": operacoes,
        "operacoes_validas": operacoes_validas,
        "operacoes_duplicadas": operacoes_duplicadas,
        "operacoes_spread_negativo": operacoes_spread_negativo,
        "operacoes_divergentes": operacoes_divergentes,
        "resumo_aba": resumo_linhas,
    }


# ============================================================================
# 6. PONTO DE ENTRADA PRINCIPAL: parse_ponte_e_taxas
# ============================================================================
def parse_ponte_e_taxas(
    data_dir_ou_eml: Union[str, Path, None] = None,
    caminho_taxas: Union[str, Path, None] = None,
) -> Dict[str, Any]:
    """Extrai e normaliza o borderô da Ponte Câmbio e os spreads contratuais.

    Contrato com o projeto:
        Chamado pelo main.py via ``parse_ponte.parse_ponte_e_taxas(data_dir)``.

    Args:
        data_dir_ou_eml: Diretório onde estão os arquivos brutos (ou caminho do .eml).
        caminho_taxas: Caminho opcional para a tabela de taxas contratadas.

    Returns:
        Dicionário estruturado com:
            - 'operacoes': Todas as operações de remessa normalizadas.
            - 'operacoes_validas': Operações válidas para cálculo de comissão.
            - 'operacoes_duplicadas': Operações duplicadas detectadas (PC-0926-0162).
            - 'operacoes_spread_negativo': Operações com spread negativo (trava D-1).
            - 'operacoes_divergentes': Operações com divergência de taxas (ex: Mundo Aberto).
            - 'spreads_contrato': Mapa {cnpj: SpreadContratado}.
            - 'spreads_contratados': Alias para 'spreads_contrato'.
            - 'cadastro_por_cnpj': Cadastro dos lojistas da tabela de taxas.
            - 'arquivo_origem': Nome do arquivo .eml de origem.
            - 'caminho_email': Path completo do arquivo .eml.
            - 'nome_anexo_xlsx': Nome do anexo Excel extraído do .eml.
            - 'email_metadata': Metadados do e-mail recebido.
            - 'resumo_aba': Linhas da aba Resumo (para auditoria).
    """
    if data_dir_ou_eml is None:
        pasta_dados = config.resolver_data_dir()
        caminho_eml = config.localizar_arquivo(pasta_dados, "ponte_email")
    else:
        alvo = Path(data_dir_ou_eml)
        if alvo.is_dir():
            pasta_dados = alvo
            caminho_eml = config.localizar_arquivo(pasta_dados, "ponte_email")
        elif alvo.is_file():
            caminho_eml = alvo
            pasta_dados = alvo.parent
        else:
            raise FileNotFoundError(f"Caminho inválido para Ponte Câmbio: {alvo}")

    if caminho_taxas is None:
        caminho_taxas_arq = config.localizar_arquivo(pasta_dados, "taxas")
    else:
        caminho_taxas_arq = Path(caminho_taxas)

    # 1. Carrega os spreads contratados da aba 'Taxas vigentes'
    spreads_por_cnpj, spreads_por_nome, cadastro_por_cnpj = carregar_spreads_contratados(
        caminho_taxas_arq
    )

    # 2. Extrai o anexo .xlsx diretamente do .eml
    dados_eml = extrair_anexo_xlsx_de_eml(caminho_eml)

    # 3. Lê e classifica todas as operações da planilha
    dados_planilha = _ler_planilha_operacoes(
        xlsx_bytes=dados_eml["xlsx_bytes"],
        spreads_por_cnpj=spreads_por_cnpj,
        spreads_por_nome=spreads_por_nome,
        arquivo_origem=caminho_eml.name,
    )

    return {
        "operacoes": dados_planilha["operacoes"],
        "operacoes_validas": dados_planilha["operacoes_validas"],
        "operacoes_duplicadas": dados_planilha["operacoes_duplicadas"],
        "operacoes_spread_negativo": dados_planilha["operacoes_spread_negativo"],
        "operacoes_divergentes": dados_planilha["operacoes_divergentes"],
        "spreads_contrato": spreads_por_cnpj,
        "spreads_contratados": spreads_por_cnpj,
        "spreads_por_nome": spreads_por_nome,
        "cadastro_por_cnpj": cadastro_por_cnpj,
        "arquivo_origem": caminho_eml.name,
        "caminho_email": caminho_eml,
        "nome_anexo_xlsx": dados_eml["nome_anexo"],
        "email_metadata": dados_eml["email_metadata"],
        "resumo_aba": dados_planilha["resumo_aba"],
    }


# Aliases para compatibilidade total
parse_ponte = parse_ponte_e_taxas
carregar_ponte = parse_ponte_e_taxas
ler_ponte = parse_ponte_e_taxas


# ============================================================================
# 7. EXECUÇÃO STANDALONE PARA INSPEÇÃO E DEBUG
# ============================================================================
if __name__ == "__main__":
    import sys

    pasta = sys.argv[1] if len(sys.argv) > 1 else None
    print("=" * 70)
    print(" EXECUTANDO PARSER DA PONTE CÂMBIO (REMESSAS)")
    print("=" * 70)
    try:
        resultado = parse_ponte_e_taxas(pasta)
        ops = resultado["operacoes"]
        validas = resultado["operacoes_validas"]
        dups = resultado["operacoes_duplicadas"]
        negs = resultado["operacoes_spread_negativo"]
        divs = resultado["operacoes_divergentes"]
        comissao_total = sum(op["comissao_tarvo_brl"] for op in validas)

        print(f"Arquivo E-mail de origem : {resultado['arquivo_origem']}")
        print(f"Anexo Excel extraído     : {resultado['nome_anexo_xlsx']}")
        print(f"Total de operações lidas : {len(ops)}")
        print(f"Operações válidas (com.) : {len(validas)}")
        print(f"Operações duplicadas     : {len(dups)} (ex: {[d['ref_origem'] for d in dups]})")
        print(f"Spreads negativos        : {len(negs)} (ex: {[n['ref_origem'] for n in negs]})")
        print(f"Divergências de taxa     : {len(divs)} (ex: Mundo Aberto)")
        print(f"Comissão Tarvo calculada : R$ {comissao_total:,.2f}")
        print("=" * 70)
        print("Execução standalone concluída com sucesso.")
    except Exception as exc:
        print(f"Erro ao executar parse_ponte_e_taxas: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
