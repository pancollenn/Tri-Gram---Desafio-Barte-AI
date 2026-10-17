"""Motor de rastreabilidade matemática (``rastro.csv``).

Regra central do edital: todo número de saída aponta para as linhas de origem
que o compõem, e a soma de ``valor`` por ``id_saida`` no rastro deve bater
centavo a centavo com o número reportado.

Uso típico (dentro de um módulo de domínio)::

    id_saida = tracker.novo_id(PREFIXO_COMISSAO)
    for tx in transacoes_do_lojista:
        tracker.registrar(id_saida, "01_orbe_....csv", tx.id_transacao, comissao_linha)
    comissoes.append({"id_saida": id_saida, ..., "comissao_brl": total})

O ``valor`` de cada linha de rastro é a CONTRIBUIÇÃO daquela linha de origem
ao número reportado (ex.: a comissão da transação, não o valor bruto).
"""
from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Mapping, Set, Tuple, Union

from src.config import (
    ARQ_RASTRO,
    ARQUIVOS_SAIDA,
    ENCODING_CSV,
    SEPARADOR_CSV,
    Numero,
    format_brl,
    para_decimal,
    round_half_up,
    tem_precisao_de_centavos,
)


class RastroTracker:
    """Gera ``id_saida`` únicos e acumula as linhas de ``rastro.csv``."""

    def __init__(self) -> None:
        self._contadores: Dict[str, int] = {}
        self._ids_emitidos: Set[str] = set()
        self._linhas: List[Dict[str, str]] = []
        self._somas: Dict[str, Decimal] = {}
        self._chaves: Set[Tuple[str, str, str]] = set()

    # -- geração de ids ------------------------------------------------------
    def novo_id(self, prefixo: str) -> str:
        """Gera um ``id_saida`` único e determinístico (ex.: ``COM-0001``)."""
        proximo = self._contadores.get(prefixo, 0) + 1
        self._contadores[prefixo] = proximo
        id_saida = f"{prefixo}-{proximo:04d}"
        self._ids_emitidos.add(id_saida)
        return id_saida

    # -- registro ------------------------------------------------------------
    def registrar(
        self,
        id_saida: str,
        arquivo_origem: str,
        ref_origem: str,
        valor: Numero,
        permitir_duplicado: bool = False,
    ) -> None:
        """Registra que a linha ``ref_origem`` de ``arquivo_origem`` contribui com ``valor``.

        Args:
            id_saida: id da linha de saída que recebe a contribuição.
            arquivo_origem: nome do arquivo bruto (ex.: ``01_orbe_..._set2026.csv``).
            ref_origem: identificador da linha (``id_transacao``, ``Nº Operação``,
                ``L10``, ``FITID``).
            valor: contribuição em reais. Deve estar em centavos exatos
                (use ``round_half_up`` antes) para o rastro fechar sem resíduos.
            permitir_duplicado: por padrão, registrar duas vezes a mesma tripla
                (id_saida, arquivo, ref) é erro, pois dobra o total em silêncio.

        Raises:
            ValueError: campos vazios, valor com mais de 2 casas ou duplicidade.
        """
        if not id_saida or not arquivo_origem or not str(ref_origem).strip():
            raise ValueError("id_saida, arquivo_origem e ref_origem são obrigatórios")
        dec = para_decimal(valor)
        if not tem_precisao_de_centavos(dec):
            raise ValueError(
                f"Valor de rastro com mais de 2 casas ({dec}) em {id_saida}/{ref_origem}: "
                "arredonde com round_half_up antes de registrar."
            )
        dec = round_half_up(dec)
        chave = (id_saida, arquivo_origem, str(ref_origem))
        if chave in self._chaves and not permitir_duplicado:
            raise ValueError(f"Linha de origem já registrada para {id_saida}: {chave[1:]}")
        self._chaves.add(chave)
        self._somas[id_saida] = self._somas.get(id_saida, Decimal("0.00")) + dec
        self._linhas.append(
            {
                "id_saida": id_saida,
                "arquivo_origem": arquivo_origem,
                "ref_origem": str(ref_origem),
                "valor": format_brl(dec),
            }
        )

    # -- consulta ------------------------------------------------------------
    def total(self, id_saida: str) -> Decimal:
        """Soma das contribuições registradas para ``id_saida`` (0.00 se não houver)."""
        return self._somas.get(id_saida, Decimal("0.00"))

    def possui_rastro(self, id_saida: str) -> bool:
        """Indica se há ao menos uma linha de rastro para ``id_saida``."""
        return id_saida in self._somas

    @property
    def linhas(self) -> List[Dict[str, str]]:
        """Cópia das linhas de rastro já formatadas para CSV."""
        return list(self._linhas)

    # -- validação -----------------------------------------------------------
    def validar_soma(self, id_saida: str, valor_total_reportado: Numero) -> None:
        """Garante que a soma do rastro bate centavo a centavo com o valor reportado.

        Raises:
            AssertionError: sem rastro para o id ou soma diferente do reportado.
        """
        if not self.possui_rastro(id_saida):
            raise AssertionError(f"[{id_saida}] sem nenhuma linha de rastro")
        reportado = round_half_up(valor_total_reportado)
        soma = self.total(id_saida)
        if soma != reportado:
            raise AssertionError(
                f"[{id_saida}] rastro soma {format_brl(soma)} mas o valor reportado é "
                f"{format_brl(reportado)} (diferença {format_brl(reportado - soma)})"
            )

    def validar_todos(self, reportados: Mapping[str, Numero]) -> None:
        """Valida vários ids de uma vez e reporta TODAS as falhas juntas.

        Args:
            reportados: mapa ``id_saida -> valor reportado``.

        Raises:
            AssertionError: com a lista completa de ids que não fecham.
        """
        falhas: List[str] = []
        for id_saida, valor in reportados.items():
            try:
                self.validar_soma(id_saida, valor)
            except AssertionError as exc:
                falhas.append(str(exc))
        if falhas:
            raise AssertionError(
                f"{len(falhas)} id(s) de saída não fecham com o rastro:\n  " + "\n  ".join(falhas)
            )

    # -- exportação ----------------------------------------------------------
    def exportar_csv(self, caminho_saida: Union[str, Path]) -> Path:
        """Grava ``rastro.csv`` (``;``, utf-8, cabeçalho do contrato).

        Args:
            caminho_saida: caminho do arquivo ou diretório (grava ``rastro.csv`` nele).

        Returns:
            Caminho do arquivo gravado.
        """
        destino = Path(caminho_saida)
        if destino.is_dir():
            destino = destino / ARQ_RASTRO
        destino.parent.mkdir(parents=True, exist_ok=True)
        colunas = ARQUIVOS_SAIDA[ARQ_RASTRO].colunas
        with open(destino, "w", encoding=ENCODING_CSV, newline="") as arq:
            escritor = csv.DictWriter(
                arq, fieldnames=colunas, delimiter=SEPARADOR_CSV, lineterminator="\n"
            )
            escritor.writeheader()
            escritor.writerows(self._linhas)
        return destino
