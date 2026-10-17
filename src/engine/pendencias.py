"""
Módulo de consolidação de pendências operacionais e comerciais (Missão 5).

Cataloga de forma estruturada todas as anomalias, disputas e exceções que
exigem intervenção e deliberação humana (Financeiro ou Comercial da Tarvo),
garantindo rastreabilidade matemática absoluta no `RastroTracker`.

Catálogo Oficial das 7 Pendências:
1. Spreads Negativos (Ponte Câmbio): 4 operações com trava de 2h expirada
   (`PC-0926-0210`, `PC-0926-0326`, `PC-0926-0491`, `PC-0926-0545`).
2. Operação Repetida (Ponte Câmbio): Retificação da duplicata `PC-0926-0162` (Bagagem Livre).
3. Spread Indevido Mundo Aberto (Ponte Câmbio): Cobrança de ~1.50% vs 1.20% contratado.
4. Ressarcimento Casa do Estudante (Orbe): Devolução de taxas retidas indevidamente (EC `1018325654`).
5. Contrato Atlas Idiomas (Orbe): Regularização de contrato ausente em 2026 (EC `1076801732`).
6. Pix Não Identificado (Banco Aurora): Crédito em `L50` de R$ 7.350,00 sem identificação do remetente.
7. Devolução de Pix Mundo Aberto (Banco Aurora): Estorno/devolução em `L65` de R$ 12.400,00.
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


def _fallback_round_half_up(val: Any) -> Decimal:
    return _fallback_para_decimal(val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


para_decimal = getattr(_config, "para_decimal", _fallback_para_decimal)
round_half_up = getattr(_config, "round_half_up", _fallback_round_half_up)

PREFIXO_PENDENCIA: str = getattr(_config, "PREFIXO_PENDENCIA", "PEN")

# Tipos formais de pendência definidos em src/config.py
PEND_SPREAD_NEGATIVO: str = getattr(_config, "PEND_SPREAD_NEGATIVO", "SPREAD_NEGATIVO")
PEND_OPERACAO_DUPLICADA: str = getattr(
    _config, "PEND_OPERACAO_DUPLICADA", "OPERACAO_DUPLICADA"
)
PEND_DIVERGENCIA_SPREAD: str = getattr(
    _config, "PEND_DIVERGENCIA_SPREAD", "DIVERGENCIA_SPREAD"
)
PEND_DEVOLUCAO_TAXA: str = getattr(_config, "PEND_DEVOLUCAO_TAXA", "DEVOLUCAO_TAXA")
PEND_CONTRATO_AUSENTE: str = getattr(
    _config, "PEND_CONTRATO_AUSENTE", "CONTRATO_AUSENTE"
)
PEND_PIX_NAO_IDENTIFICADO: str = getattr(
    _config, "PEND_PIX_NAO_IDENTIFICADO", "PIX_NAO_IDENTIFICADO"
)
PEND_DEVOLUCAO_PIX: str = getattr(_config, "PEND_DEVOLUCAO_PIX", "DEVOLUCAO_PIX")

# Responsáveis pela decisão humana
QUEM_FINANCEIRO: str = getattr(
    _config, "QUEM_FINANCEIRO", "Financeiro Tarvo (Helena)"
)
QUEM_COMERCIAL: str = getattr(
    _config, "QUEM_COMERCIAL", "Comercial Tarvo (Diego)"
)

# Códigos de estabelecimento (EC) das exceções de Checkout
EC_CASA_DO_ESTUDANTE: str = str(
    getattr(_config, "EC_CASA_DO_ESTUDANTE", getattr(_config, "EC_TAXA_ZERO", "1018325654"))
)
EC_ATLAS_IDIOMAS: str = str(
    getattr(_config, "EC_ATLAS_IDIOMAS", getattr(_config, "EC_SEM_CONTRATO", "1076801732"))
)

TOLERANCIA_TAXA_PP: Decimal = para_decimal(
    getattr(_config, "TOLERANCIA_TAXA_PP", Decimal("0.01"))
)


def _normalizar_texto(texto: Any) -> str:
    """Remove acentos e converte para minúsculas para buscas resilientes."""
    if texto is None:
        return ""
    sem_acento = "".join(
        c
        for c in unicodedata.normalize("NFKD", str(texto).strip())
        if not unicodedata.combining(c)
    )
    return sem_acento.lower()


# ============================================================================
# 2. REGISTRO DE PENDÊNCIA E AMARRAÇÃO NO RASTRO
# ============================================================================
def _registrar_pendencia(
    tracker: Any,
    tipo: str,
    ref_origem: str,
    valor_brl: Decimal,
    motivo: str,
    quem_decide: str,
    itens_rastro: list[tuple[str, str, Decimal]],
) -> dict[str, Any]:
    """
    Cria um registro formal para `saida/pendencias.csv` e registra suas linhas
    de origem no `RastroTracker` de modo que a soma dos itens feche exatamente
    com `valor_brl`.
    """
    valor_final = round_half_up(valor_brl)
    id_saida = (
        tracker.novo_id(PREFIXO_PENDENCIA)
        if tracker is not None and hasattr(tracker, "novo_id")
        else f"{PREFIXO_PENDENCIA}-0000"
    )

    if tracker is not None and hasattr(tracker, "registrar"):
        for arq_origem, ref_item, val_item in itens_rastro:
            tracker.registrar(
                id_saida,
                str(arq_origem),
                str(ref_item),
                round_half_up(val_item),
            )

    return {
        "id_saida": id_saida,
        "tipo": tipo,
        "ref_origem": str(ref_origem),
        "valor_brl": valor_final,
        "motivo": motivo,
        "quem_decide": quem_decide,
    }


# ============================================================================
# 3. COLETORES ESPECIALIZADOS POR FONTE DE DADOS
# ============================================================================
def _coletar_pendencias_remessas(
    dados_remessas: dict[str, Any] | None,
    tracker: Any,
    agrupar_por_categoria: bool = False,
) -> list[dict[str, Any]]:
    """
    Coleta as pendências oriundas do relatório da Ponte Câmbio:
    1. Spreads negativos (4 operações com estouro da trava de cotação de 2h).
    2. Operação repetida (`PC-0926-0162` - Bagagem Livre).
    3. Cobrança de spread divergente sobre a Mundo Aberto (~1.50% vs 1.20% contratado).
    """
    if not dados_remessas:
        return []

    pendencias: list[dict[str, Any]] = []
    arquivo_ponte = str(
        dados_remessas.get("arquivo_origem")
        or "03_email_ponte_cambio_relatorio_set2026.eml"
    )
    todas_ops: list[dict[str, Any]] = list(dados_remessas.get("operacoes") or [])

    # ------------------------------------------------------------------------
    # Pendência 1: Spreads Negativos (PC-0926-0210, -0326, -0491, -0545)
    # ------------------------------------------------------------------------
    ops_negativas: list[dict[str, Any]] = list(
        dados_remessas.get("operacoes_spread_negativo") or []
    )
    if not ops_negativas and todas_ops:
        ops_negativas = [
            op
            for op in todas_ops
            if not op.get("is_duplicada", False)
            and (
                round_half_up(op.get("spread_brl", op.get("spread_rs", 0))) < Decimal("0.00")
                or para_decimal(op.get("spread_pct", op.get("taxa_aplicada_pct", 0))) < Decimal("0.00")
            )
        ]

    if ops_negativas:
        if agrupar_por_categoria:
            itens_rastro_neg: list[tuple[str, str, Decimal]] = []
            refs_neg: list[str] = []
            soma_neg = Decimal("0.00")
            for op in ops_negativas:
                ref = str(op.get("ref_origem") or op.get("num_operacao") or "")
                arq = str(op.get("arquivo_origem") or arquivo_ponte)
                spread_val = round_half_up(op.get("spread_brl", op.get("spread_rs", 0)))
                soma_neg += spread_val
                refs_neg.append(ref)
                itens_rastro_neg.append((arq, ref, spread_val))

            pendencias.append(
                _registrar_pendencia(
                    tracker=tracker,
                    tipo=PEND_SPREAD_NEGATIVO,
                    ref_origem=refs_neg[0] if len(refs_neg) == 1 else ",".join(refs_neg),
                    valor_brl=soma_neg,
                    motivo=(
                        f"Contestação de {len(ops_negativas)} operações com spread negativo "
                        f"({', '.join(refs_neg)}) na Ponte Câmbio por estouro da trava de 2h "
                        f"(excluídas da comissão e da NFS-e)."
                    ),
                    quem_decide=QUEM_FINANCEIRO,
                    itens_rastro=itens_rastro_neg,
                )
            )
        else:
            for op in ops_negativas:
                ref = str(op.get("ref_origem") or op.get("num_operacao") or "")
                arq = str(op.get("arquivo_origem") or arquivo_ponte)
                lojista = str(op.get("lojista") or op.get("cliente") or "").strip()
                spread_val = round_half_up(op.get("spread_brl", op.get("spread_rs", 0)))
                spread_pct = round_half_up(
                    op.get("spread_pct", op.get("taxa_aplicada_pct", 0))
                )
                pendencias.append(
                    _registrar_pendencia(
                        tracker=tracker,
                        tipo=PEND_SPREAD_NEGATIVO,
                        ref_origem=ref,
                        valor_brl=spread_val,
                        motivo=(
                            f"Operação de câmbio {ref} ({lojista}) com spread negativo "
                            f"({spread_pct}% / R$ {spread_val}) por expiração da trava de cotação "
                            f"de 2h; excluída da comissão e enviada para contestação junto à Ponte Câmbio."
                        ),
                        quem_decide=QUEM_FINANCEIRO,
                        itens_rastro=[(arq, ref, spread_val)],
                    )
                )

    # ------------------------------------------------------------------------
    # Pendência 2: Operação Repetida (PC-0926-0162 - Bagagem Livre)
    # ------------------------------------------------------------------------
    ops_duplicadas: list[dict[str, Any]] = list(
        dados_remessas.get("operacoes_duplicadas") or []
    )
    if not ops_duplicadas and todas_ops:
        vistas: set[str] = set()
        for op in todas_ops:
            ref = str(op.get("ref_origem") or op.get("num_operacao") or "")
            if ref in vistas:
                ops_duplicadas.append(op)
            else:
                vistas.add(ref)

    for op in ops_duplicadas:
        ref = str(op.get("ref_origem") or op.get("num_operacao") or "")
        arq = str(op.get("arquivo_origem") or arquivo_ponte)
        lojista = str(op.get("lojista") or op.get("cliente") or "Bagagem Livre").strip()
        spread_val = round_half_up(op.get("spread_brl", op.get("spread_rs", 0)))
        comissao_dup = round_half_up(spread_val * Decimal("0.50"))
        # Utiliza o spread_brl (ou comissão duplicada, se parametrizado) garantindo consistência com o rastro
        valor_dup = spread_val if spread_val != Decimal("0.00") else comissao_dup
        pendencias.append(
            _registrar_pendencia(
                tracker=tracker,
                tipo=PEND_OPERACAO_DUPLICADA,
                ref_origem=ref,
                valor_brl=valor_dup,
                motivo=(
                    f"Operação repetida {ref} ({lojista}) no relatório da Ponte Câmbio "
                    f"(Spread R$ {spread_val} / Comissão Tarvo R$ {comissao_dup}); "
                    f"segunda ocorrência expurgada da apuração para retificação do borderô."
                ),
                quem_decide=QUEM_FINANCEIRO,
                itens_rastro=[(arq, ref, valor_dup)],
            )
        )

    # ------------------------------------------------------------------------
    # Pendência 3: Divergência de Spread da Mundo Aberto (1.50% vs 1.20%)
    # ------------------------------------------------------------------------
    ops_divergentes: list[dict[str, Any]] = list(
        dados_remessas.get("operacoes_divergentes") or []
    )
    if not ops_divergentes and todas_ops:
        for op in todas_ops:
            if op.get("is_duplicada", False) or op.get("is_spread_negativo", False):
                continue
            taxa_ap = para_decimal(op.get("spread_pct", op.get("taxa_aplicada_pct", 0)))
            taxa_ct = para_decimal(
                op.get("spread_contratado_pct", op.get("taxa_contratada_pct", 0))
            )
            if taxa_ct > Decimal("0.00") and abs(taxa_ap - taxa_ct) > TOLERANCIA_TAXA_PP:
                ops_divergentes.append(op)

    if ops_divergentes:
        itens_rastro_div: list[tuple[str, str, Decimal]] = []
        soma_dif_brl = Decimal("0.00")
        lojista_div = str(
            ops_divergentes[0].get("lojista")
            or ops_divergentes[0].get("cliente")
            or "Mundo Aberto Intercâmbio"
        ).strip()
        cnpj_div = str(ops_divergentes[0].get("cnpj") or "").strip()
        taxa_ct_ref = round_half_up(
            ops_divergentes[0].get(
                "spread_contratado_pct",
                ops_divergentes[0].get("taxa_contratada_pct", Decimal("1.20")),
            )
        )
        taxa_ap_ref = round_half_up(
            ops_divergentes[0].get(
                "spread_pct",
                ops_divergentes[0].get("taxa_aplicada_pct", Decimal("1.50")),
            )
        )

        for op in ops_divergentes:
            ref = str(op.get("ref_origem") or op.get("num_operacao") or "")
            arq = str(op.get("arquivo_origem") or arquivo_ponte)
            dif_op = op.get("diferenca_brl")
            if dif_op is None or round_half_up(dif_op) == Decimal("0.00"):
                val_brl = para_decimal(op.get("valor_brl", op.get("valor_bruto", 0)))
                t_ap = para_decimal(op.get("spread_pct", op.get("taxa_aplicada_pct", 0)))
                t_ct = para_decimal(
                    op.get("spread_contratado_pct", op.get("taxa_contratada_pct", 0))
                )
                if val_brl > Decimal("0.00"):
                    dif_calculada = round_half_up(val_brl * (t_ap - t_ct) / Decimal("100"))
                else:
                    sp_brl = para_decimal(op.get("spread_brl", op.get("spread_rs", 0)))
                    dif_calculada = (
                        round_half_up(sp_brl * (t_ap - t_ct) / t_ap)
                        if t_ap != Decimal("0")
                        else Decimal("0.00")
                    )
            else:
                dif_calculada = round_half_up(dif_op)

            soma_dif_brl += dif_calculada
            itens_rastro_div.append((arq, ref, dif_calculada))

        ref_div_principal = str(
            ops_divergentes[0].get("ref_origem")
            or ops_divergentes[0].get("num_operacao")
            or cnpj_div
        )
        pendencias.append(
            _registrar_pendencia(
                tracker=tracker,
                tipo=PEND_DIVERGENCIA_SPREAD,
                ref_origem=ref_div_principal,
                valor_brl=soma_dif_brl,
                motivo=(
                    f"Cobrança de spread a maior pela Ponte Câmbio sobre {lojista_div} "
                    f"em {len(ops_divergentes)} operações (aplicado ~{taxa_ap_ref}% vs "
                    f"{taxa_ct_ref}% contratado), gerando diferença total de R$ {soma_dif_brl}."
                ),
                quem_decide=QUEM_FINANCEIRO,
                itens_rastro=itens_rastro_div,
            )
        )

    return pendencias


def _coletar_pendencias_checkout(
    dados_checkout: dict[str, Any] | None,
    tracker: Any,
) -> list[dict[str, Any]]:
    """
    Coleta as pendências oriundas do relatório de Checkout da adquirente Orbe:
    4. Ressarcimento Casa do Estudante (EC `1018325654` - acordo comercial taxa 0.00%).
    5. Contrato ausente Atlas Idiomas (EC `1076801732` - sem contrato assinado em 2026).
    """
    if not dados_checkout:
        return []

    pendencias: list[dict[str, Any]] = []
    transacoes: list[dict[str, Any]] = list(dados_checkout.get("transacoes") or [])
    arquivo_orbe_padrao = str(
        dados_checkout.get("arquivo_origem")
        or "01_orbe_relatorio_comissoes_set2026.csv"
    )

    # ------------------------------------------------------------------------
    # Pendência 4: Ressarcimento de taxas da Casa do Estudante (EC 1018325654)
    # ------------------------------------------------------------------------
    txs_casa_estudante: list[dict[str, Any]] = []
    for tx in transacoes:
        ec = str(tx.get("cod_estabelecimento") or "").strip()
        nome = _normalizar_texto(tx.get("lojista") or tx.get("nome_estabelecimento"))
        if ec == EC_CASA_DO_ESTUDANTE or "casa do estudante" in nome:
            txs_casa_estudante.append(tx)

    if txs_casa_estudante:
        itens_rastro_casa: list[tuple[str, str, Decimal]] = []
        soma_taxa_retida = Decimal("0.00")

        for tx in txs_casa_estudante:
            id_tx = str(tx.get("id_transacao") or tx.get("ref_origem") or "")
            arq_tx = str(tx.get("arquivo_origem") or arquivo_orbe_padrao)
            val_bruto = para_decimal(tx.get("valor_bruto", 0))
            taxa_ap = para_decimal(tx.get("taxa_aplicada_pct", 0))

            # Usa a mesma fórmula canônica de `divergencias.py` (ou `valor_taxa` se idêntico)
            if "valor_taxa" in tx and tx.get("valor_taxa") is not None and taxa_ap == Decimal("0"):
                dif_tx = round_half_up(tx["valor_taxa"])
            else:
                dif_tx = round_half_up(val_bruto * taxa_ap / Decimal("100"))

            if dif_tx != Decimal("0.00"):
                soma_taxa_retida += dif_tx
                itens_rastro_casa.append((arq_tx, id_tx, dif_tx))

        if itens_rastro_casa:
            pendencias.append(
                _registrar_pendencia(
                    tracker=tracker,
                    tipo=PEND_DEVOLUCAO_TAXA,
                    ref_origem=EC_CASA_DO_ESTUDANTE,
                    valor_brl=soma_taxa_retida,
                    motivo=(
                        f"Devolução/ressarcimento de taxas cobradas indevidamente pela Orbe "
                        f"da Casa do Estudante (EC {EC_CASA_DO_ESTUDANTE}) em "
                        f"{len(itens_rastro_casa)} transações (acordo comercial vigente prevê "
                        f"taxa de 0.00% no checkout)."
                    ),
                    quem_decide=QUEM_FINANCEIRO,
                    itens_rastro=itens_rastro_casa,
                )
            )

    # ------------------------------------------------------------------------
    # Pendência 5: Contrato Ausente da Atlas Idiomas (EC 1076801732)
    # ------------------------------------------------------------------------
    txs_sem_contrato: list[dict[str, Any]] = []
    for tx in transacoes:
        ec = str(tx.get("cod_estabelecimento") or "").strip()
        nome = _normalizar_texto(tx.get("lojista") or tx.get("nome_estabelecimento"))
        sem_contrato_flag = bool(tx.get("sem_contrato", False))
        if sem_contrato_flag or ec == EC_ATLAS_IDIOMAS or "atlas idiomas" in nome:
            txs_sem_contrato.append(tx)

    if txs_sem_contrato:
        # Agrupa por código de estabelecimento caso haja mais de um EC sem contrato
        por_ec: dict[str, list[dict[str, Any]]] = {}
        for tx in txs_sem_contrato:
            ec_key = str(tx.get("cod_estabelecimento") or EC_ATLAS_IDIOMAS).strip()
            por_ec.setdefault(ec_key, []).append(tx)

        for ec_key, lista_tx in por_ec.items():
            itens_rastro_atlas: list[tuple[str, str, Decimal]] = []
            soma_taxa_atlas = Decimal("0.00")
            soma_bruto_atlas = Decimal("0.00")
            nome_lojista = str(
                lista_tx[0].get("lojista")
                or lista_tx[0].get("nome_estabelecimento")
                or "Atlas Idiomas"
            ).strip()

            for tx in lista_tx:
                id_tx = str(tx.get("id_transacao") or tx.get("ref_origem") or "")
                arq_tx = str(tx.get("arquivo_origem") or arquivo_orbe_padrao)
                val_bruto = round_half_up(tx.get("valor_bruto", 0))
                taxa_ap = para_decimal(tx.get("taxa_aplicada_pct", 0))
                val_taxa = tx.get("valor_taxa")
                if val_taxa is not None:
                    taxa_retida = round_half_up(val_taxa)
                else:
                    taxa_retida = round_half_up(val_bruto * taxa_ap / Decimal("100"))

                soma_bruto_atlas += val_bruto
                soma_taxa_atlas += taxa_retida
                itens_rastro_atlas.append((arq_tx, id_tx, taxa_retida))

            pendencias.append(
                _registrar_pendencia(
                    tracker=tracker,
                    tipo=PEND_CONTRATO_AUSENTE,
                    ref_origem=ec_key,
                    valor_brl=soma_taxa_atlas,
                    motivo=(
                        f"Estabelecimento {nome_lojista} (EC {ec_key}) operou {len(lista_tx)} "
                        f"transações em 09/2026 (volume bruto R$ {soma_bruto_atlas} / "
                        f"taxas Orbe R$ {soma_taxa_atlas}) sem contrato ou tabela de taxas "
                        f"assinada para 2026; faturamento bloqueado até formalização comercial."
                    ),
                    quem_decide=QUEM_COMERCIAL,
                    itens_rastro=itens_rastro_atlas,
                )
            )

    return pendencias


def _coletar_pendencias_extratos(
    dados_extratos: dict[str, Any] | None,
    tracker: Any,
) -> list[dict[str, Any]]:
    """
    Coleta as pendências oriundas dos extratos bancários (Banco Aurora):
    6. Pix recebido não identificado de R$ 7.350,00 (linha física `L50`).
    7. Devolução/estorno de Pix de R$ 12.400,00 referente à Mundo Aberto (linha física `L65`).
    """
    if not dados_extratos:
        return []

    pendencias: list[dict[str, Any]] = []
    lancamentos_aurora: list[dict[str, Any]] = list(
        dados_extratos.get("lancamentos_aurora") or []
    )
    arquivos_map = dados_extratos.get("arquivos") or {}
    arquivo_aurora_padrao = str(
        arquivos_map.get("aurora")
        or dados_extratos.get("arquivo_aurora")
        or "05a_extrato_banco_aurora_cc4471_set2026.csv"
    )

    # ------------------------------------------------------------------------
    # Pendência 6: Pix Não Identificado (Aurora L50 - R$ 7.350,00)
    # ------------------------------------------------------------------------
    lanc_pix_nao_id: dict[str, Any] | None = None
    for lanc in lancamentos_aurora:
        ref = str(lanc.get("ref_origem") or "").strip().upper()
        desc = _normalizar_texto(lanc.get("descricao"))
        valor = round_half_up(lanc.get("valor", 0))

        is_nao_identificado = (
            "nao identificad" in desc
            or "sem identificac" in desc
            or "desconhecid" in desc
            or ("pix" in desc and "cpf" in desc and valor == Decimal("7350.00"))
        )
        if is_nao_identificado or (ref == "L50" and valor == Decimal("7350.00")):
            lanc_pix_nao_id = lanc
            break

    if lanc_pix_nao_id is None:
        # Fallback por linha física L50 caso o texto varie
        for lanc in lancamentos_aurora:
            if str(lanc.get("ref_origem") or "").strip().upper() == "L50":
                lanc_pix_nao_id = lanc
                break

    if lanc_pix_nao_id is not None:
        ref_l50 = str(lanc_pix_nao_id.get("ref_origem") or "L50").strip()
        arq_l50 = str(lanc_pix_nao_id.get("arquivo_origem") or arquivo_aurora_padrao)
        val_l50 = round_half_up(lanc_pix_nao_id.get("valor", Decimal("7350.00")))
        data_l50 = str(lanc_pix_nao_id.get("data") or "").strip()
        desc_l50 = str(lanc_pix_nao_id.get("descricao") or "").strip()

        pendencias.append(
            _registrar_pendencia(
                tracker=tracker,
                tipo=PEND_PIX_NAO_IDENTIFICADO,
                ref_origem=ref_l50,
                valor_brl=val_l50,
                motivo=(
                    f"Crédito de Pix no Banco Aurora ({ref_l50} em {data_l50}: '{desc_l50}') "
                    f"no valor de R$ {val_l50} sem identificação do lojista/remetente; "
                    f"alocado em conta transitória (1.1.09.002) aguardando conciliação manual."
                ),
                quem_decide=QUEM_FINANCEIRO,
                itens_rastro=[(arq_l50, ref_l50, val_l50)],
            )
        )

    # ------------------------------------------------------------------------
    # Pendência 7: Devolução/Estorno de Pix Mundo Aberto (Aurora L65 - R$ 12.400,00)
    # ------------------------------------------------------------------------
    lanc_devolucao_pix: dict[str, Any] | None = None
    for lanc in lancamentos_aurora:
        ref = str(lanc.get("ref_origem") or "").strip().upper()
        desc = _normalizar_texto(lanc.get("descricao"))
        valor = round_half_up(lanc.get("valor", 0))

        is_devolucao_mundo_aberto = (
            ("devoluc" in desc or "estorn" in desc)
            and ("pix" in desc or "mundo aberto" in desc)
        )
        if is_devolucao_mundo_aberto or (
            ref == "L65" and abs(valor) == Decimal("12400.00")
        ):
            lanc_devolucao_pix = lanc
            break

    if lanc_devolucao_pix is None:
        # Fallback por linha física L65
        for lanc in lancamentos_aurora:
            if str(lanc.get("ref_origem") or "").strip().upper() == "L65":
                lanc_devolucao_pix = lanc
                break

    if lanc_devolucao_pix is not None:
        ref_l65 = str(lanc_devolucao_pix.get("ref_origem") or "L65").strip()
        arq_l65 = str(
            lanc_devolucao_pix.get("arquivo_origem") or arquivo_aurora_padrao
        )
        val_l65 = round_half_up(lanc_devolucao_pix.get("valor", Decimal("-12400.00")))
        data_l65 = str(lanc_devolucao_pix.get("data") or "").strip()
        desc_l65 = str(lanc_devolucao_pix.get("descricao") or "").strip()

        pendencias.append(
            _registrar_pendencia(
                tracker=tracker,
                tipo=PEND_DEVOLUCAO_PIX,
                ref_origem=ref_l65,
                valor_brl=val_l65,
                motivo=(
                    f"Devolução/estorno de Pix no Banco Aurora ({ref_l65} em {data_l65}: "
                    f"'{desc_l65}') no valor de R$ {val_l65} referente à Mundo Aberto; "
                    f"exige verificação da origem da operação e ajuste do repasse/faturamento."
                ),
                quem_decide=QUEM_FINANCEIRO,
                itens_rastro=[(arq_l65, ref_l65, val_l65)],
            )
        )

    return pendencias


# ============================================================================
# 4. PONTO DE ENTRADA PRINCIPAL (consolidar_pendencias)
# ============================================================================
def consolidar_pendencias(
    dados_checkout: dict[str, Any] | None = None,
    dados_remessas: dict[str, Any] | None = None,
    dados_extratos: dict[str, Any] | None = None,
    tracker: Any = None,
    *,
    agrupar_spreads_negativos: bool | None = None,
) -> list[dict[str, Any]]:
    """
    Consolida todas as anomalias operacionais e comerciais do período que exigem
    deliberação humana, gerando as linhas prontas para `saida/pendencias.csv`.

    Parâmetros:
        dados_checkout: Dicionário retornado por `parse_orbe.parse_orbe_e_taxas`.
        dados_remessas: Dicionário retornado por `parse_ponte.parse_ponte_e_taxas`.
        dados_extratos: Dicionário retornado por `parse_extratos.parse_extratos_e_plano`.
        tracker: Instância de `RastroTracker` para geração de `id_saida` e amarração
                 no `rastro.csv`.
        agrupar_spreads_negativos: Se `True`, consolida os 4 spreads negativos em uma
                                   única linha de pendência (totalizando exatas 7 linhas).
                                   Se `False`, emite uma linha por operação de spread negativo.
                                   Por padrão, consulta `config.AGRUPAR_SPREADS_NEGATIVOS_PENDENCIA`
                                   (default `True` para corresponder exatamente às 7 pendências).

    Retorna:
        Lista de dicionários contendo as colunas obrigatórias de `saida/pendencias.csv`:
        `id_saida;tipo;ref_origem;valor_brl;motivo;quem_decide`.
    """
    if agrupar_spreads_negativos is None:
        agrupar_spreads_negativos = bool(
            getattr(_config, "AGRUPAR_SPREADS_NEGATIVOS_PENDENCIA", True)
        )

    pendencias: list[dict[str, Any]] = []

    # 1 a 3: Remessas Internacionais (Ponte Câmbio)
    pendencias.extend(
        _coletar_pendencias_remessas(
            dados_remessas=dados_remessas,
            tracker=tracker,
            agrupar_por_categoria=agrupar_spreads_negativos,
        )
    )

    # 4 e 5: Checkout (Adquirente Orbe)
    pendencias.extend(
        _coletar_pendencias_checkout(
            dados_checkout=dados_checkout,
            tracker=tracker,
        )
    )

    # 6 e 7: Conciliação Bancária (Extratos Banco Aurora)
    pendencias.extend(
        _coletar_pendencias_extratos(
            dados_extratos=dados_extratos,
            tracker=tracker,
        )
    )

    return pendencias


# Aliases de compatibilidade
gerar_pendencias = consolidar_pendencias
apurar_pendencias = consolidar_pendencias