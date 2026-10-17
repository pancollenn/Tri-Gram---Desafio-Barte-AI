"""Configuração central do pipeline de fechamento da Tarvo Pagamentos.

Este módulo é COMPARTILHADO: concentra caminhos, contratos dos 6 arquivos de
saída, utilitários financeiros (arredondamento, formatação, CNPJ) e as regras
de domínio confirmadas pelo financeiro da Tarvo (Helena, via Slack).

Regra de convivência: alterações aqui devem ser pequenas, aditivas e avisadas
ao time, pois todos os módulos dependem deste arquivo.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, NamedTuple, Optional, Tuple, Union

# ---------------------------------------------------------------------------
# Tipos compartilhados
# ---------------------------------------------------------------------------
Numero = Union[Decimal, int, float, str]
"""Qualquer valor numérico aceito pelos utilitários (preferir ``Decimal``)."""

Linha = Dict[str, Any]
"""Uma linha de saída: dicionário cujas chaves são as colunas do CSV de destino."""


class ResultadoLinhaNegocio(NamedTuple):
    """Retorno de ``processar_checkout`` e ``processar_remessas``.

    Cada campo é uma lista de ``Linha`` com as chaves exatas dos cabeçalhos
    definidos em ``ARQUIVOS_SAIDA`` (colunas extras são ignoradas na gravação).
    """

    comissoes: List[Linha]  # -> comissoes_por_lojista.csv
    divergencias: List[Linha]  # -> divergencias_taxa.csv
    notas: List[Linha]  # -> notas_a_emitir.csv
    pendencias: List[Linha]  # -> pendencias.csv


class ResultadoBancos(NamedTuple):
    """Retorno de ``processar_bancos``."""

    lancamentos: List[Linha]  # -> lancamentos_classificados.csv
    pendencias: List[Linha]  # -> pendencias.csv


# ---------------------------------------------------------------------------
# Caminhos (entrada configurável por argumento/variável de ambiente)
# ---------------------------------------------------------------------------
RAIZ_REPO: Path = Path(__file__).resolve().parent.parent

ENV_DATA_DIR = "TARVO_DATA_DIR"
ENV_SAIDA_DIR = "TARVO_SAIDA_DIR"

SAIDA_DIR_PADRAO: Path = RAIZ_REPO / "saida"

# Ordem de busca do diretório de entrada quando nada é informado.
CANDIDATOS_DATA_DIR: Tuple[Path, ...] = (
    RAIZ_REPO / "data",
    RAIZ_REPO / "Tarvo_Data_Pack_set2026",
    RAIZ_REPO.parent / "Tarvo_Data_Pack_set2026",
)


def resolver_data_dir(valor_cli: Optional[Union[str, Path]] = None) -> Path:
    """Resolve o diretório com os arquivos brutos.

    Precedência: argumento (``--data-dir``) > variável ``TARVO_DATA_DIR`` >
    primeiro diretório existente em ``CANDIDATOS_DATA_DIR``.

    Raises:
        FileNotFoundError: se nenhum diretório válido for encontrado.
    """
    explicito = valor_cli or os.environ.get(ENV_DATA_DIR)
    if explicito:
        caminho = Path(explicito).expanduser().resolve()
        if not caminho.is_dir():
            raise FileNotFoundError(f"Diretório de entrada não encontrado: {caminho}")
        return caminho
    for candidato in CANDIDATOS_DATA_DIR:
        if candidato.is_dir():
            return candidato.resolve()
    tentados = "\n  - ".join(str(c) for c in CANDIDATOS_DATA_DIR)
    raise FileNotFoundError(
        "Diretório de entrada não encontrado. Use --data-dir, a variável "
        f"{ENV_DATA_DIR} ou coloque os arquivos em uma destas pastas:\n  - {tentados}"
    )


def resolver_saida_dir(valor_cli: Optional[Union[str, Path]] = None) -> Path:
    """Resolve (e cria, se preciso) o diretório de saída (padrão: ``saida/``)."""
    explicito = valor_cli or os.environ.get(ENV_SAIDA_DIR)
    caminho = Path(explicito).expanduser().resolve() if explicito else SAIDA_DIR_PADRAO
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho


# Padrões (glob) dos arquivos de entrada. Usar glob e não o nome literal para
# que a solução rode em outubro com arquivos "novos no mesmo formato"
# (ex.: ``..._out2026.csv``) sem alterar código.
PADROES_ENTRADA: Dict[str, str] = {
    "orbe": "01_orbe_relatorio_comissoes_*.csv",
    "taxas": "02_tabela_taxas_contratadas*.xlsx",
    "ponte_email": "03_email_ponte_cambio_relatorio_*.eml",
    "plano_contas": "04_plano_de_contas_fenix_erp*.csv",
    "aurora": "05a_extrato_banco_aurora_*.csv",
    "meridiano": "05b_extrato_banco_meridiano_*.ofx",
}


def localizar_arquivo(data_dir: Union[str, Path], chave: str) -> Path:
    """Localiza o arquivo de entrada identificado por ``chave`` em ``PADROES_ENTRADA``.

    Raises:
        FileNotFoundError: nenhum arquivo casa com o padrão.
        RuntimeError: mais de um arquivo casa (ambiguidade; nunca escolher no chute).
    """
    padrao = PADROES_ENTRADA[chave]
    achados = sorted(Path(data_dir).glob(padrao))
    if not achados:
        raise FileNotFoundError(f"Nenhum arquivo '{padrao}' em {data_dir}")
    if len(achados) > 1:
        nomes = ", ".join(a.name for a in achados)
        raise RuntimeError(f"Mais de um arquivo casa com '{padrao}': {nomes}")
    return achados[0]


# ---------------------------------------------------------------------------
# Contrato dos 6 arquivos de saída (nomes e cabeçalhos EXATOS do edital)
# ---------------------------------------------------------------------------
SEPARADOR_CSV = ";"
ENCODING_CSV = "utf-8"

ARQ_COMISSOES = "comissoes_por_lojista.csv"
ARQ_DIVERGENCIAS = "divergencias_taxa.csv"
ARQ_NOTAS = "notas_a_emitir.csv"
ARQ_LANCAMENTOS = "lancamentos_classificados.csv"
ARQ_PENDENCIAS = "pendencias.csv"
ARQ_RASTRO = "rastro.csv"


@dataclass(frozen=True)
class ArquivoSaida:
    """Especificação de um CSV de saída.

    Os conjuntos abaixo dizem ao ``main.py`` como serializar cada coluna.
    """

    nome: str
    colunas: Tuple[str, ...]
    monetarias: FrozenSet[str] = frozenset()  # exatamente 2 casas, ponto decimal
    percentuais: FrozenSet[str] = frozenset()  # ponto decimal, mínimo 2 casas
    cnpj: FrozenSet[str] = frozenset()  # 14 dígitos
    datas: FrozenSet[str] = frozenset()  # AAAA-MM-DD
    razoes: FrozenSet[str] = frozenset()  # confiança 0..1


ARQUIVOS_SAIDA: Dict[str, ArquivoSaida] = {
    ARQ_COMISSOES: ArquivoSaida(
        nome=ARQ_COMISSOES,
        colunas=("id_saida", "cnpj", "lojista", "linha_negocio", "comissao_brl"),
        monetarias=frozenset({"comissao_brl"}),
        cnpj=frozenset({"cnpj"}),
    ),
    ARQ_DIVERGENCIAS: ArquivoSaida(
        nome=ARQ_DIVERGENCIAS,
        colunas=(
            "id_saida",
            "cnpj",
            "linha_negocio",
            "ref_origem",
            "taxa_contratada_pct",
            "taxa_aplicada_pct",
            "diferenca_brl",
        ),
        monetarias=frozenset({"diferenca_brl"}),
        percentuais=frozenset({"taxa_contratada_pct", "taxa_aplicada_pct"}),
        cnpj=frozenset({"cnpj"}),
    ),
    ARQ_NOTAS: ArquivoSaida(
        nome=ARQ_NOTAS,
        colunas=(
            "id_saida",
            "tomador_cnpj",
            "tomador",
            "linha_negocio",
            "valor_brl",
            "discriminacao",
        ),
        monetarias=frozenset({"valor_brl"}),
        cnpj=frozenset({"tomador_cnpj"}),
    ),
    ARQ_LANCAMENTOS: ArquivoSaida(
        nome=ARQ_LANCAMENTOS,
        colunas=(
            "id_saida",
            "banco",
            "ref_origem",
            "data",
            "descricao",
            "valor",
            "conta_codigo",
            "metodo",
            "confianca",
        ),
        monetarias=frozenset({"valor"}),
        datas=frozenset({"data"}),
        razoes=frozenset({"confianca"}),
    ),
    ARQ_PENDENCIAS: ArquivoSaida(
        nome=ARQ_PENDENCIAS,
        colunas=("id_saida", "tipo", "ref_origem", "valor_brl", "motivo", "quem_decide"),
        monetarias=frozenset({"valor_brl"}),
    ),
    ARQ_RASTRO: ArquivoSaida(
        nome=ARQ_RASTRO,
        colunas=("id_saida", "arquivo_origem", "ref_origem", "valor"),
        monetarias=frozenset({"valor"}),
    ),
}

# Domínios estritos (valores literais exigidos pelo edital)
LINHA_CHECKOUT = "CHECKOUT"
LINHA_REMESSA = "REMESSA"
LINHAS_NEGOCIO: Tuple[str, ...] = (LINHA_CHECKOUT, LINHA_REMESSA)

BANCO_AURORA = "AURORA"
BANCO_MERIDIANO = "MERIDIANO"
BANCOS: Tuple[str, ...] = (BANCO_AURORA, BANCO_MERIDIANO)

METODO_REGRA = "REGRA"
METODO_IA = "IA"
METODO_HUMANO = "HUMANO"
METODOS: Tuple[str, ...] = (METODO_REGRA, METODO_IA, METODO_HUMANO)

# Prefixos de ``id_saida`` (ver ``RastroTracker.novo_id``)
PREFIXO_COMISSAO = "COM"
PREFIXO_DIVERGENCIA = "DIV"
PREFIXO_NOTA = "NF"
PREFIXO_LANCAMENTO = "LAN"
PREFIXO_PENDENCIA = "PEN"

# ---------------------------------------------------------------------------
# Utilitários financeiros e de formatação
# ---------------------------------------------------------------------------
CENTAVO = Decimal("0.01")


def para_decimal(val: Numero) -> Decimal:
    """Converte para ``Decimal`` finito sem passar por imprecisão binária.

    ``float`` é convertido via ``str`` (ex.: ``0.1`` -> ``Decimal('0.1')``).

    Raises:
        TypeError: tipo não suportado (inclui ``bool`` e ``None``).
        ValueError: texto inválido ou valor não finito (NaN/Infinity).
    """
    if isinstance(val, bool) or val is None:
        raise TypeError(f"Valor numérico inválido: {val!r}")
    if isinstance(val, Decimal):
        dec = val
    elif isinstance(val, int):
        dec = Decimal(val)
    elif isinstance(val, float):
        dec = Decimal(str(val))
    elif isinstance(val, str):
        try:
            dec = Decimal(val.strip())
        except InvalidOperation as exc:
            raise ValueError(f"Número inválido: {val!r}") from exc
    else:
        raise TypeError(f"Tipo não suportado para número: {type(val).__name__}")
    if not dec.is_finite():
        raise ValueError(f"Número não finito: {val!r}")
    return dec


def round_half_up(val: Numero) -> Decimal:
    """Arredonda para 2 casas com ``ROUND_HALF_UP`` (``0.005 -> 0.01``).

    Empates se afastam do zero (``-0.005 -> -0.01``), o que mantém simetria
    entre uma venda e o seu estorno: ``round(x)`` e ``round(-x)`` são opostos.
    """
    return para_decimal(val).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def tem_precisao_de_centavos(val: Numero) -> bool:
    """Retorna ``True`` se ``val`` já está exatamente em centavos (<= 2 casas)."""
    dec = para_decimal(val)
    return dec == dec.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def format_brl(val: Numero) -> str:
    """Formata valor monetário com ponto decimal e 2 casas (``1520.50``).

    Nunca produz ``-0.00``.
    """
    dec = round_half_up(val)
    if dec == 0:
        dec = Decimal("0.00")
    return format(dec, "f")


def format_pct(val: Numero) -> str:
    """Formata percentual com ponto decimal e no mínimo 2 casas (``2.59``, ``0.00``)."""
    dec = para_decimal(val)
    if -dec.as_tuple().exponent < 2:  # type: ignore[operator]
        dec = dec.quantize(CENTAVO)
    return format(dec, "f")


def clean_cnpj(cnpj_str: Union[str, int, float]) -> str:
    """Remove pontuação e devolve exatamente 14 dígitos (zeros à esquerda preservados).

    Aceita ``str`` (``'00.520.815/0001-00'``), ``int`` ou ``float`` inteiro
    (planilhas podem entregar o CNPJ como número, perdendo zeros à esquerda).

    Raises:
        ValueError: sem dígitos ou com mais de 14 dígitos.
    """
    if isinstance(cnpj_str, bool) or cnpj_str is None:
        raise ValueError(f"CNPJ inválido: {cnpj_str!r}")
    if isinstance(cnpj_str, float):
        if not cnpj_str.is_integer():
            raise ValueError(f"CNPJ inválido: {cnpj_str!r}")
        cnpj_str = int(cnpj_str)
    digitos = re.sub(r"\D", "", str(cnpj_str))
    if not digitos or len(digitos) > 14:
        raise ValueError(f"CNPJ inválido: {cnpj_str!r}")
    return digitos.zfill(14)


_RE_MILHAR_PONTO = re.compile(r"^-?\d{1,3}(\.\d{3})+$")


def parse_decimal_ptbr(texto: Union[str, Numero]) -> Decimal:
    """Converte número no formato exportado pelos sistemas (pt-BR) para ``Decimal``.

    - ``'1.234,56'`` -> ``1234.56``; ``'2,59'`` -> ``2.59``; ``'R$ -10,00'`` -> ``-10.00``.
    - Sem vírgula: ``'1.234'`` é lido como milhar (pt-BR); ``'1520.50'`` como decimal.
    - Não-strings (``Decimal``, ``int``, ``float``) passam por ``para_decimal``.

    Raises:
        ValueError: texto vazio ou inválido.
    """
    if not isinstance(texto, str):
        return para_decimal(texto)
    limpo = texto.replace("R$", "").replace("\xa0", "").replace(" ", "").strip()
    if not limpo:
        raise ValueError("Número vazio")
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    elif _RE_MILHAR_PONTO.match(limpo):
        limpo = limpo.replace(".", "")
    return para_decimal(limpo)


def parse_data_ptbr(valor: Union[str, date, datetime]) -> str:
    """Converte ``DD/MM/AAAA`` (ou ``date``/``datetime``/ISO) para ``AAAA-MM-DD``.

    Raises:
        ValueError: formato não reconhecido ou data inexistente.
    """
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    texto = str(valor).strip().split(" ")[0].split("T")[0]
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto, formato).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Data em formato não reconhecido: {valor!r}")


# ---------------------------------------------------------------------------
# Regras de domínio CONFIRMADAS com o financeiro (Helena, Slack #tarvo-financeiro)
# ---------------------------------------------------------------------------
# ECs da Orbe que não constam (ou constam com outro nome) na planilha de taxas.
# Valor = lojista a considerar. O casamento é por EC (código), nunca por
# similaridade de nome.
EC_FALTANTES_TABELA: Dict[str, str] = {
    "1043300981": "Novo Horizonte Intercâmbio",
    "1043396662": "Horizonte Viagens e Turismo",
    "1038867654": "Kiwi Experience",
}

# EC sem contrato assinado em 2026: NÃO faturar; isolar em pendencias.csv.
EC_SEM_CONTRATO_2026: Dict[str, str] = {
    "1076801732": "Atlas Idiomas",
}

# Casa do Estudante: tarifa de checkout zerada (setembro a dezembro/2026).
EC_CASA_DO_ESTUDANTE = "1018325654"
TAXA_CONTRATADA_CASA_DO_ESTUDANTE_PCT = Decimal("0.00")

# Regras gerais de apuração
TAXA_ANTECIPACAO_PADRAO_PCT = Decimal("2.10")  # conferir contra a planilha
PARTICIPACAO_TARVO_SPREAD = Decimal("0.50")  # 50% do Spread R$ realizado
SPREAD_PADRAO_PCT = Decimal("1.50")  # célula vazia ou "padrão" na planilha
TOLERANCIA_TAXA_PP = Decimal("0.01")  # pontos percentuais (evita alarme falso)

# Ponte Câmbio S.A.: tomador único das notas de remessa
PONTE_CAMBIO_CNPJ = "75374179000146"
PONTE_CAMBIO_NOME = "Ponte Câmbio S.A."

# Referências de setembro/2026 (usar SOMENTE em conferências, nunca como filtro:
# em outubro os casos serão outros e devem ser detectados pelos dados).
OPERACAO_DUPLICADA_SET2026 = "PC-0926-0162"
SPREADS_NEGATIVOS_SET2026: Tuple[str, ...] = (
    "PC-0926-0210",
    "PC-0926-0326",
    "PC-0926-0491",
    "PC-0926-0545",
)

# Contas do plano de contas Fênix com papel fixo (conferir com 04_plano_de_contas)
CONTA_COMISSOES_A_RECEBER = "1.1.03.002"  # baixa da comissão de câmbio de agosto
CONTA_TRANSITORIA_MUTUO = "1.1.09.001"  # transferências Aurora <-> Meridiano
CONTA_TRANSITORIA_NAO_IDENTIFICADO = "1.1.09.002"  # Pix sem identificação

# Tipos de pendência (coluna ``tipo`` de pendencias.csv)
PEND_SPREAD_NEGATIVO = "SPREAD_NEGATIVO"
PEND_OPERACAO_DUPLICADA = "OPERACAO_DUPLICADA"
PEND_DIVERGENCIA_SPREAD = "DIVERGENCIA_SPREAD_REMESSA"
PEND_DEVOLUCAO_TAXA = "DEVOLUCAO_TAXA_INDEVIDA"
PEND_DIVERGENCIA_TAXA_ADQUIRENTE = "DIVERGENCIA_TAXA_ADQUIRENTE"
PEND_CONTRATO_AUSENTE = "CONTRATO_AUSENTE"
PEND_PIX_NAO_IDENTIFICADO = "PIX_NAO_IDENTIFICADO"
PEND_DEVOLUCAO_PIX = "DEVOLUCAO_PIX"

# Valores sugeridos para ``quem_decide``
QUEM_FINANCEIRO = "Financeiro Tarvo (Helena)"
QUEM_COMERCIAL = "Comercial Tarvo (Diego)"
