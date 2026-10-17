"""
Módulo de apuração de divergências de taxas e spreads (Missão 2).

Compara transação por transação (Checkout) e operação por operação (Remessas)
a taxa contratada contra a taxa efetivamente aplicada pela adquirente Orbe
e pela parceira Ponte Câmbio, registrando o rastro matemático no `RastroTracker`.

Regras de Negócio:
1. Checkout:
   - Filtra transações onde `abs(taxa_aplicada_pct - taxa_contratada_pct) > 0.01` p.p.
   - Ignora truncamentos de 1 centavo da Orbe quando a taxa percentual está correta.
   - Calcula `diferenca_brl = round_half_up(valor_bruto * (taxa_aplicada_pct - taxa_contratada_pct) / 100)`.
   - Inclui integralmente as cobranças sobre a Casa do Estudante (`taxa_contratada_pct = 0.00%`).
   - Ignora transações sem contrato assinado em 2026 (Atlas Idiomas - tratada em `pendencias.py`).
2. Remessas:
   - Apura as divergências de spread da Mundo Aberto Intercâmbio (~1.50% aplicado vs 1.20% contratado).
   - Apura as 4 operações com spread negativo decorrentes de estouro da trava de 2h,
     reportando o spread negativo em reais em `diferenca_brl`.
   - Expurga a segunda ocorrência da operação duplicada `PC-0926-0162`.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import re
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

PREFIXO_DIVERGENCIA: str = getattr(_config, "PREFIXO_DIVERGENCIA", "DIV")
LINHA_CHECKOUT: str = getattr(_config, "LINHA_CHECKOUT", "CHECKOUT")
LINHA_REMESSA: str = getattr(_config, "LINHA_REMESSA", "REMESSA")
TOLERANCIA_TAXA_PP: Decimal = para_decimal(
    getattr(_config, "TOLERANCIA_TAXA_PP", Decimal("0.01"))
)
EC_ATLAS_IDIOMAS: str = str(
    getattr(_config, "EC_ATLAS_IDIOMAS", getattr(_config, "EC_SEM_CONTRATO", "1076801732"))
)


def _normalizar_taxa_pct(val: Any) -> Decimal:
    """Garante que taxas percentuais tenham pelo menos 2 casas decimais."""
    dec = para_decimal(val)
    if dec == Decimal("0"):
        return Decimal("0.00")
    # Se possuir no máximo 2 casas significativas, padroniza em 2 casas;
    # caso contrário, preserva até 4 casas para não truncar taxas fracionárias.
    q2 = dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if dec == q2:
        return q2
    return dec.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP).normalize()


# ============================================================================
# 2. EMISSOR PADRONIZADO COM REGISTRO NO RASTRO
# ============================================================================
def _emitir_divergencia(
    tracker: Any,
    cnpj: str,
    linha_negocio: str,
    arquivo_origem: str,
    ref_origem: str,
    taxa_contratada_pct: Decimal,
    taxa_aplicada_pct: Decimal,
    diferenca_brl: Decimal,
) -> dict[str, Any]:
    """
    Gera um registro formal para `saida/divergencias_taxa.csv` e registra
    sua linha correspondente no `RastroTracker`.
    """
    dif_arredondada = round_half_up(diferenca_brl)
    taxa_ct_fmt = round_half_up(taxa_contratada_pct)
    taxa_ap_fmt = round_half_up(taxa_aplicada_pct)

    id_saida = (
        tracker.novo_id(PREFIXO_DIVERGENCIA)
        if tracker is not None and hasattr(tracker, "novo_id")
        else f"{PREFIXO_DIVERGENCIA}-0000"
    )

    if tracker is not None and hasattr(tracker, "registrar"):
        tracker.registrar(
            id_saida,
            str(arquivo_origem),
            str(ref_origem),
            dif_arredondada,
        )

    return {
        "id_saida": id_saida,
        "cnpj": clean_cnpj(cnpj),
        "linha_negocio": linha_negocio,
        "ref_origem": str(ref_origem),
        "taxa_contratada_pct": taxa_ct_fmt,
        "taxa_aplicada_pct": taxa_ap_fmt,
        "diferenca_brl": dif_arredondada,
    }


# ============================================================================
# 3. APURAÇÃO DE DIVERGÊNCIAS DE CHECKOUT (ORBE)
# ============================================================================
def _apurar_divergencias_checkout(
    dados_checkout: dict[str, Any] | None,
    tracker: Any,
) -> list[dict[str, Any]]:
    """
    Analisa todas as transações de Checkout da adquirente Orbe e identifica
    aquelas em que `abs(taxa_aplicada_pct - taxa_contratada_pct) > TOLERANCIA_TAXA_PP`.
    """
    if not dados_checkout:
        return []

    transacoes: list[dict[str, Any]] = list(dados_checkout.get("transacoes") or [])
    arquivo_padrao = str(
        dados_checkout.get("arquivo_origem")
        or "01_orbe_relatorio_comissoes_set2026.csv"
    )

    divergencias_checkout: list[dict[str, Any]] = []

    for tx in transacoes:
        # 1. Pula estabelecimentos sem contrato em 2026 (ex: Atlas Idiomas)
        ec = str(tx.get("cod_estabelecimento") or "").strip()
        if bool(tx.get("sem_contrato", False)) or ec == EC_ATLAS_IDIOMAS:
            continue

        taxa_ct_raw = tx.get("taxa_contratada_pct")
        if taxa_ct_raw is None:
            continue

        cnpj_raw = tx.get("cnpj")
        if not cnpj_raw:
            continue
        cnpj = clean_cnpj(cnpj_raw)

        taxa_contratada_pct = para_decimal(taxa_ct_raw)
        taxa_aplicada_pct = para_decimal(tx.get("taxa_aplicada_pct", Decimal("0.00")))

        # 2. Verifica se a diferença em pontos percentuais supera a tolerância (0.01 p.p.)
        diferenca_pp = taxa_aplicada_pct - taxa_contratada_pct
        if abs(diferenca_pp) <= TOLERANCIA_TAXA_PP:
            continue

        # 3. Calcula o impacto financeiro em reais pela fórmula canônica da especificação:
        #    diferenca_brl = round_half_up(valor_bruto * (taxa_aplicada_pct - taxa_contratada_pct) / 100)
        valor_bruto = para_decimal(tx.get("valor_bruto", Decimal("0.00")))
        diferenca_brl = round_half_up(
            valor_bruto * (taxa_aplicada_pct - taxa_contratada_pct) / Decimal("100")
        )

        if diferenca_brl == Decimal("0.00"):
            continue

        ref_origem = str(tx.get("id_transacao") or tx.get("ref_origem") or "").strip()
        arquivo_origem = str(tx.get("arquivo_origem") or arquivo_padrao).strip()

        divergencias_checkout.append(
            _emitir_divergencia(
                tracker=tracker,
                cnpj=cnpj,
                linha_negocio=LINHA_CHECKOUT,
                arquivo_origem=arquivo_origem,
                ref_origem=ref_origem,
                taxa_contratada_pct=taxa_contratada_pct,
                taxa_aplicada_pct=taxa_aplicada_pct,
                diferenca_brl=diferenca_brl,
            )
        )

    return divergencias_checkout


# ============================================================================
# 4. APURAÇÃO DE DIVERGÊNCIAS DE REMESSAS (PONTE CÂMBIO)
# ============================================================================
def _calcular_diferenca_remessa_divergente(
    op: dict[str, Any],
    taxa_contratada_pct: Decimal,
    taxa_aplicada_pct: Decimal,
) -> Decimal:
    """
    Calcula a diferença financeira em reais para uma operação de câmbio com
    taxa de spread divergente (ex: Mundo Aberto 1.50% aplicado vs 1.20% contratado).
    """
    dif_precalculada = op.get("diferenca_brl")
    if dif_precalculada is not None and round_half_up(dif_precalculada) != Decimal("0.00"):
        return round_half_up(dif_precalculada)

    valor_brl = para_decimal(
        op.get("valor_brl", op.get("valor_operacao_brl", op.get("valor_bruto", 0)))
    )
    spread_brl = para_decimal(op.get("spread_brl", op.get("spread_rs", 0)))

    # Se o spread_brl veio explícito na planilha e valor_brl é conhecido,
    # verifica se `spread_brl - round_half_up(valor_brl * taxa_contratada / 100)`
    # ou `round_half_up(valor_brl * (taxa_aplicada - taxa_contratada) / 100)` se aplica:
    if valor_brl > Decimal("0.00"):
        return round_half_up(
            valor_brl * (taxa_aplicada_pct - taxa_contratada_pct) / Decimal("100")
        )

    if spread_brl != Decimal("0.00") and taxa_aplicada_pct != Decimal("0.00"):
        spread_contratado_brl = round_half_up(
            spread_brl * (taxa_contratada_pct / taxa_aplicada_pct)
        )
        return round_half_up(spread_brl - spread_contratado_brl)

    return Decimal("0.00")


def _apurar_divergencias_remessas(
    dados_remessas: dict[str, Any] | None,
    tracker: Any,
) -> list[dict[str, Any]]:
    """
    Apura as divergências de remessas internacionais da Ponte Câmbio:
    1. Operações onde o spread aplicado diverge do contratado (ex: 23 operações da Mundo Aberto).
    2. Operações com spread negativo por estouro da trava de 2h (4 operações:
       `PC-0926-0210`, `PC-0926-0326`, `PC-0926-0491`, `PC-0926-0545`).
    """
    if not dados_remessas:
        return []

    arquivo_ponte = str(
        dados_remessas.get("arquivo_origem")
        or "03_email_ponte_cambio_relatorio_set2026.eml"
    )
    spreads_map: dict[str, Any] = (
        dados_remessas.get("spreads_contrato")
        or dados_remessas.get("spreads_contratados")
        or {}
    )

    ops_divergentes: list[dict[str, Any]] = list(
        dados_remessas.get("operacoes_divergentes") or []
    )
    ops_negativas: list[dict[str, Any]] = list(
        dados_remessas.get("operacoes_spread_negativo") or []
    )

    # Se o dicionário vier apenas com a lista bruta `operacoes`, reconstrói a seleção
    todas_ops: list[dict[str, Any]] = list(dados_remessas.get("operacoes") or [])
    if not ops_divergentes and not ops_negativas and todas_ops:
        vistas: set[str] = set()
        for op in todas_ops:
            ref = str(op.get("ref_origem") or op.get("num_operacao") or "").strip()
            if not ref or op.get("is_duplicada", False) or ref in vistas:
                continue
            vistas.add(ref)

            spread_brl = round_half_up(op.get("spread_brl", op.get("spread_rs", 0)))
            taxa_ap = para_decimal(op.get("spread_pct", op.get("taxa_aplicada_pct", 0)))
            cnpj_op = clean_cnpj(op.get("cnpj") or op.get("cnpj_cliente"))

            taxa_ct_raw = op.get("spread_contratado_pct", op.get("taxa_contratada_pct"))
            if taxa_ct_raw is None and cnpj_op in spreads_map:
                info_sp = spreads_map[cnpj_op]
                taxa_ct_raw = (
                    info_sp.get("spread_pct")
                    if isinstance(info_sp, dict)
                    else info_sp
                )
            taxa_ct = para_decimal(taxa_ct_raw) if taxa_ct_raw is not None else Decimal("1.50")

            if spread_brl < Decimal("0.00") or taxa_ap < Decimal("0.00"):
                ops_negativas.append(op)
            elif abs(taxa_ap - taxa_ct) > TOLERANCIA_TAXA_PP:
                ops_divergentes.append(op)

    # Preserva a ordem de aparição no relatório original da Ponte Câmbio
    # combinando `ops_divergentes` e `ops_negativas` sem duplicar `ref_origem`.
    candidatas: list[tuple[int, str, dict[str, Any]]] = []
    refs_adicionadas: set[str] = set()

    for idx_fallback, op in enumerate(ops_divergentes):
        ref = str(op.get("ref_origem") or op.get("num_operacao") or "").strip()
        if not ref or ref in refs_adicionadas or op.get("is_duplicada", False):
            continue
        refs_adicionadas.add(ref)
        ordem = int(op.get("linha_planilha", idx_fallback))
        candidatas.append((ordem, "TAXA", op))

    for idx_fallback, op in enumerate(ops_negativas, start=10000):
        ref = str(op.get("ref_origem") or op.get("num_operacao") or "").strip()
        if not ref or ref in refs_adicionadas or op.get("is_duplicada", False):
            continue
        refs_adicionadas.add(ref)
        ordem = int(op.get("linha_planilha", idx_fallback))
        candidatas.append((ordem, "NEGATIVO", op))

    candidatas.sort(key=lambda item: item[0])

    divergencias_remessa: list[dict[str, Any]] = []

    for _, subtipo, op in candidatas:
        ref_origem = str(op.get("ref_origem") or op.get("num_operacao") or "").strip()
        arquivo_origem = str(op.get("arquivo_origem") or arquivo_ponte).strip()
        cnpj_bruto = op.get("cnpj") or op.get("cnpj_cliente")
        if not cnpj_bruto:
            continue
        cnpj = clean_cnpj(cnpj_bruto)

        taxa_ct_raw = op.get("spread_contratado_pct", op.get("taxa_contratada_pct"))
        if (taxa_ct_raw is None or para_decimal(taxa_ct_raw) == Decimal("0.00")) and cnpj in spreads_map:
            info_sp = spreads_map[cnpj]
            taxa_ct_raw = (
                info_sp.get("spread_pct") if isinstance(info_sp, dict) else info_sp
            )
        taxa_contratada_pct = para_decimal(taxa_ct_raw) if taxa_ct_raw is not None else Decimal("1.50")
        taxa_aplicada_pct = para_decimal(
            op.get("spread_pct", op.get("taxa_aplicada_pct", Decimal("0.00")))
        )

        if subtipo == "NEGATIVO" or op.get("is_spread_negativo", False):
            # Nas 4 operações de spread negativo, diferenca_brl é o próprio spread negativo em reais
            diferenca_brl = round_half_up(
                op.get("spread_brl", op.get("spread_rs", op.get("diferenca_brl", 0)))
            )
        else:
            diferenca_brl = _calcular_diferenca_remessa_divergente(
                op=op,
                taxa_contratada_pct=taxa_contratada_pct,
                taxa_aplicada_pct=taxa_aplicada_pct,
            )

        if diferenca_brl == Decimal("0.00"):
            continue

        divergencias_remessa.append(
            _emitir_divergencia(
                tracker=tracker,
                cnpj=cnpj,
                linha_negocio=LINHA_REMESSA,
                arquivo_origem=arquivo_origem,
                ref_origem=ref_origem,
                taxa_contratada_pct=taxa_contratada_pct,
                taxa_aplicada_pct=taxa_aplicada_pct,
                diferenca_brl=diferenca_brl,
            )
        )

    return divergencias_remessa


# ============================================================================
# 5. PONTO DE ENTRADA PRINCIPAL (apurar_divergencias)
# ============================================================================
def apurar_divergencias(
    dados_checkout: dict[str, Any] | None = None,
    dados_remessas: dict[str, Any] | None = None,
    tracker: Any = None,
) -> list[dict[str, Any]]:
    """
    Apura transação por transação todas as divergências entre taxas contratadas
    e taxas aplicadas nas linhas de negócio de Checkout e Remessas.

    Parâmetros:
        dados_checkout: Dicionário retornado por `parse_orbe.parse_orbe_e_taxas`.
        dados_remessas: Dicionário retornado por `parse_ponte.parse_ponte_e_taxas`.
        tracker: Instância ativa de `RastroTracker` para geração de `id_saida` (`DIV-xxxx`)
                 e amarração no `rastro.csv`.

    Retorna:
        Lista de dicionários prontos para gravação em `saida/divergencias_taxa.csv`:
        `id_saida;cnpj;linha_negocio;ref_origem;taxa_contratada_pct;taxa_aplicada_pct;diferenca_brl`.
    """
    divergencias: list[dict[str, Any]] = []

    # 1. Divergências de Checkout (Orbe)
    divergencias.extend(
        _apurar_divergencias_checkout(
            dados_checkout=dados_checkout,
            tracker=tracker,
        )
    )

    # 2. Divergências de Remessas Internacionais (Ponte Câmbio)
    divergencias.extend(
        _apurar_divergencias_remessas(
            dados_remessas=dados_remessas,
            tracker=tracker,
        )
    )

    return divergencias


# Aliases de compatibilidade
calcular_divergencias = apurar_divergencias
gerar_divergencias = apurar_divergencias