"""
Módulo de faturamento e geração de Notas Fiscais de Serviços - NFS-e (Missão 3).

Responsabilidades:
1. Checkout: Emitir uma nota fiscal individual para cada lojista ativo cujo saldo
   líquido de comissão de checkout seja estritamente positivo (`> R$ 0.00`).
   - Lojistas com comissão zero (ex: Casa do Estudante, taxa 0.00%) ou negativa não emitem nota.
   - Estabelecimentos sem contrato assinado em 2026 (ex: Atlas Idiomas) são bloqueados.
2. Remessas: Emitir exatamente UMA ÚNICA NOTA FISCAL consolidada contra a parceira
   Ponte Câmbio S.A. (CNPJ `75374179000146`) pelo somatório das comissões válidas de
   remessa do mês.
3. Rastreabilidade (`rastro.csv`): Amarrar cada `id_saida` (`NF-xxxx`) às transações
   da Orbe ou operações da Ponte Câmbio que compõem o valor faturado, garantindo que
   a soma no rastro feche centavo a centavo com `valor_brl`.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import re
import unicodedata
from typing import Any

try:
    from src import config as _config
except ImportError:
    try:
        import config as _config  # type: ignore[import-not-found]
    except ImportError:
        _config = None


# ============================================================================
# 1. CONSTANTES E UTILITÁRIOS DE DOMÍNIO (INTEGRADOS COM src/config.py)
# ============================================================================
def _fallback_para_decimal(val: Any, default: Decimal = Decimal("0.00")) -> Decimal:
    if val is None:
        return default
    if isinstance(val, Decimal):
        return val
    if isinstance(val, (int, bool)):
        return Decimal(int(val))
    if isinstance(val, float):
        return Decimal(str(val))
    texto = str(val).strip()
    if not texto:
        return default
    texto = re.sub(r"[R$\s%]", "", texto)
    if "," in texto and "." in texto:
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        return Decimal(texto)
    except Exception:
        return default


def _fallback_round_half_up(val: Any, casas: str = "0.01") -> Decimal:
    return _fallback_para_decimal(val).quantize(Decimal(casas), rounding=ROUND_HALF_UP)


def _fallback_clean_cnpj(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, float):
        val = int(val)
    digitos = re.sub(r"\D", "", str(val).strip())
    if not digitos:
        return ""
    return digitos.zfill(14)[:14]


para_decimal = getattr(_config, "para_decimal", _fallback_para_decimal)
round_half_up = getattr(_config, "round_half_up", _fallback_round_half_up)
clean_cnpj = getattr(_config, "clean_cnpj", _fallback_clean_cnpj)

PREFIXO_NOTA: str = getattr(_config, "PREFIXO_NOTA", "NF")
LINHA_CHECKOUT: str = getattr(_config, "LINHA_CHECKOUT", "CHECKOUT")
LINHA_REMESSA: str = getattr(_config, "LINHA_REMESSA", "REMESSA")

PONTE_CAMBIO_CNPJ: str = clean_cnpj(
    getattr(_config, "PONTE_CAMBIO_CNPJ", "75374179000146")
)
PONTE_CAMBIO_NOME: str = str(
    getattr(
        _config,
        "PONTE_CAMBIO_NOME",
        getattr(_config, "PONTE_CAMBIO_TOMADOR", "Ponte Câmbio S.A."),
    )
)

EC_ATLAS_IDIOMAS: str = str(
    getattr(_config, "EC_ATLAS_IDIOMAS", getattr(_config, "EC_SEM_CONTRATO", "1076801732"))
)
EC_CASA_DO_ESTUDANTE: str = str(
    getattr(_config, "EC_CASA_DO_ESTUDANTE", getattr(_config, "EC_TAXA_ZERO", "1018325654"))
)

DISCRIMINACAO_CHECKOUT_PADRAO: str = str(
    getattr(
        _config,
        "DISCRIMINACAO_NOTA_CHECKOUT",
        "Serviços de intermediação e agenciamento - Checkout competência 09/2026",
    )
)
DISCRIMINACAO_REMESSA_PADRAO: str = str(
    getattr(
        _config,
        "DISCRIMINACAO_NOTA_REMESSA",
        "Serviços de intermediação e agenciamento de remessas internacionais competência 09/2026",
    )
)


def _normalizar_texto(texto: Any) -> str:
    if texto is None:
        return ""
    sem_acento = "".join(
        c
        for c in unicodedata.normalize("NFKD", str(texto).strip())
        if not unicodedata.combining(c)
    )
    return sem_acento.lower()


def _inferir_competencia(
    dados_checkout: dict[str, Any] | None,
    dados_remessas: dict[str, Any] | None,
) -> str:
    """
    Infere dinamicamente o mês/ano de competência (ex: '09/2026' ou '10/2026')
    a partir das datas das transações/operações para suportar execução em outros meses.
    """
    datas: list[str] = []
    if dados_checkout:
        for tx in dados_checkout.get("transacoes") or []:
            d = str(tx.get("data_movimento") or "").strip()
            if len(d) >= 7 and d[4] == "-":
                datas.append(d[:7])
                break
    if not datas and dados_remessas:
        for op in dados_remessas.get("operacoes_validas") or dados_remessas.get("operacoes") or []:
            d = str(op.get("data") or op.get("data_operacao") or "").strip()
            if len(d) >= 7 and d[4] == "-":
                datas.append(d[:7])
                break

    if datas:
        ano, mes = datas[0].split("-")
        return f"{mes}/{ano}"
    return "09/2026"


# ============================================================================
# 2. MAPEAMENTO DE TRANSAÇÕES E OPERAÇÕES PARA O RASTRO DAS NOTAS
# ============================================================================
def _mapear_rastro_checkout_por_cnpj(
    dados_checkout: dict[str, Any] | None,
) -> tuple[dict[str, list[tuple[str, str, Decimal]]], dict[str, str]]:
    """
    Reconstrói a lista de contribuições individuais `(arquivo_origem, id_transacao, comissao_linha)`
    de cada lojista (indexado por CNPJ de 14 dígitos) aplicando exatamente a regra de
    cálculo de comissão de Checkout (`round_half_up(valor_bruto * taxa_contratada_pct / 100)`).

    Retorna:
        (rastro_por_cnpj, nome_lojista_por_cnpj)
    """
    rastro_por_cnpj: dict[str, list[tuple[str, str, Decimal]]] = {}
    nomes_por_cnpj: dict[str, str] = {}

    if not dados_checkout:
        return rastro_por_cnpj, nomes_por_cnpj

    transacoes: list[dict[str, Any]] = list(dados_checkout.get("transacoes") or [])
    arquivo_padrao = str(
        dados_checkout.get("arquivo_origem")
        or "01_orbe_relatorio_comissoes_set2026.csv"
    )

    for tx in transacoes:
        ec = str(tx.get("cod_estabelecimento") or "").strip()
        nome_lojista = str(
            tx.get("lojista") or tx.get("nome_estabelecimento") or ""
        ).strip()

        # Bloqueia estabelecimentos sem contrato (Atlas Idiomas) e taxa zero (Casa do Estudante)
        if (
            bool(tx.get("sem_contrato", False))
            or ec == EC_ATLAS_IDIOMAS
            or "atlas idiomas" in _normalizar_texto(nome_lojista)
        ):
            continue

        taxa_ct_raw = tx.get("taxa_contratada_pct")
        if taxa_ct_raw is None:
            continue

        cnpj = clean_cnpj(tx.get("cnpj"))
        if not cnpj:
            continue

        taxa_contratada_pct = para_decimal(taxa_ct_raw)
        valor_bruto = para_decimal(tx.get("valor_bruto", Decimal("0.00")))

        # Se a transação já trouxer a comissão calculada pelo parser/engine, usa-a;
        # caso contrário, calcula linha a linha pela taxa contratada com round_half_up.
        if "comissao_contratada_brl" in tx and tx["comissao_contratada_brl"] is not None:
            comissao_linha = round_half_up(tx["comissao_contratada_brl"])
        else:
            comissao_linha = round_half_up(
                valor_bruto * taxa_contratada_pct / Decimal("100")
            )

        id_tx = str(tx.get("id_transacao") or tx.get("ref_origem") or "").strip()
        arq_tx = str(tx.get("arquivo_origem") or arquivo_padrao).strip()

        rastro_por_cnpj.setdefault(cnpj, []).append((arq_tx, id_tx, comissao_linha))
        if nome_lojista and cnpj not in nomes_por_cnpj:
            nomes_por_cnpj[cnpj] = nome_lojista

    return rastro_por_cnpj, nomes_por_cnpj


def _mapear_rastro_remessas(
    dados_remessas: dict[str, Any] | None,
) -> list[tuple[str, str, Decimal]]:
    """
    Extrai a lista de contribuições individuais `(arquivo_origem, ref_origem, comissao_op)`
    de todas as operações válidas de remessa (50% do `Spread R$` com `round_half_up`,
    excluindo a duplicata `PC-0926-0162` e os 4 spreads negativos).
    """
    itens_rastro: list[tuple[str, str, Decimal]] = []
    if not dados_remessas:
        return itens_rastro

    arquivo_ponte = str(
        dados_remessas.get("arquivo_origem")
        or "03_email_ponte_cambio_relatorio_set2026.eml"
    )

    ops_validas: list[dict[str, Any]] = list(
        dados_remessas.get("operacoes_validas") or []
    )
    if not ops_validas:
        # Fallback caso apenas `operacoes` esteja presente no dicionário
        todas_ops: list[dict[str, Any]] = list(dados_remessas.get("operacoes") or [])
        vistas: set[str] = set()
        for op in todas_ops:
            ref = str(op.get("ref_origem") or op.get("num_operacao") or "").strip()
            if not ref or ref in vistas or bool(op.get("is_duplicada", False)):
                continue
            vistas.add(ref)

            spread_brl = round_half_up(op.get("spread_brl", op.get("spread_rs", 0)))
            spread_pct = para_decimal(
                op.get("spread_pct", op.get("taxa_aplicada_pct", 0))
            )
            if (
                bool(op.get("is_spread_negativo", False))
                or spread_brl < Decimal("0.00")
                or spread_pct < Decimal("0.00")
            ):
                continue
            ops_validas.append(op)

    for op in ops_validas:
        ref_op = str(op.get("ref_origem") or op.get("num_operacao") or "").strip()
        arq_op = str(op.get("arquivo_origem") or arquivo_ponte).strip()

        if "comissao_tarvo_brl" in op and op["comissao_tarvo_brl"] is not None:
            comissao_op = round_half_up(op["comissao_tarvo_brl"])
        elif "comissao_brl" in op and op["comissao_brl"] is not None:
            comissao_op = round_half_up(op["comissao_brl"])
        else:
            spread_brl = para_decimal(op.get("spread_brl", op.get("spread_rs", 0)))
            comissao_op = round_half_up(spread_brl * Decimal("0.50"))

        if comissao_op != Decimal("0.00"):
            itens_rastro.append((arq_op, ref_op, comissao_op))

    return itens_rastro


def _obter_rastro_existente_no_tracker(
    tracker: Any,
    id_comissao: str,
) -> list[tuple[str, str, Decimal]]:
    """
    Se o `tracker` já possui os apontamentos registrados para um `id_saida` de comissão
    (`COM-xxxx`), recupera essas mesmas linhas de origem para espelhar na nota fiscal
    (`NF-xxxx`), garantindo consistência 100% entre `comissoes_por_lojista.csv` e `notas_a_emitir.csv`.
    """
    if tracker is None or not id_comissao:
        return []

    try:
        linhas_tracker = tracker.linhas() if callable(getattr(tracker, "linhas", None)) else []
        encontradas: list[tuple[str, str, Decimal]] = []
        for item in linhas_tracker:
            if str(item.get("id_saida") or "") == id_comissao:
                encontradas.append(
                    (
                        str(item.get("arquivo_origem") or ""),
                        str(item.get("ref_origem") or ""),
                        round_half_up(item.get("valor", Decimal("0.00"))),
                    )
                )
        return encontradas
    except Exception:
        return []


# ============================================================================
# 3. EMISSORES DE NOTAS DE CHECKOUT E REMESSA
# ============================================================================
def _gerar_notas_checkout(
    comissoes: list[dict[str, Any]] | None,
    dados_checkout: dict[str, Any] | None,
    tracker: Any,
    competencia: str,
) -> list[dict[str, Any]]:
    """
    Gera uma NFS-e para cada lojista ativo de Checkout com comissão líquida > R$ 0.00.
    """
    rastro_por_cnpj, nomes_por_cnpj = _mapear_rastro_checkout_por_cnpj(dados_checkout)

    discriminacao_base = DISCRIMINACAO_CHECKOUT_PADRAO
    if "09/2026" in discriminacao_base and competencia != "09/2026":
        discriminacao_base = discriminacao_base.replace("09/2026", competencia)

    # Coleta as linhas de comissão de CHECKOUT já apuradas em `comissoes.py`
    comissoes_checkout: list[dict[str, Any]] = [
        c
        for c in (comissoes or [])
        if str(c.get("linha_negocio") or "").strip().upper() == LINHA_CHECKOUT
    ]

    # Se `comissoes` não foi fornecido (ex: teste isolado), reconstrói a partir do rastro_por_cnpj
    if not comissoes_checkout and rastro_por_cnpj:
        for cnpj, itens in sorted(rastro_por_cnpj.items()):
            soma_cnpj = sum((val for _, _, val in itens), Decimal("0.00"))
            comissoes_checkout.append(
                {
                    "id_saida": "",
                    "cnpj": cnpj,
                    "lojista": nomes_por_cnpj.get(cnpj, ""),
                    "linha_negocio": LINHA_CHECKOUT,
                    "comissao_brl": soma_cnpj,
                }
            )

    notas_checkout: list[dict[str, Any]] = []

    for com in comissoes_checkout:
        cnpj = clean_cnpj(com.get("cnpj") or com.get("tomador_cnpj"))
        lojista = str(
            com.get("lojista") or com.get("tomador") or nomes_por_cnpj.get(cnpj, "")
        ).strip()
        valor_comissao = round_half_up(
            com.get("comissao_brl", com.get("valor_brl", Decimal("0.00")))
        )

        # Regra 1 & 2: Somente lojistas com comissão estritamente > 0.00 e contrato ativo
        if valor_comissao <= Decimal("0.00"):
            continue
        if not cnpj or "atlas idiomas" in _normalizar_texto(lojista):
            continue

        id_com_origem = str(com.get("id_saida") or "").strip()
        itens_rastro = _obter_rastro_existente_no_tracker(tracker, id_com_origem)
        if not itens_rastro:
            itens_rastro = rastro_por_cnpj.get(cnpj, [])

        # Se houver itens no rastro, garante que o valor da nota bata exatamente com a soma
        if itens_rastro:
            soma_rastro = sum((val for _, _, val in itens_rastro), Decimal("0.00"))
            if soma_rastro > Decimal("0.00"):
                valor_comissao = round_half_up(soma_rastro)

        id_nota = (
            tracker.novo_id(PREFIXO_NOTA)
            if tracker is not None and hasattr(tracker, "novo_id")
            else f"{PREFIXO_NOTA}-0000"
        )

        if tracker is not None and hasattr(tracker, "registrar"):
            for arq_origem, ref_origem, val_item in itens_rastro:
                tracker.registrar(
                    id_nota,
                    arq_origem,
                    ref_origem,
                    round_half_up(val_item),
                )

        notas_checkout.append(
            {
                "id_saida": id_nota,
                "tomador_cnpj": cnpj,
                "tomador": lojista,
                "linha_negocio": LINHA_CHECKOUT,
                "valor_brl": valor_comissao,
                "discriminacao": discriminacao_base,
            }
        )

    return notas_checkout


def _gerar_nota_unica_remessa(
    comissoes: list[dict[str, Any]] | None,
    dados_remessas: dict[str, Any] | None,
    tracker: Any,
    competencia: str,
) -> list[dict[str, Any]]:
    """
    Gera exatamente UMA ÚNICA NFS-e contra a Ponte Câmbio S.A. (`75374179000146`)
    consolidando todas as comissões válidas de remessa do mês.
    """
    discriminacao_remessa = DISCRIMINACAO_REMESSA_PADRAO
    if "09/2026" in discriminacao_remessa and competencia != "09/2026":
        discriminacao_remessa = discriminacao_remessa.replace("09/2026", competencia)

    comissoes_remessa: list[dict[str, Any]] = [
        c
        for c in (comissoes or [])
        if str(c.get("linha_negocio") or "").strip().upper() == LINHA_REMESSA
    ]

    # 1. Tenta obter os itens de rastro já registrados pelas linhas de comissão de remessa
    itens_rastro_remessa: list[tuple[str, str, Decimal]] = []
    for com in comissoes_remessa:
        id_com = str(com.get("id_saida") or "").strip()
        if id_com:
            itens_rastro_remessa.extend(
                _obter_rastro_existente_no_tracker(tracker, id_com)
            )

    # 2. Caso o tracker não exponha leitura ou `comissoes` não tenha sido passado,
    #    mapeia diretamente das 228 operações válidas de `dados_remessas`
    if not itens_rastro_remessa:
        itens_rastro_remessa = _mapear_rastro_remessas(dados_remessas)

    if itens_rastro_remessa:
        valor_total_remessa = round_half_up(
            sum((val for _, _, val in itens_rastro_remessa), Decimal("0.00"))
        )
    else:
        valor_total_remessa = round_half_up(
            sum(
                (
                    round_half_up(c.get("comissao_brl", c.get("valor_brl", Decimal("0.00"))))
                    for c in comissoes_remessa
                ),
                Decimal("0.00"),
            )
        )

    if valor_total_remessa <= Decimal("0.00"):
        return []

    id_nota_remessa = (
        tracker.novo_id(PREFIXO_NOTA)
        if tracker is not None and hasattr(tracker, "novo_id")
        else f"{PREFIXO_NOTA}-0000"
    )

    if tracker is not None and hasattr(tracker, "registrar"):
        for arq_origem, ref_origem, val_item in itens_rastro_remessa:
            tracker.registrar(
                id_nota_remessa,
                arq_origem,
                ref_origem,
                round_half_up(val_item),
            )

    return [
        {
            "id_saida": id_nota_remessa,
            "tomador_cnpj": PONTE_CAMBIO_CNPJ,
            "tomador": PONTE_CAMBIO_NOME,
            "linha_negocio": LINHA_REMESSA,
            "valor_brl": valor_total_remessa,
            "discriminacao": discriminacao_remessa,
        }
    ]


# ============================================================================
# 4. PONTO DE ENTRADA PRINCIPAL (gerar_notas_a_emitir)
# ============================================================================
def gerar_notas_a_emitir(
    comissoes: list[dict[str, Any]] | None = None,
    dados_checkout: dict[str, Any] | None = None,
    dados_remessas: dict[str, Any] | None = None,
    tracker: Any = None,
) -> list[dict[str, Any]]:
    """
    Gera a lista formal de Notas Fiscais de Serviços (NFS-e) a emitir pela Tarvo
    para as linhas de negócio de Checkout e Remessas Internacionais.

    Parâmetros:
        comissoes: Lista de linhas geradas por `comissoes.calcular_comissoes`.
        dados_checkout: Dicionário retornado por `parse_orbe.parse_orbe_e_taxas`.
        dados_remessas: Dicionário retornado por `parse_ponte.parse_ponte_e_taxas`.
        tracker: Instância ativa de `RastroTracker` para geração de `id_saida` (`NF-xxxx`)
                 e registro de rastreabilidade em `rastro.csv`.

    Retorna:
        Lista de dicionários prontos para gravação em `saida/notas_a_emitir.csv`:
        `id_saida;tomador_cnpj;tomador;linha_negocio;valor_brl;discriminacao`.
    """
    competencia = _inferir_competencia(dados_checkout, dados_remessas)
    notas: list[dict[str, Any]] = []

    # 1. Notas fiscais de Checkout (1 NFS-e por lojista com comissão líquida > R$ 0.00)
    notas.extend(
        _gerar_notas_checkout(
            comissoes=comissoes,
            dados_checkout=dados_checkout,
            tracker=tracker,
            competencia=competencia,
        )
    )

    # 2. Nota fiscal única de Remessas contra a Ponte Câmbio S.A. (CNPJ 75374179000146)
    notas.extend(
        _gerar_nota_unica_remessa(
            comissoes=comissoes,
            dados_remessas=dados_remessas,
            tracker=tracker,
            competencia=competencia,
        )
    )

    return notas


# Aliases de compatibilidade
emitir_notas = gerar_notas_a_emitir
calcular_notas = gerar_notas_a_emitir
gerar_notas = gerar_notas_a_emitir