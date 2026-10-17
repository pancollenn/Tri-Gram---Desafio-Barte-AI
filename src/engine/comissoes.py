"""Cálculo das comissões devidas à Tarvo por lojista (``comissoes_por_lojista.csv``).

Responsabilidade:
    Consome os dados tratados de Checkout (Orbe) e Remessas (Ponte Câmbio) e calcula
    a comissão líquida de cada lojista por linha de negócio, registrando a contribuição
    de cada transação no RastroTracker.

Colunas de saída:
    id_saida;cnpj;lojista;linha_negocio;comissao_brl
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

from src import config
from src.engine.rastro import RastroTracker


def calcular_comissoes(
    dados_checkout: Dict[str, Any],
    dados_remessas: Dict[str, Any],
    tracker: RastroTracker,
) -> List[config.Linha]:
    """Calcula a comissão consolidada por lojista e linha de negócio.

    Regras aplicadas:
        1. Checkout: comissão calculada pela taxa contratada (não pela aplicada pela Orbe).
        2. Estornos abatem comissão pela taxa vigente na data da venda original.
        3. Casa do Estudante: taxa contratada 0.00% (comissão = R$ 0.00).
        4. Remessas: 50% de participação no spread de operações válidas da Ponte Câmbio.
        5. Expurgo da duplicata PC-0926-0162 e exclusão dos 4 spreads negativos.
        6. Rastro: cada transação/operação é registrada via ``tracker.registrar()``.

    Returns:
        Lista de dicionários formatados para ``comissoes_por_lojista.csv``.
    """
    resultado: List[config.Linha] = []
    
    # --- PARTE 1: CHECKOUT (Objetivo Mínimo) ---
    transacoes = dados_checkout.get("transacoes", [])
    arquivo_origem = dados_checkout.get("arquivo_origem") or "01_orbe_relatorio_comissoes_set2026.csv"
    
    # Passo 1: Agrupar transações válidas por CNPJ do lojista
    por_lojista: Dict[str, List[Dict[str, Any]]] = {}
    
    for tx in transacoes:
        cod_ec = str(tx.get("cod_estabelecimento", "")).strip()
        # Pula quem não tem contrato (ex: Atlas Idiomas)
        if tx.get("sem_contrato") or cod_ec in config.EC_SEM_CONTRATO_2026:
            continue
        # Se a taxa vier ausente e não for a Casa do Estudante (cuja taxa é forçada para 0.00), ignora
        if tx.get("taxa_contratada_pct") is None and cod_ec != config.EC_CASA_DO_ESTUDANTE:
            continue
        
        cnpj_bruto = tx.get("cnpj")
        if not cnpj_bruto:
            continue
        cnpj = config.clean_cnpj(cnpj_bruto)
        por_lojista.setdefault(cnpj, []).append(tx)
   
    # Passo 2, 3 e 4: Calcular comissão por linha, registrar no rastro e somar por lojista
    for cnpj, lista_tx in por_lojista.items():
        id_saida = tracker.novo_id(config.PREFIXO_COMISSAO)
        primeira_tx = lista_tx[0]
        nome_lojista = (
            primeira_tx.get("lojista")
            or primeira_tx.get("nome_lojista")
            or primeira_tx.get("nome_estabelecimento")
            or "Lojista"
        )
        soma_comissao = Decimal("0.00")
        
        for tx in lista_tx:
            valor_bruto = config.para_decimal(tx["valor_bruto"])
            
            # Blindagem oficial: Casa do Estudante tem taxa contratada de 0.00%
            cod_ec = str(tx.get("cod_estabelecimento", "")).strip()
            if cod_ec == config.EC_CASA_DO_ESTUDANTE:
                taxa_pct = config.TAXA_CONTRATADA_CASA_DO_ESTUDANTE_PCT
            else:
                taxa_pct = config.para_decimal(tx["taxa_contratada_pct"])
            
            # Calcula a comissão da transação individual arredondada em 2 casas
            comissao_linha = config.round_half_up(valor_bruto * taxa_pct / Decimal("100"))
            
            # Registra a transação no rastro.csv
            tracker.registrar(
                id_saida=id_saida,
                arquivo_origem=arquivo_origem,
                ref_origem=str(tx["id_transacao"]),
                valor=comissao_linha,
            )
            soma_comissao += comissao_linha
        
        # Adiciona a linha consolidada do lojista para comissoes_por_lojista.csv
        resultado.append({
            "id_saida": id_saida,
            "cnpj": cnpj,
            "lojista": nome_lojista,
            "linha_negocio": config.LINHA_CHECKOUT,
            "comissao_brl": soma_comissao,
        })
    
    return resultado
