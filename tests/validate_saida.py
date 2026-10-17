#!/usr/bin/env python3
"""Auditoria cega dos arquivos de ``saida/`` (QA, Pessoa 3).

Uso::

    python tests/validate_saida.py                 # audita ./saida
    python tests/validate_saida.py --saida-dir X   # outra pasta
    python tests/validate_saida.py -v              # lista todos os ids do rastro
    python tests/validate_saida.py --estrito       # avisos (ex.: arquivo vazio) viram erro

DE PROPÓSITO este script NÃO importa nada de ``src/``: o contrato do edital é
repetido aqui, de forma independente, para que um erro no código de produção
(ex.: cabeçalho trocado em ``config.py``) seja pego em vez de replicado.
Só usa biblioteca padrão.

Códigos de saída: 0 = sem erros; 1 = há erros (ou avisos com ``--estrito``).
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

RAIZ = Path(__file__).resolve().parent.parent
SEPARADOR = ";"
LIMITE_ERROS_POR_VERIFICACAO = 15
LIMITE_OK_LISTADOS = 10

LINHAS_NEGOCIO = {"CHECKOUT", "REMESSA"}
BANCOS = {"AURORA", "MERIDIANO"}
METODOS = {"REGRA", "IA", "HUMANO"}
PONTE_CAMBIO_CNPJ = "75374179000146"

RE_CNPJ = re.compile(r"^\d{14}$")
RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RE_DINHEIRO = re.compile(r"^-?\d+\.\d{2}$")
RE_PCT = re.compile(r"^-?\d+(\.\d+)?$")
RE_RAZAO = re.compile(r"^\d(\.\d+)?$")
TOKENS_INVALIDOS = {"nan", "null", "none", "nat", "inf", "-inf", "infinity", "-infinity"}

COMISSOES = "comissoes_por_lojista.csv"
DIVERGENCIAS = "divergencias_taxa.csv"
NOTAS = "notas_a_emitir.csv"
LANCAMENTOS = "lancamentos_classificados.csv"
PENDENCIAS = "pendencias.csv"
RASTRO = "rastro.csv"

# Contrato do edital: cabeçalho exato + tipo de cada coluna sensível.
CONTRATO: Dict[str, Dict[str, object]] = {
    COMISSOES: {
        "colunas": ["id_saida", "cnpj", "lojista", "linha_negocio", "comissao_brl"],
        "dinheiro": {"comissao_brl"},
        "cnpj": {"cnpj"},
        "dominios": {"linha_negocio": LINHAS_NEGOCIO},
    },
    DIVERGENCIAS: {
        "colunas": [
            "id_saida", "cnpj", "linha_negocio", "ref_origem",
            "taxa_contratada_pct", "taxa_aplicada_pct", "diferenca_brl",
        ],
        "dinheiro": {"diferenca_brl"},
        "pct": {"taxa_contratada_pct", "taxa_aplicada_pct"},
        "cnpj": {"cnpj"},
        "dominios": {"linha_negocio": LINHAS_NEGOCIO},
    },
    NOTAS: {
        "colunas": ["id_saida", "tomador_cnpj", "tomador", "linha_negocio", "valor_brl", "discriminacao"],
        "dinheiro": {"valor_brl"},
        "cnpj": {"tomador_cnpj"},
        "dominios": {"linha_negocio": LINHAS_NEGOCIO},
    },
    LANCAMENTOS: {
        "colunas": [
            "id_saida", "banco", "ref_origem", "data", "descricao",
            "valor", "conta_codigo", "metodo", "confianca",
        ],
        "dinheiro": {"valor"},
        "razao": {"confianca"},
        "data": {"data"},
        "dominios": {"banco": BANCOS, "metodo": METODOS},
    },
    PENDENCIAS: {
        "colunas": ["id_saida", "tipo", "ref_origem", "valor_brl", "motivo", "quem_decide"],
        "dinheiro": {"valor_brl"},
    },
    RASTRO: {
        "colunas": ["id_saida", "arquivo_origem", "ref_origem", "valor"],
        "dinheiro": {"valor"},
    },
}

Linha = Dict[str, str]


class Relatorio:
    """Acumula e imprime os resultados [OK] / [ERRO] / [AVISO]."""

    def __init__(self) -> None:
        self.erros = 0
        self.avisos = 0

    def ok(self, msg: str) -> None:
        print(f"[OK]    {msg}")

    def erro(self, msg: str) -> None:
        self.erros += 1
        print(f"[ERRO]  {msg}")

    def aviso(self, msg: str) -> None:
        self.avisos += 1
        print(f"[AVISO] {msg}")

    def secao(self, titulo: str) -> None:
        print(f"\n=== {titulo} ===")


class Coletor:
    """Limita a quantidade de mensagens de erro impressas por verificação."""

    def __init__(self, rel: Relatorio, limite: int = LIMITE_ERROS_POR_VERIFICACAO) -> None:
        self.rel = rel
        self.limite = limite
        self.total = 0

    def erro(self, msg: str) -> None:
        self.total += 1
        if self.total <= self.limite:
            self.rel.erro(msg)
        else:
            self.rel.erros += 1  # conta, mas não imprime

    def fechar(self) -> None:
        if self.total > self.limite:
            print(f"        ... e mais {self.total - self.limite} erro(s) semelhantes omitidos")


def _decimal(texto: str) -> Optional[Decimal]:
    try:
        valor = Decimal(texto)
    except InvalidOperation:
        return None
    return valor if valor.is_finite() else None


# ---------------------------------------------------------------------------
# Leitura e validação estrutural
# ---------------------------------------------------------------------------
def carregar(saida_dir: Path, nome: str, rel: Relatorio) -> Optional[List[Linha]]:
    """Lê um CSV de saída validando existência, encoding, cabeçalho e nº de colunas.

    Retorna ``None`` se o arquivo for ilegível (erro já reportado).
    """
    caminho = saida_dir / nome
    esperado: List[str] = CONTRATO[nome]["colunas"]  # type: ignore[assignment]
    if not caminho.is_file():
        rel.erro(f"{nome}: arquivo não encontrado em {saida_dir}")
        return None
    bruto = caminho.read_bytes()
    if bruto.startswith(b"\xef\xbb\xbf"):
        rel.erro(f"{nome}: contém BOM UTF-8 (gravar como utf-8 puro)")
        return None
    try:
        texto = bruto.decode("utf-8")
    except UnicodeDecodeError as exc:
        rel.erro(f"{nome}: não é UTF-8 válido ({exc})")
        return None

    leitor = csv.reader(texto.splitlines(), delimiter=SEPARADOR)
    linhas_brutas = list(leitor)
    if not linhas_brutas:
        rel.erro(f"{nome}: arquivo vazio (sem cabeçalho)")
        return None
    cabecalho = linhas_brutas[0]
    if cabecalho != esperado:
        rel.erro(
            f"{nome}: cabeçalho incorreto.\n"
            f"        esperado: {SEPARADOR.join(esperado)}\n"
            f"        obtido:   {SEPARADOR.join(cabecalho)}"
        )
        return None

    linhas: List[Linha] = []
    coletor = Coletor(rel)
    for n, campos in enumerate(linhas_brutas[1:], start=2):
        if not campos:
            continue
        if len(campos) != len(esperado):
            coletor.erro(f"{nome} linha {n}: {len(campos)} colunas, esperado {len(esperado)}")
            continue
        linha = dict(zip(esperado, campos))
        linha["_n"] = str(n)
        linhas.append(linha)
    coletor.fechar()

    if coletor.total == 0:
        rel.ok(f"{nome}: existe, cabeçalho exato, {len(linhas)} linha(s) de dados")
    if not linhas:
        rel.aviso(f"{nome}: sem linhas de dados (esperado enquanto o módulo não for implementado)")
    return linhas


def validar_formatos(nome: str, linhas: List[Linha], rel: Relatorio) -> None:
    """Valida NaN/null, decimais, CNPJ, datas e domínios estritos de um arquivo."""
    contrato = CONTRATO[nome]
    dinheiro: Set[str] = contrato.get("dinheiro", set())  # type: ignore[assignment]
    pct: Set[str] = contrato.get("pct", set())  # type: ignore[assignment]
    razao: Set[str] = contrato.get("razao", set())  # type: ignore[assignment]
    cnpjs: Set[str] = contrato.get("cnpj", set())  # type: ignore[assignment]
    datas: Set[str] = contrato.get("data", set())  # type: ignore[assignment]
    dominios: Dict[str, Set[str]] = contrato.get("dominios", {})  # type: ignore[assignment]
    numericas = dinheiro | pct | razao

    coletor = Coletor(rel)
    for linha in linhas:
        n = linha["_n"]
        for coluna, valor in linha.items():
            if coluna == "_n":
                continue
            if valor.strip().lower() in TOKENS_INVALIDOS:
                coletor.erro(f"{nome} linha {n}: {coluna}={valor!r} (NaN/null proibido)")
            elif coluna in ("id_saida", "ref_origem") and not valor.strip():
                coletor.erro(f"{nome} linha {n}: {coluna} vazio")
        for coluna in numericas:
            valor = linha[coluna]
            if "," in valor:
                coletor.erro(f"{nome} linha {n}: {coluna}={valor!r} usa vírgula (usar ponto decimal)")
            elif coluna in dinheiro and not RE_DINHEIRO.match(valor):
                coletor.erro(f"{nome} linha {n}: {coluna}={valor!r} não é decimal com 2 casas (ex.: 1520.50)")
            elif coluna in pct and not RE_PCT.match(valor):
                coletor.erro(f"{nome} linha {n}: {coluna}={valor!r} não é decimal com ponto")
            elif coluna in razao:
                if not RE_RAZAO.match(valor) or not (Decimal(valor) <= 1):
                    coletor.erro(f"{nome} linha {n}: {coluna}={valor!r} deve estar entre 0 e 1")
        for coluna in cnpjs:
            if not RE_CNPJ.match(linha[coluna]):
                coletor.erro(f"{nome} linha {n}: {coluna}={linha[coluna]!r} não tem exatamente 14 dígitos")
        for coluna in datas:
            valor = linha[coluna]
            if not RE_DATA.match(valor):
                coletor.erro(f"{nome} linha {n}: {coluna}={valor!r} fora do formato AAAA-MM-DD")
            else:
                try:
                    datetime.strptime(valor, "%Y-%m-%d")
                except ValueError:
                    coletor.erro(f"{nome} linha {n}: {coluna}={valor!r} é uma data inexistente")
        for coluna, permitidos in dominios.items():
            if linha[coluna] not in permitidos:
                coletor.erro(
                    f"{nome} linha {n}: {coluna}={linha[coluna]!r} fora do domínio {sorted(permitidos)}"
                )
    coletor.fechar()
    if coletor.total == 0:
        rel.ok(f"{nome}: formatos (decimais, CNPJ, datas, domínios, NaN/null) válidos")


def validar_unicidade_ids(nome: str, linhas: List[Linha], rel: Relatorio) -> None:
    """``id_saida`` não pode se repetir dentro de um mesmo arquivo (exceto rastro)."""
    if nome == RASTRO:
        return
    vistos: Dict[str, str] = {}
    coletor = Coletor(rel)
    for linha in linhas:
        id_saida = linha["id_saida"]
        if id_saida in vistos:
            coletor.erro(f"{nome} linha {linha['_n']}: id_saida {id_saida!r} repetido (primeira vez na linha {vistos[id_saida]})")
        else:
            vistos[id_saida] = linha["_n"]
    coletor.fechar()
    if coletor.total == 0 and linhas:
        rel.ok(f"{nome}: id_saida únicos")


def validar_regras_de_notas(notas: List[Linha], rel: Relatorio) -> None:
    """Guardas de negócio sobre notas: valor > 0 e nota única de remessa para a Ponte."""
    coletor = Coletor(rel)
    remessas = [n for n in notas if n["linha_negocio"] == "REMESSA"]
    for nota in notas:
        valor = _decimal(nota["valor_brl"])
        if valor is not None and valor <= 0:
            coletor.erro(f"{NOTAS} linha {nota['_n']}: nota com valor {nota['valor_brl']} (<= 0 não emite nota)")
    if len(remessas) > 1:
        coletor.erro(f"{NOTAS}: {len(remessas)} notas de REMESSA; o esperado é UMA única nota contra a Ponte Câmbio")
    for nota in remessas:
        if nota["tomador_cnpj"] != PONTE_CAMBIO_CNPJ:
            coletor.erro(f"{NOTAS} linha {nota['_n']}: nota de REMESSA com tomador {nota['tomador_cnpj']} (esperado {PONTE_CAMBIO_CNPJ})")
    coletor.fechar()
    if coletor.total == 0 and notas:
        rel.ok(f"{NOTAS}: valores > 0 e nota única de REMESSA contra a Ponte Câmbio")


# ---------------------------------------------------------------------------
# Auditoria do rastro
# ---------------------------------------------------------------------------
def somar_rastro(rastro: List[Linha], rel: Relatorio) -> Dict[str, Decimal]:
    """Soma ``valor`` por ``id_saida`` e valida campos de origem."""
    somas: Dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    vistos: Set[Tuple[str, str, str]] = set()
    coletor = Coletor(rel)
    duplicadas = 0
    for linha in rastro:
        if not linha["arquivo_origem"].strip():
            coletor.erro(f"{RASTRO} linha {linha['_n']}: arquivo_origem vazio")
        valor = _decimal(linha["valor"])
        if valor is None:
            continue  # já reportado em validar_formatos
        chave = (linha["id_saida"], linha["arquivo_origem"], linha["ref_origem"])
        if chave in vistos:
            duplicadas += 1
        vistos.add(chave)
        somas[linha["id_saida"]] += valor
    coletor.fechar()
    if duplicadas:
        rel.aviso(f"{RASTRO}: {duplicadas} linha(s) repetida(s) (mesmo id_saida/arquivo/ref); confira dupla contagem")
    return dict(somas)


def auditar_rastro(
    comissoes: List[Linha],
    notas: List[Linha],
    lancamentos: List[Linha],
    outros_ids: Set[str],
    somas: Dict[str, Decimal],
    verboso: bool,
    rel: Relatorio,
) -> None:
    """Compara a soma do rastro com o valor reportado em comissões, notas e lançamentos."""
    reportados: List[Tuple[str, str, Decimal]] = []  # (arquivo, id_saida, valor)
    for linha in comissoes:
        valor = _decimal(linha["comissao_brl"])
        if valor is not None:
            reportados.append((COMISSOES, linha["id_saida"], valor))
    for linha in notas:
        valor = _decimal(linha["valor_brl"])
        if valor is not None:
            reportados.append((NOTAS, linha["id_saida"], valor))

    if not reportados:
        rel.aviso("Rastro: nenhuma comissão/nota para auditar (arquivos sem linhas)")

    ok = 0
    coletor = Coletor(rel)
    for arquivo, id_saida, valor in reportados:
        if id_saida not in somas:
            coletor.erro(f"Rastro {id_saida} ({arquivo}): reportado {valor} mas SEM nenhuma linha em {RASTRO}")
        elif somas[id_saida] != valor:
            coletor.erro(
                f"Rastro {id_saida} ({arquivo}): reportado {valor}, soma do rastro {somas[id_saida]} "
                f"(diferença {valor - somas[id_saida]})"
            )
        else:
            ok += 1
            if verboso or ok <= LIMITE_OK_LISTADOS:
                rel.ok(f"Rastro {id_saida} ({arquivo}): {valor} = soma de {RASTRO}")
    coletor.fechar()
    if ok > LIMITE_OK_LISTADOS and not verboso:
        print(f"        ... {ok - LIMITE_OK_LISTADOS} id(s) OK adicionais omitidos (use -v)")
    if reportados:
        resumo = f"Rastro: {ok} de {len(reportados)} id(s) de comissão/nota fecham centavo a centavo"
        (rel.ok if ok == len(reportados) else rel.erro)(resumo)

    # Lançamentos: quando houver rastro, deve fechar com o valor; se não houver, avisa.
    sem_rastro = 0
    coletor_lanc = Coletor(rel)
    for linha in lancamentos:
        valor = _decimal(linha["valor"])
        if valor is None:
            continue
        id_saida = linha["id_saida"]
        if id_saida not in somas:
            sem_rastro += 1
        elif somas[id_saida] != valor:
            coletor_lanc.erro(f"Rastro {id_saida} ({LANCAMENTOS} {linha['ref_origem']}): valor {valor} != rastro {somas[id_saida]}")
    coletor_lanc.fechar()
    if sem_rastro:
        rel.aviso(f"{LANCAMENTOS}: {sem_rastro} lançamento(s) sem linha de rastro")
    elif lancamentos and coletor_lanc.total == 0:
        rel.ok(f"{LANCAMENTOS}: todos os lançamentos têm rastro igual ao valor")

    # Rastro órfão: id que não aparece em nenhum arquivo de saída.
    ids_conhecidos = {i for _, i, _ in reportados} | {l["id_saida"] for l in lancamentos} | outros_ids
    orfaos = sorted(set(somas) - ids_conhecidos)
    if orfaos:
        amostra = ", ".join(orfaos[:5]) + ("..." if len(orfaos) > 5 else "")
        rel.erro(f"{RASTRO}: {len(orfaos)} id_saida sem correspondência em nenhum arquivo de saída ({amostra})")
    elif somas:
        rel.ok(f"{RASTRO}: nenhum id_saida órfão")


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------
def auditar(saida_dir: Path, verboso: bool = False, estrito: bool = False) -> int:
    """Executa a auditoria completa. Retorna o código de saída (0 = ok)."""
    rel = Relatorio()
    print(f"Auditoria de {saida_dir}")

    dados: Dict[str, Optional[List[Linha]]] = {}
    for nome in CONTRATO:
        rel.secao(nome)
        linhas = carregar(saida_dir, nome, rel)
        dados[nome] = linhas
        if linhas:
            validar_formatos(nome, linhas, rel)
            validar_unicidade_ids(nome, linhas, rel)

    rel.secao("Regras de notas")
    if dados[NOTAS]:
        validar_regras_de_notas(dados[NOTAS], rel)  # type: ignore[arg-type]

    rel.secao("Auditoria de rastro (rastro.csv x comissoes x notas)")
    if any(dados[n] is None for n in (COMISSOES, NOTAS, RASTRO)):
        rel.erro("Auditoria de rastro não executada: arquivos obrigatórios ausentes ou ilegíveis")
    else:
        somas = somar_rastro(dados[RASTRO] or [], rel)
        outros_ids = {l["id_saida"] for n in (DIVERGENCIAS, PENDENCIAS) for l in (dados[n] or [])}
        auditar_rastro(
            dados[COMISSOES] or [],
            dados[NOTAS] or [],
            dados[LANCAMENTOS] or [],
            outros_ids,
            somas,
            verboso,
            rel,
        )

    print("\n=== RESUMO ===")
    print(f"Erros: {rel.erros} | Avisos: {rel.avisos}")
    if rel.erros:
        print("[ERRO]  Auditoria REPROVADA")
        return 1
    if estrito and rel.avisos:
        print("[ERRO]  Auditoria reprovada no modo --estrito (há avisos)")
        return 1
    print("[OK]    Auditoria APROVADA" + (" (com avisos)" if rel.avisos else ""))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(errors="replace")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description="Auditoria dos CSVs de saida/ (Desafio Barte AI)")
    parser.add_argument("--saida-dir", default=str(RAIZ / "saida"), help="Pasta com os CSVs gerados")
    parser.add_argument("-v", "--verboso", action="store_true", help="Lista todos os ids do rastro")
    parser.add_argument("--estrito", action="store_true", help="Trata avisos como erros")
    args = parser.parse_args(argv)
    return auditar(Path(args.saida_dir), verboso=args.verboso, estrito=args.estrito)


if __name__ == "__main__":
    sys.exit(main())
