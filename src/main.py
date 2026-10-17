"""Orquestrador do pipeline de fechamento (Tarvo Pagamentos, setembro/2026).

Uso::

    python src/main.py                      # roda tudo e valida ao final
    python src/main.py --data-dir <pasta>   # pasta com os arquivos brutos
    python src/main.py --modulos checkout   # roda só parte (desenvolvimento em paralelo)

Estrutura em 3 camadas:
    1. Ingestão: src/parsers/ (parse_orbe, parse_ponte, parse_extratos)
    2. Engine:   src/engine/ (comissoes, divergencias, notas, pendencias, rastro)
    3. AI:       src/ai/ (classifier)

Códigos de saída: 0 = ok; 1 = rastro/validação falhou; 2 = erro de entrada/dados.
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

# Permite `python src/main.py` a partir de qualquer diretório de trabalho.
_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from src.ai import classifier  # noqa: E402
from src.config import (  # noqa: E402
    ARQ_COMISSOES,
    ARQ_DIVERGENCIAS,
    ARQ_LANCAMENTOS,
    ARQ_NOTAS,
    ARQ_PENDENCIAS,
    ARQUIVOS_SAIDA,
    ENCODING_CSV,
    SEPARADOR_CSV,
    ArquivoSaida,
    Linha,
    clean_cnpj,
    format_brl,
    format_pct,
    para_decimal,
    parse_data_ptbr,
    resolver_data_dir,
    resolver_saida_dir,
    tem_precisao_de_centavos,
)
from src.engine import comissoes, divergencias, notas, pendencias, rastro  # noqa: E402
from src.engine.rastro import RastroTracker  # noqa: E402
from src.parsers import parse_extratos, parse_orbe, parse_ponte  # noqa: E402

MODULOS_DISPONIVEIS = ("checkout", "remessas", "bancos")
SCRIPT_VALIDACAO = _RAIZ / "tests" / "validate_saida.py"


# ---------------------------------------------------------------------------
# Serialização dos CSVs
# ---------------------------------------------------------------------------
def _formatar_celula(spec: ArquivoSaida, coluna: str, valor: object) -> str:
    """Converte um valor de domínio para o texto exigido pelo contrato."""
    if valor is None:
        raise ValueError("valor None não permitido (use texto vazio ou 0.00 explicitamente)")
    if coluna in spec.monetarias:
        if not tem_precisao_de_centavos(valor):  # type: ignore[arg-type]
            raise ValueError(f"valor monetário com mais de 2 casas: {valor!r} (arredonde antes)")
        return format_brl(valor)  # type: ignore[arg-type]
    if coluna in spec.percentuais:
        return format_pct(valor)  # type: ignore[arg-type]
    if coluna in spec.cnpj:
        return clean_cnpj(valor)  # type: ignore[arg-type]
    if coluna in spec.datas:
        return parse_data_ptbr(valor)  # type: ignore[arg-type]
    if coluna in spec.razoes:
        razao = para_decimal(valor)  # type: ignore[arg-type]
        if not 0 <= razao <= 1:
            raise ValueError(f"confianca fora de [0, 1]: {valor!r}")
        return format_pct(razao)
    return str(valor)


def _serializar(spec: ArquivoSaida, linhas: Sequence[Linha]) -> List[Dict[str, str]]:
    """Valida chaves e formata todas as linhas de um arquivo de saída."""
    saida: List[Dict[str, str]] = []
    for indice, linha in enumerate(linhas, start=1):
        faltando = [c for c in spec.colunas if c not in linha]
        if faltando:
            raise ValueError(f"{spec.nome} linha {indice}: faltam colunas {faltando}")
        try:
            saida.append({c: _formatar_celula(spec, c, linha[c]) for c in spec.colunas})
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{spec.nome} linha {indice} (id_saida={linha.get('id_saida')}): {exc}") from exc
    return saida


def _gravar_csv(spec: ArquivoSaida, linhas: Sequence[Dict[str, str]], saida_dir: Path) -> Path:
    destino = saida_dir / spec.nome
    with open(destino, "w", encoding=ENCODING_CSV, newline="") as arq:
        escritor = csv.DictWriter(
            arq, fieldnames=spec.colunas, delimiter=SEPARADOR_CSV, lineterminator="\n"
        )
        escritor.writeheader()
        escritor.writerows(linhas)
    return destino


# ---------------------------------------------------------------------------
# Pipeline Modular
# ---------------------------------------------------------------------------
def executar_pipeline(
    data_dir: Path, tracker: RastroTracker, modulos: Sequence[str]
) -> Dict[str, List[Linha]]:
    """Executa o pipeline em camadas e consolida as linhas por arquivo de saída."""
    consolidado: Dict[str, List[Linha]] = {
        ARQ_COMISSOES: [],
        ARQ_DIVERGENCIAS: [],
        ARQ_NOTAS: [],
        ARQ_LANCAMENTOS: [],
        ARQ_PENDENCIAS: [],
    }

    dados_checkout = {}
    dados_remessas = {}
    dados_extratos = {}

    # 1. Ingestão (src/parsers/)
    if "checkout" in modulos:
        print("[main] [1/3 Ingestão] Lendo dados de Checkout (parse_orbe)...")
        dados_checkout = parse_orbe.parse_orbe_e_taxas(data_dir)

    if "remessas" in modulos:
        print("[main] [1/3 Ingestão] Lendo dados de Remessas (parse_ponte)...")
        dados_remessas = parse_ponte.parse_ponte_e_taxas(data_dir)

    if "bancos" in modulos:
        print("[main] [1/3 Ingestão] Lendo extratos bancários e plano ERP (parse_extratos)...")
        dados_extratos = parse_extratos.parse_extratos_e_plano(data_dir)

    # 2. Regras Determinísticas e Cálculos Financeiros (src/engine/)
    if "checkout" in modulos or "remessas" in modulos:
        print("[main] [2/3 Engine] Calculando comissões (comissoes.py)...")
        comissoes_linhas = comissoes.calcular_comissoes(dados_checkout, dados_remessas, tracker)
        consolidado[ARQ_COMISSOES].extend(comissoes_linhas)

        print("[main] [2/3 Engine] Apurando divergências de taxas (divergencias.py)...")
        divergencias_linhas = divergencias.apurar_divergencias(dados_checkout, dados_remessas, tracker)
        consolidado[ARQ_DIVERGENCIAS].extend(divergencias_linhas)

        print("[main] [2/3 Engine] Gerando faturamento e notas fiscais (notas.py)...")
        notas_linhas = notas.gerar_notas_a_emitir(comissoes_linhas, dados_checkout, dados_remessas, tracker)
        consolidado[ARQ_NOTAS].extend(notas_linhas)

    # 3. Classificação Contábil Inteligente (src/ai/)
    if "bancos" in modulos:
        print("[main] [3/3 AI] Classificando extratos bancários no ERP (classifier.py)...")
        lancamentos_linhas = classifier.classificar_lancamentos(dados_extratos, tracker)
        consolidado[ARQ_LANCAMENTOS].extend(lancamentos_linhas)

    # 4. Governança e Triagem de Pendências
    print("[main] [Governança] Consolidando pendências operacionais (pendencias.py)...")
    pendencias_linhas = pendencias.consolidar_pendencias(dados_checkout, dados_remessas, dados_extratos, tracker)
    consolidado[ARQ_PENDENCIAS].extend(pendencias_linhas)

    return consolidado


def _validar_rastro(tracker: RastroTracker, consolidado: Dict[str, List[Linha]]) -> Optional[str]:
    """Confere o rastro contra comissões e notas. Retorna a mensagem de erro, se houver."""
    reportados: Dict[str, object] = {}
    for linha in consolidado[ARQ_COMISSOES]:
        reportados[linha["id_saida"]] = linha["comissao_brl"]
    for linha in consolidado[ARQ_NOTAS]:
        reportados[linha["id_saida"]] = linha["valor_brl"]
    try:
        tracker.validar_todos(reportados)  # type: ignore[arg-type]
    except AssertionError as exc:
        return str(exc)
    print(f"[main] Rastro OK: {len(reportados)} id(s) de comissao/nota fecham centavo a centavo.")
    return None


def _rodar_validacao(saida_dir: Path, estrito: bool) -> int:
    comando: List[str] = [sys.executable, str(SCRIPT_VALIDACAO), "--saida-dir", str(saida_dir)]
    if estrito:
        comando.append("--estrito")
    print("[main] Executando auditoria (tests/validate_saida.py) ...")
    sys.stdout.flush()
    return subprocess.call(comando)


def main(argv: Optional[Sequence[str]] = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(errors="replace")  # type: ignore[union-attr]

    parser = argparse.ArgumentParser(description="Fechamento Tarvo Pagamentos (Desafio Barte AI)")
    parser.add_argument("--data-dir", help="Pasta com os arquivos brutos (ou TARVO_DATA_DIR)")
    parser.add_argument("--saida-dir", help="Pasta de saída (padrão: saida/ ou TARVO_SAIDA_DIR)")
    parser.add_argument(
        "--modulos",
        default=",".join(MODULOS_DISPONIVEIS),
        help="Lista separada por vírgula: " + ",".join(MODULOS_DISPONIVEIS),
    )
    parser.add_argument("--sem-validacao", action="store_true", help="Não executa a auditoria final")
    parser.add_argument("--estrito", action="store_true", help="Auditoria trata avisos como erros")
    args = parser.parse_args(argv)

    modulos = [m.strip() for m in args.modulos.split(",") if m.strip()]
    desconhecidos = [m for m in modulos if m not in MODULOS_DISPONIVEIS]
    if desconhecidos:
        print(f"[ERRO] Módulo(s) desconhecido(s): {desconhecidos}", file=sys.stderr)
        return 2

    try:
        data_dir = resolver_data_dir(args.data_dir)
        saida_dir = resolver_saida_dir(args.saida_dir)
    except FileNotFoundError as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        return 2
    print(f"[main] Entrada: {data_dir}\n[main] Saida:   {saida_dir}")

    tracker = RastroTracker()
    try:
        consolidado = executar_pipeline(data_dir, tracker, modulos)
        arquivos: Dict[str, List[Dict[str, str]]] = {
            nome: _serializar(ARQUIVOS_SAIDA[nome], linhas) for nome, linhas in consolidado.items()
        }
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"[ERRO] Falha no processamento: {exc}", file=sys.stderr)
        return 2

    # Rastro: valida ANTES de gravar, mas grava mesmo se falhar (facilita depuração).
    erro_rastro = _validar_rastro(tracker, consolidado)
    for nome, linhas in arquivos.items():
        _gravar_csv(ARQUIVOS_SAIDA[nome], linhas, saida_dir)
        print(f"[main] {nome}: {len(linhas)} linha(s)")
    tracker.exportar_csv(saida_dir)
    print(f"[main] rastro.csv: {len(tracker.linhas)} linha(s)")

    codigo = 0
    if erro_rastro:
        print(f"[ERRO] Rastro nao fecha:\n  {erro_rastro}", file=sys.stderr)
        codigo = 1
    if not args.sem_validacao and _rodar_validacao(saida_dir, args.estrito) != 0:
        codigo = 1
    print("[main] Concluido com sucesso." if codigo == 0 else "[main] Concluido COM ERROS.")
    return codigo


if __name__ == "__main__":
    sys.exit(main())
