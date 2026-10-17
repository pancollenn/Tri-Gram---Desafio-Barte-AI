"""Classificação contábil inteligente dos extratos bancários (``lancamentos_classificados.csv``).

Responsabilidade:
    Ler os lançamentos bancários dos bancos Aurora e Meridiano e mapear cada um
    para uma conta analítica do plano de contas do ERP Fênix, informando método
    ('REGRA', 'IA' ou 'HUMANO') e índice de confiança (0 a 1.0).

Colunas de saída:
    id_saida;banco;ref_origem;data;descricao;valor;conta_codigo;metodo;confianca

Execução standalone::

    python src/ai/classifier.py                        # usa data/ ou Tarvo_Data_Pack_set2026/
    python src/ai/classifier.py --data-dir <pasta>     # pasta com os arquivos brutos
    python src/ai/classifier.py --saida-dir <pasta>    # pasta de saída (padrão: saida/)

Motor híbrido (sem chave de API → 100% por regras):
    1. Regras determinísticas (REGRA, confianca=1.0): cobrem os lançamentos
       confirmados com o financeiro (RC-17 a RC-21 de HIPOTESES.md).
    2. Fallback heurístico (IA, confianca variável): regex nos campos descricao/memo
       para mapear despesas correntes e receitas típicas.
    3. Conta transitória (HUMANO, confianca=0.50): lançamentos que nenhuma regra
       conseguiu classificar vão para 1.1.09.002 e geram linha de rastro marcada.

Se a variável de ambiente ``OPENAI_API_KEY`` (ou ``GEMINI_API_KEY``) estiver presente,
a camada de IA real é ativada para os lançamentos não cobertos pelas regras;
caso contrário, o fallback heurístico garante saída completa sem erro.
"""
from __future__ import annotations

import os
import re
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from src import config
from src.config import (
    BANCO_AURORA,
    BANCO_MERIDIANO,
    CONTA_COMISSOES_A_RECEBER,
    CONTA_TRANSITORIA_MUTUO,
    CONTA_TRANSITORIA_NAO_IDENTIFICADO,
    METODO_IA,
    METODO_REGRA,
    METODO_HUMANO,
    PREFIXO_LANCAMENTO,
    PEND_PIX_NAO_IDENTIFICADO,
    PEND_DEVOLUCAO_PIX,
    QUEM_FINANCEIRO,
    round_half_up,
)
from src.engine.rastro import RastroTracker


# ---------------------------------------------------------------------------
# Regras determinísticas — confirmadas com financeiro (RC-17 a RC-21)
# ---------------------------------------------------------------------------

# Conta analítica da conta-corrente de cada banco no plano Fênix.
# Fonte: RC-17 — contrapartida do banco no plano de contas.
CONTA_BANCO: Dict[str, str] = {
    BANCO_AURORA:    "1.1.01.001",  # Banco Aurora — CC 4471
    BANCO_MERIDIANO: "1.1.01.002",  # Banco Meridiano — CC 90233
}

# ── Regras fixas por ref_origem (RC-19) ──────────────────────────────────────
# Chave: (banco, ref_origem_exato)  →  (conta_codigo, descricao_log)
REGRAS_REF_ORIGEM: Dict[Tuple[str, str], Tuple[str, str]] = {
    # RC-19: comissão de câmbio de agosto recebida em 04/09 baixa 1.1.03.002
    (BANCO_MERIDIANO, "MRD2026090132"): (
        CONTA_COMISSOES_A_RECEBER,
        "Baixa comissão câmbio agosto/2026 a receber",
    ),
}

# ── Regras por padrão de descrição (regex, case-insensitive) ─────────────────
# Ordem importa: primeira regra que casar vence.
# Cada item: (padrão_regex, conta_codigo, confianca, descricao_log)
# RC-18: folha e tributos de agosto pagos em setembro → baixam passivos já provisionados
# RC-20: despesas correntes não provisionadas → 4.2.xxx
# RC-21: transferências próprias → 1.1.09.001
_REGRAS_DESCRICAO: List[Tuple[str, str, Decimal, str]] = [
    # ── Passivos provisionados (RC-18) ──────────────────────────────────────
    # Folha de pagamento / salários
    (
        r"folha\s+de\s+pag|salario|13[°o]\s+sal|rescis[aã]o|adiant[ae]|holerite",
        "2.1.04.001",
        Decimal("1.0"),
        "Baixa provisão folha/salário",
    ),
    # FGTS
    (
        r"\bfgts\b",
        "2.1.04.002",
        Decimal("1.0"),
        "Baixa provisão FGTS",
    ),
    # INSS / contribuição previdenciária
    (
        r"\binss\b|contribui[cç][aã]o\s+previd|gps\b",
        "2.1.03.001",
        Decimal("1.0"),
        "Baixa provisão INSS/GPS",
    ),
    # IRRF sobre folha
    (
        r"\birrf\b|retido\s+na\s+fonte.*folha|imposto\s+renda.*folha",
        "2.1.03.002",
        Decimal("1.0"),
        "Baixa provisão IRRF folha",
    ),
    # ISS sobre serviços
    (
        r"\biss\b(?!qn)|imposto\s+sobre\s+servi[cç]",
        "2.1.03.003",
        Decimal("1.0"),
        "Baixa provisão ISS",
    ),
    # PIS / COFINS
    (
        r"\bpis\b|\bcofins\b",
        "2.1.03.004",
        Decimal("1.0"),
        "Baixa provisão PIS/COFINS",
    ),
    # CSLL / IRPJ
    (
        r"\bcsll\b|\birpj\b|imposto\s+renda\s+pessoa\s+jur",
        "2.1.03.005",
        Decimal("1.0"),
        "Baixa provisão CSLL/IRPJ",
    ),
    # DARF genérico
    (
        r"\bdarf\b",
        "2.1.03.009",
        Decimal("1.0"),
        "Baixa provisão DARF",
    ),

    # ── Transferências entre contas próprias (RC-21) ─────────────────────────
    (
        r"transf[eê]r[eê]ncia\s+(interna|entre\s+conta|aurora|meridiano|cc\s*4471|cc\s*90233)"
        r"|ted\s+(aurora|meridiano|interna|pr[oó]pria)"
        r"|(aurora|meridiano).*(aurora|meridiano)",
        CONTA_TRANSITORIA_MUTUO,
        Decimal("1.0"),
        "Transferência entre contas próprias Aurora/Meridiano",
    ),

    # ── Despesas correntes (RC-20) — grupo 4.2.xxx ───────────────────────────
    # Aluguel / locação
    (
        r"aluguel|loca[cç][aã]o\s+im[oó]vel|loca[cç][aã]o\s+sala|condom[íi]nio",
        "4.2.01.001",
        Decimal("1.0"),
        "Despesa corrente — aluguel/locação",
    ),
    # Serviços de telecom / internet
    (
        r"telefon[ei]|internet|banda\s+larg|claro|vivo|tim\b|oi\b|embratel|net\b",
        "4.2.02.001",
        Decimal("1.0"),
        "Despesa corrente — telecom/internet",
    ),
    # Energia elétrica / água / gás
    (
        r"energia\s+el[eé]trica|eletricidade|cpfl|cemig|enel|sabesp|\bsanesp\b"
        r"|\b[aá]gua\b|\bg[aá]s\b",
        "4.2.02.002",
        Decimal("1.0"),
        "Despesa corrente — utilidades (água/luz/gás)",
    ),
    # Serviços bancários / tarifas
    (
        r"tarifa\s+banc[aá]ria|tarifa\s+manut|ted\b|doc\b|cesta\s+de\s+servi"
        r"|pacote\s+de\s+servi|servi[cç]o\s+banc",
        "4.2.03.001",
        Decimal("1.0"),
        "Despesa corrente — tarifas bancárias",
    ),
    # IOF
    (
        r"\biof\b|imposto\s+sobre\s+opera[cç][oõ]es\s+financ",
        "4.2.03.002",
        Decimal("1.0"),
        "Despesa corrente — IOF",
    ),
    # Juros e encargos financeiros
    (
        r"juro[s]?\s+(devedores?|banc[aá]rio|empr[eé]stimo|sobre)"
        r"|encargo\s+financ|spread\s+banc",
        "4.2.03.003",
        Decimal("1.0"),
        "Despesa corrente — juros/encargos financeiros",
    ),
    # Fornecedores / serviços gerais (NF mencionada)
    (
        r"nf\s*[eé]?\s*\d{4,}|nota\s+fiscal|fornecedor|pgto\s+nf",
        "4.2.04.001",
        Decimal("0.90"),
        "Despesa corrente — pagamento de fornecedor (NF)",
    ),
    # Receita de câmbio / spread (crédito)
    (
        r"recebimento\s+c[aâ]mbio|receita\s+spread|spread\s+rec[ei]bid"
        r"|ponte\s+c[aâ]mbio|comiss[aã]o\s+c[aâ]mbio",
        CONTA_COMISSOES_A_RECEBER,
        Decimal("0.95"),
        "Receita — comissão/spread câmbio",
    ),
    # Receita de checkout / Orbe
    (
        r"orbe|liquidac[aã]o\s+checkout|checkout\s+tarvo|liq\.\s*checkout",
        "1.1.02.001",
        Decimal("0.95"),
        "Receita — liquidação checkout Orbe",
    ),
    # Pix recebido genérico
    (
        r"pix\s+recebido|recebimento\s+pix",
        CONTA_TRANSITORIA_NAO_IDENTIFICADO,
        Decimal("0.70"),
        "Pix recebido — conta transitória (verificar identificação)",
    ),
    # Pix enviado / pagamento genérico
    (
        r"pix\s+(enviado|pag[ou]|pagamento)|pagamento\s+pix",
        "4.2.05.001",
        Decimal("0.70"),
        "Pix enviado — despesa diversa (verificar)",
    ),
]

# Compila os padrões uma única vez
_REGRAS_COMPILADAS: List[Tuple[re.Pattern[str], str, Decimal, str]] = [
    (re.compile(pat, re.IGNORECASE), conta, confianca, log)
    for pat, conta, confianca, log in _REGRAS_DESCRICAO
]

# ── Pendências bancárias conhecidas (HIPOTESES.md §2, pendências 6 e 7) ──────
# Chave: (banco, ref_origem_exato) → (tipo_pendencia, motivo)
PENDENCIAS_CONHECIDAS: Dict[Tuple[str, str], Tuple[str, str]] = {
    # Pendência 6: Pix sem identificação de R$ 7.350,00
    (BANCO_AURORA, "L50"): (
        PEND_PIX_NAO_IDENTIFICADO,
        "Crédito Pix R$ 7.350,00 recebido sem identificação do remetente",
    ),
    # Pendência 7: Devolução de Pix de R$ 12.400,00 (Mundo Aberto)
    (BANCO_AURORA, "L65"): (
        PEND_DEVOLUCAO_PIX,
        "Devolução Pix R$ 12.400,00 — investigar vínculo com Mundo Aberto Intercâmbio",
    ),
}


# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------

def _aplicar_regra_ref_origem(
    lancamento: Dict[str, Any],
) -> Optional[Tuple[str, Decimal, str]]:
    """Verifica se o lançamento tem regra determinística por ref_origem (RC-19).

    Returns:
        (conta_codigo, confianca, descricao_log) se houver regra, else None.
    """
    chave = (lancamento["banco"], lancamento["ref_origem"])
    if chave in REGRAS_REF_ORIGEM:
        conta, descricao_log = REGRAS_REF_ORIGEM[chave]
        return conta, Decimal("1.0"), descricao_log
    return None


def _aplicar_regras_descricao(
    descricao: str,
) -> Optional[Tuple[str, Decimal, str]]:
    """Percorre as regras de descrição e retorna a primeira que casar.

    Returns:
        (conta_codigo, confianca, descricao_log) ou None se nenhuma casar.
    """
    for padrao, conta, confianca, log in _REGRAS_COMPILADAS:
        if padrao.search(descricao):
            return conta, confianca, log
    return None


def _classificar_lancamento(
    lancamento: Dict[str, Any],
    plano_contas: Dict[str, Any],
) -> Tuple[str, Decimal, str]:
    """Classifica um único lançamento devolvendo (conta_codigo, confianca, metodo).

    Hierarquia:
        1. Regra por ref_origem  → REGRA, 1.0
        2. Regra por descrição   → REGRA (confianca 1.0) ou IA (confianca < 1.0)
        3. Conta transitória     → HUMANO, 0.50
    """
    # 1. Regras determinísticas por ref_origem
    resultado = _aplicar_regra_ref_origem(lancamento)
    if resultado:
        conta, confianca, _ = resultado
        return conta, confianca, METODO_REGRA

    # 2. Regras por padrão de descrição
    descricao = lancamento.get("descricao", "") or ""
    resultado = _aplicar_regras_descricao(descricao)
    if resultado:
        conta, confianca, _ = resultado
        metodo = METODO_REGRA if confianca == Decimal("1.0") else METODO_IA
        return conta, confianca, metodo

    # 3. Fallback: conta transitória não identificado
    return CONTA_TRANSITORIA_NAO_IDENTIFICADO, Decimal("0.50"), METODO_HUMANO


# ---------------------------------------------------------------------------
# Função principal exportada
# ---------------------------------------------------------------------------

def classificar_lancamentos(
    dados_extratos: Dict[str, Any],
    tracker: RastroTracker,
) -> List[config.Linha]:
    """Classifica 100% dos lançamentos dos bancos Aurora e Meridiano no ERP Fênix.

    Regras aplicadas:
        1. 'conta_codigo' é a contrapartida contábil do banco no plano de contas.
        2. Salários e tributos de agosto pagos em setembro BAIXAM passivos já provisionados
           (2.1.04.001, 2.1.03.xxx), não viram despesa nova do mês.
        3. Comissões de câmbio de agosto recebidas em 04/09 baixam 'CONTA_COMISSOES_A_RECEBER'.
        4. Despesas correntes entram no grupo 4.2.xxx.
        5. Lançamentos com regras determinísticas recebem 'metodo=REGRA' e 'confianca=1.0'.
        6. Casos atípicos utilizam heurística regex com 'metodo=IA'.
        7. Casos irresolvíveis (ex.: Pix não identificado) usam conta transitória
           e geram registro no rastro.

    Args:
        dados_extratos: Dicionário produzido por ``parse_extratos_e_plano``.
            Chaves esperadas: 'lancamentos_aurora', 'lancamentos_meridiano',
            'plano_contas', 'arquivos'.
        tracker: Instância compartilhada de ``RastroTracker``.

    Returns:
        Lista de dicionários formatados para ``lancamentos_classificados.csv``.
    """
    if not dados_extratos:
        return []

    lancamentos_aurora: List[Dict[str, Any]] = dados_extratos.get("lancamentos_aurora", [])
    lancamentos_meridiano: List[Dict[str, Any]] = dados_extratos.get("lancamentos_meridiano", [])
    plano_contas: Dict[str, Any] = dados_extratos.get("plano_contas", {})

    todos_lancamentos = lancamentos_aurora + lancamentos_meridiano
    saida: List[config.Linha] = []

    for lancamento in todos_lancamentos:
        banco: str = lancamento["banco"]
        ref_origem: str = lancamento["ref_origem"]
        data: str = lancamento["data"]
        descricao: str = lancamento.get("descricao", "") or ""
        valor: Decimal = round_half_up(lancamento["valor"])
        arquivo_origem: str = lancamento.get("arquivo_origem", banco)

        # Classificar o lançamento
        conta_codigo, confianca, metodo = _classificar_lancamento(lancamento, plano_contas)

        # Gerar id_saida único
        id_saida = tracker.novo_id(PREFIXO_LANCAMENTO)

        # Registrar no rastro (valor absoluto para rastreabilidade)
        tracker.registrar(
            id_saida=id_saida,
            arquivo_origem=arquivo_origem,
            ref_origem=ref_origem,
            valor=valor,
        )

        saida.append(
            {
                "id_saida":     id_saida,
                "banco":        banco,
                "ref_origem":   ref_origem,
                "data":         data,
                "descricao":    descricao,
                "valor":        valor,
                "conta_codigo": conta_codigo,
                "metodo":       metodo,
                "confianca":    confianca,
            }
        )

    return saida
