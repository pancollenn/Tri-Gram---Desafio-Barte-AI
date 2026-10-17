#!/usr/bin/env python3
"""Testes unitários automatizados para o motor de rastreabilidade (RastroTracker).

Valida as regras de negócio de `src/engine/rastro.py` e o módulo de compatibilidade
`src/rastro_tracker.py`:
1. Geração sequencial e determinística de id_saida por prefixo.
2. Registro de apontamentos com validação estrita de campos obrigatórios.
3. Proteção contra dízimas / precisão além de centavos (tem_precisao_de_centavos).
4. Prevenção de duplicatas de (id_saida, arquivo_origem, ref_origem) e flag permitir_duplicado.
5. Cálculo de somas acumuladas e consulta de existência de rastro.
6. Validação matemática centavo a centavo (validar_soma e validar_todos).
7. Exportação de `rastro.csv` (delimitador ';', UTF-8, cabeçalho do edital).
8. Compatibilidade de re-exportação pública em `src.rastro_tracker` (__all__).

Uso:
    python tests/test_rastro.py                 # CLI completo com sumário
    python -m unittest tests.test_rastro        # Runner padrão do unittest
"""
from __future__ import annotations

import argparse
import csv
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from typing import Optional

# Garante raiz do repositório no sys.path
_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from src.config import ARQ_RASTRO, ENCODING_CSV, SEPARADOR_CSV
from src.engine.rastro import RastroTracker
import src.rastro_tracker as shim_module


class TestRunner:
    """Coletor e formatador de resultados de testes CLI."""

    def __init__(self, verboso: bool = False):
        self.verboso = verboso
        self.sucessos = 0
        self.falhas = 0

    def asserir(self, condicao: bool, mensagem: str, detalhe: Optional[str] = None) -> None:
        if condicao:
            self.sucessos += 1
            print(f"  [OK]    {mensagem}")
        else:
            self.falhas += 1
            print(f"  [ERRO]  {mensagem}")
            if detalhe:
                print(f"          -> Detalhe: {detalhe}")


# ============================================================================
# 1. TESTES DE GERAÇÃO DE IDS
# ============================================================================
def testar_geracao_ids(runner: TestRunner) -> None:
    print("\n" + "=" * 70)
    print(" 1. GERAÇÃO DETERMINÍSTICA DE ID_SAIDA")
    print("=" * 70)

    tracker = RastroTracker()

    id_com1 = tracker.novo_id("COM")
    id_com2 = tracker.novo_id("COM")
    id_nf1 = tracker.novo_id("NF")
    id_com3 = tracker.novo_id("COM")

    runner.asserir(
        id_com1 == "COM-0001" and id_com2 == "COM-0002" and id_com3 == "COM-0003",
        "Prefixos mantêm contadores sequenciais independentes com 4 dígitos ('COM-0001', 'COM-0002', 'COM-0003')",
        f"Recebido: {id_com1}, {id_com2}, {id_com3}",
    )
    runner.asserir(
        id_nf1 == "NF-0001",
        "Novo prefixo 'NF' inicia contagem em 'NF-0001' sem conflitar com 'COM'",
        f"Recebido: {id_nf1}",
    )
    runner.asserir(
        id_com1 in tracker._ids_emitidos and id_nf1 in tracker._ids_emitidos,
        "IDs gerados são adicionados ao conjunto de controle _ids_emitidos",
    )


# ============================================================================
# 2. TESTES DE REGISTRO E ACUMULAÇÃO
# ============================================================================
def testar_registro_e_acumulacao(runner: TestRunner) -> None:
    print("\n" + "=" * 70)
    print(" 2. REGISTRO DE APONTAMENTOS E ACUMULAÇÃO MATEMÁTICA")
    print("=" * 70)

    tracker = RastroTracker()
    id_com = tracker.novo_id("COM")

    # Registro de duas transações distintas
    tracker.registrar(
        id_saida=id_com,
        arquivo_origem="01_orbe_relatorio_comissoes_set2026.csv",
        ref_origem="TX-1001",
        valor=Decimal("120.50"),
    )
    tracker.registrar(
        id_saida=id_com,
        arquivo_origem="01_orbe_relatorio_comissoes_set2026.csv",
        ref_origem="TX-1002",
        valor="79.50",  # aceita string numérica
    )

    runner.asserir(
        tracker.possui_rastro(id_com),
        f"possui_rastro('{id_com}') retorna True após registros",
    )
    runner.asserir(
        not tracker.possui_rastro("COM-9999"),
        "possui_rastro('COM-9999') retorna False para id não registrado",
    )
    runner.asserir(
        tracker.total(id_com) == Decimal("200.00"),
        f"total('{id_com}') calcula a soma acumulada exata em Decimal (120.50 + 79.50 = 200.00)",
        f"Total obtido: {tracker.total(id_com)}",
    )
    runner.asserir(
        tracker.total("COM-9999") == Decimal("0.00"),
        "total('COM-9999') retorna Decimal('0.00') para id inexistente",
    )

    # Imutabilidade da lista de linhas
    linhas = tracker.linhas
    runner.asserir(
        len(linhas) == 2,
        f"Propriedade linhas retorna exatamente as 2 entradas registradas",
    )
    runner.asserir(
        linhas[0]["valor"] == "120.50" and linhas[1]["valor"] == "79.50",
        "Valores em linhas são formatados com 2 casas decimais e ponto ('120.50', '79.50')",
    )
    linhas.clear()
    runner.asserir(
        len(tracker.linhas) == 2,
        "Modificação na lista retornada pela propriedade .linhas não afeta o estado interno",
    )


# ============================================================================
# 3. TESTES DE RESILIÊNCIA, PREVENÇÃO DE DUPLICATAS E CASOS DE BORDA
# ============================================================================
def testar_resiliencia_e_excecoes(runner: TestRunner) -> None:
    print("\n" + "=" * 70)
    print(" 3. RESILIÊNCIA, VALIDAÇÃO DE CAMPOS E DUPLICATAS")
    print("=" * 70)

    tracker = RastroTracker()
    id_saida = tracker.novo_id("PEN")

    # 1. Campos obrigatórios vazios
    erros_campos = 0
    for args in [
        ("", "arquivo.csv", "REF-1", Decimal("10.00")),
        (id_saida, "", "REF-1", Decimal("10.00")),
        (id_saida, "arquivo.csv", "", Decimal("10.00")),
        (id_saida, "arquivo.csv", "   ", Decimal("10.00")),
    ]:
        try:
            tracker.registrar(*args)
        except ValueError:
            erros_campos += 1

    runner.asserir(
        erros_campos == 4,
        "Lança ValueError quando id_saida, arquivo_origem ou ref_origem estão vazios ou em branco",
        f"Erros capturados: {erros_campos}/4",
    )

    # 2. Precisão decimal além de centavos (sem arredondamento prévio)
    disparou_precisao = False
    try:
        tracker.registrar(id_saida, "arquivo.csv", "REF-A", Decimal("10.123"))
    except ValueError as exc:
        disparou_precisao = "mais de 2 casas" in str(exc)

    runner.asserir(
        disparou_precisao,
        "Rejeita valor com mais de 2 casas decimais sem arredondamento com ValueError explícito",
    )

    # 3. Prevenção de duplicatas por padrão (permitir_duplicado=False)
    tracker.registrar(id_saida, "arquivo.csv", "REF-DUPL", Decimal("50.00"))
    bloqueou_duplicata = False
    try:
        tracker.registrar(id_saida, "arquivo.csv", "REF-DUPL", Decimal("50.00"), permitir_duplicado=False)
    except ValueError as exc:
        bloqueou_duplicata = "Linha de origem já registrada" in str(exc)

    runner.asserir(
        bloqueou_duplicata,
        "Bloqueia duplicata de (id_saida, arquivo_origem, ref_origem) com ValueError",
    )

    # 4. Aceitação explícita com permitir_duplicado=True
    aceitou_duplicado = False
    try:
        tracker.registrar(id_saida, "arquivo.csv", "REF-DUPL", Decimal("25.00"), permitir_duplicado=True)
        aceitou_duplicado = tracker.total(id_saida) == Decimal("75.00")
    except Exception:
        aceitou_duplicado = False

    runner.asserir(
        aceitou_duplicado,
        "Permite repetição de ref_origem quando permitir_duplicado=True e acumula soma (50.00 + 25.00 = 75.00)",
    )


# ============================================================================
# 4. TESTES DE VALIDAÇÃO MATEMÁTICA CENTAVO A CENTAVO
# ============================================================================
def testar_validacao_soma(runner: TestRunner) -> None:
    print("\n" + "=" * 70)
    print(" 4. VALIDAÇÃO MATEMÁTICA CENTAVO A CENTAVO (validar_soma / validar_todos)")
    print("=" * 70)

    tracker = RastroTracker()
    id_saida = tracker.novo_id("DIV")

    tracker.registrar(id_saida, "arquivo.csv", "REF-1", Decimal("100.25"))
    tracker.registrar(id_saida, "arquivo.csv", "REF-2", Decimal("49.75"))
    # Soma total = 150.00

    # 1. Validação com valor exato (deve passar sem exceção)
    passou_exato = False
    try:
        tracker.validar_soma(id_saida, Decimal("150.00"))
        tracker.validar_soma(id_saida, "150.00")
        passou_exato = True
    except AssertionError:
        passou_exato = False

    runner.asserir(
        passou_exato,
        "validar_soma() passa com sucesso quando a soma do rastro bate centavo a centavo (150.00)",
    )

    # 2. Validação com divergência de centavos (deve falhar)
    falhou_divergencia = False
    try:
        tracker.validar_soma(id_saida, Decimal("150.01"))
    except AssertionError as exc:
        falhou_divergencia = "diferença 0.01" in str(exc)

    runner.asserir(
        falhou_divergencia,
        "validar_soma() dispara AssertionError detalhando a diferença ao divergir em 1 centavo (150.01 vs 150.00)",
    )

    # 3. Validação em id sem rastro
    falhou_sem_rastro = False
    try:
        tracker.validar_soma("DIV-9999", Decimal("100.00"))
    except AssertionError as exc:
        falhou_sem_rastro = "sem nenhuma linha de rastro" in str(exc)

    runner.asserir(
        falhou_sem_rastro,
        "validar_soma() dispara AssertionError quando id_saida não possui linhas no rastro",
    )

    # 4. validar_todos em lote
    id_ok = tracker.novo_id("DIV")
    tracker.registrar(id_ok, "arquivo.csv", "REF-OK", Decimal("30.00"))

    falhou_todos = False
    try:
        tracker.validar_todos({
            id_saida: Decimal("150.05"),  # divergente
            id_ok: Decimal("30.00"),      # correto
            "DIV-8888": Decimal("10.00"), # inexistente
        })
    except AssertionError as exc:
        msg = str(exc)
        falhou_todos = "2 id(s) de saída não fecham" in msg and id_saida in msg and "DIV-8888" in msg

    runner.asserir(
        falhou_todos,
        "validar_todos() agrega e reporta todas as falhas conjuntas em uma única AssertionError",
    )


# ============================================================================
# 5. TESTES DE EXPORTAÇÃO CSV E COMPATIBILIDADE SHIM
# ============================================================================
def testar_exportacao_e_compatibilidade(runner: TestRunner) -> None:
    print("\n" + "=" * 70)
    print(" 5. EXPORTAÇÃO CSV E SHIM DE COMPATIBILIDADE")
    print("=" * 70)

    tracker = RastroTracker()
    id_saida = tracker.novo_id("COM")
    tracker.registrar(id_saida, "01_orbe.csv", "TX-1", Decimal("350.40"))
    tracker.registrar(id_saida, "01_orbe.csv", "TX-2", Decimal("-50.40"))

    with tempfile.TemporaryDirectory() as tmp_dir:
        pasta = Path(tmp_dir)

        # 1. Exportação passando diretório (deve criar rastro.csv automaticamente)
        caminho_gerado = tracker.exportar_csv(pasta)
        runner.asserir(
            caminho_gerado.exists() and caminho_gerado.name == ARQ_RASTRO,
            f"exportar_csv(pasta) grava o arquivo padrão '{ARQ_RASTRO}' no diretório informado",
        )

        with open(caminho_gerado, "r", encoding=ENCODING_CSV) as f:
            leitor = csv.reader(f, delimiter=SEPARADOR_CSV)
            linhas_csv = list(leitor)

        runner.asserir(
            linhas_csv[0] == ["id_saida", "arquivo_origem", "ref_origem", "valor"],
            "Cabeçalho do CSV segue estritamente o edital: ['id_saida', 'arquivo_origem', 'ref_origem', 'valor']",
            f"Recebido: {linhas_csv[0]}",
        )
        runner.asserir(
            len(linhas_csv) == 3,  # cabeçalho + 2 linhas
            "CSV contém exatamente o cabeçalho mais as 2 linhas de dados registradas",
        )
        runner.asserir(
            linhas_csv[1] == [id_saida, "01_orbe.csv", "TX-1", "350.40"]
            and linhas_csv[2] == [id_saida, "01_orbe.csv", "TX-2", "-50.40"],
            "Valores preservam sinal e formato BRL com 2 casas ('350.40', '-50.40')",
        )

    # 2. Validação do shim src/rastro_tracker.py
    runner.asserir(
        shim_module.RastroTracker is RastroTracker,
        "src.rastro_tracker reexporta exatamente a mesma classe RastroTracker de src.engine.rastro",
    )
    runner.asserir(
        getattr(shim_module, "__all__", None) == ["RastroTracker"],
        "src.rastro_tracker define __all__ = ['RastroTracker'] para exportação pública e suporte a linters",
    )


# ============================================================================
# 6. CASOS DE TESTE COMPATÍVEIS COM UNITTEST (python -m unittest)
# ============================================================================
class TestRastroUnitario(unittest.TestCase):
    """Integração com o test runner nativo do Python (unittest)."""

    def setUp(self) -> None:
        self.runner = TestRunner(verboso=False)

    def test_geracao_ids(self) -> None:
        testar_geracao_ids(self.runner)
        self.assertEqual(self.runner.falhas, 0, f"{self.runner.falhas} falha(s) na geração de IDs")

    def test_registro_e_acumulacao(self) -> None:
        testar_registro_e_acumulacao(self.runner)
        self.assertEqual(self.runner.falhas, 0, f"{self.runner.falhas} falha(s) no registro e acumulação")

    def test_resiliencia_e_excecoes(self) -> None:
        testar_resiliencia_e_excecoes(self.runner)
        self.assertEqual(self.runner.falhas, 0, f"{self.runner.falhas} falha(s) em resiliência e exceções")

    def test_validacao_soma(self) -> None:
        testar_validacao_soma(self.runner)
        self.assertEqual(self.runner.falhas, 0, f"{self.runner.falhas} falha(s) na validação de soma")

    def test_exportacao_e_compatibilidade(self) -> None:
        testar_exportacao_e_compatibilidade(self.runner)
        self.assertEqual(self.runner.falhas, 0, f"{self.runner.falhas} falha(s) na exportação e shim")


# ============================================================================
# 7. PONTO DE ENTRADA CLI
# ============================================================================
def main() -> int:
    parser = argparse.ArgumentParser(description="Testes unitários de rastro.py e rastro_tracker.py")
    parser.add_argument("-v", "--verboso", action="store_true", help="Imprime detalhes dos testes")
    args = parser.parse_args()

    runner = TestRunner(verboso=args.verboso)

    testar_geracao_ids(runner)
    testar_registro_e_acumulacao(runner)
    testar_resiliencia_e_excecoes(runner)
    testar_validacao_soma(runner)
    testar_exportacao_e_compatibilidade(runner)

    print("\n" + "=" * 70)
    print(f" RESUMO DOS TESTES: {runner.sucessos} SUCESSOS, {runner.falhas} FALHAS")
    print("=" * 70)

    if runner.falhas == 0:
        print("  >>> TODOS OS TESTES PASSARAM COM SUCESSO! <<<\n")
        return 0
    else:
        print(f"  >>> ATENÇÃO: {runner.falhas} TESTE(S) FALHARAM! <<<\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
