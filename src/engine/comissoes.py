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
from typing import Any, Dict, List, Set

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
    arquivo_origem_checkout = dados_checkout.get("arquivo_origem") or "01_orbe_relatorio_comissoes_set2026.csv"
    
    if transacoes:
        # Passo 1: Agrupar transações válidas por CNPJ do lojista
        por_lojista_checkout: Dict[str, List[Dict[str, Any]]] = {}
        
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
            por_lojista_checkout.setdefault(cnpj, []).append(tx)
       
        # Passo 2, 3 e 4: Calcular comissão por linha, registrar no rastro e somar por lojista
        for cnpj, lista_tx in por_lojista_checkout.items():
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
                    arquivo_origem=tx.get("arquivo_origem") or arquivo_origem_checkout,
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
    
    # --- PARTE 2: REMESSAS (Objetivo Alvo) ---
    operacoes = dados_remessas.get("operacoes_validas")
    if operacoes is None and "operacoes" in dados_remessas:
        operacoes = dados_remessas["operacoes"]

    arquivo_origem_remessas = dados_remessas.get("arquivo_origem") or "03_email_ponte_cambio_relatorio_set2026.eml"

    if operacoes:
        # Filtro de segurança caso a lista não tenha vindo pré-filtrada
        vistos: Set[str] = set()
        ops_validas: List[Dict[str, Any]] = []
        for op in operacoes:
            ref = str(op.get("ref_origem") or op.get("num_operacao") or "")
            spread_brl = config.para_decimal(op.get("spread_brl", 0))
            
            # Expurgo de duplicata (RC-12)
            if op.get("is_duplicada") or ref in vistos:
                continue
            # Exclusão de spreads negativos (RC-13)
            if (
                op.get("is_spread_negativo")
                or spread_brl < Decimal("0.00")
                or config.para_decimal(op.get("spread_pct", 0)) < Decimal("0.00")
            ):
                continue
            if op.get("is_valida_comissao") is False:
                continue
            
            vistos.add(ref)
            ops_validas.append(op)

        # Agrupar operações válidas por CNPJ
        por_lojista_remessas: Dict[str, List[Dict[str, Any]]] = {}
        for op in ops_validas:
            cnpj_bruto = op.get("cnpj")
            if not cnpj_bruto:
                continue
            cnpj = config.clean_cnpj(cnpj_bruto)
            por_lojista_remessas.setdefault(cnpj, []).append(op)

        # Para cada lojista de remessas: calcula comissão, registra no rastro e consolida
        for cnpj, lista_ops in por_lojista_remessas.items():
            id_saida = tracker.novo_id(config.PREFIXO_COMISSAO)
            primeira_op = lista_ops[0]
            nome_lojista = (
                primeira_op.get("lojista")
                or primeira_op.get("cliente")
                or "Lojista"
            )
            soma_comissao = Decimal("0.00")

            for op in lista_ops:
                spread_brl = config.para_decimal(op["spread_brl"])
                # RC-10: Tarvo fica com 50% do Spread R$ de cada operação
                comissao_linha = config.round_half_up(spread_brl * config.PARTICIPACAO_TARVO_SPREAD)

                ref_origem = str(op.get("ref_origem") or op.get("num_operacao"))
                tracker.registrar(
                    id_saida=id_saida,
                    arquivo_origem=op.get("arquivo_origem") or arquivo_origem_remessas,
                    ref_origem=ref_origem,
                    valor=comissao_linha,
                )
                soma_comissao += comissao_linha

            resultado.append({
                "id_saida": id_saida,
                "cnpj": cnpj,
                "lojista": nome_lojista,
                "linha_negocio": config.LINHA_REMESSA,
                "comissao_brl": soma_comissao,
            })

    return resultado

