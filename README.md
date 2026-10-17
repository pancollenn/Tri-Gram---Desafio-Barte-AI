# Tarvo Pagamentos: fechamento de setembro/2026 (Desafio Barte AI)

Time **Tri-Gram**. Solução que automatiza o fechamento mensal da Tarvo (checkout, remessas e conciliação bancária), com **todo número rastreável até a linha de origem**.

## Visão geral da arquitetura (híbrida)

```
                    arquivos brutos (CSV, XLSX, EML, OFX)
                                     │
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │ 1. INGESTÃO (src/parsers/): parse_orbe, parse_ponte, parse_extratos    │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │ dados tipados (Decimal)
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │ 2. REGRAS & CÁLCULOS (src/engine/):                                    │
 │    • comissoes.py    ➔ comissoes_por_lojista.csv                       │
 │    • divergencias.py ➔ divergencias_taxa.csv                           │
 │    • notas.py        ➔ notas_a_emitir.csv                              │
 │    • pendencias.py   ➔ pendencias.csv                                  │
 │    • rastro.py       ➔ rastro.csv (RastroTracker em memória)           │
 ├────────────────────────────────────────────────────────────────────────┤
 │ 3. IA & CLASSIFICAÇÃO (src/ai/):                                       │
 │    • classifier.py   ➔ lancamentos_classificados.csv (Regra + LLM)     │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │ validação matemática
                                     ▼
      src/main.py ➔ saida/*.csv (6 arquivos) ➔ tests/validate_saida.py
```

- **Números (comissões, divergências, notas): 100% código determinístico.** Nenhuma IA calcula dinheiro, pois LLMs erram somas de centavos e quebram o rastro.
- **IA apenas onde há ambiguidade semântica** (classificação de lançamentos bancários atípicos, `metodo=IA` com `confianca < 1`) e como ferramenta de desenvolvimento. Sem chave de API, a solução roda por inteiro (fallback gracioso por regras).
- **Rastro**: `rastro.csv` liga cada número de saída às linhas de origem; a soma de `valor` por `id_saida` fecha centavo a centavo (validada em `main.py` e em `tests/validate_saida.py`).

## Requisitos do Sistema

### 1. Ambiente de Execução
- **Python**: versão **3.9 ou superior** (desenvolvido e homologado em Python 3.12).
- **Sistema Operacional**: compatível com Linux, macOS e Windows.

### 2. Dependências de Pacotes Python
A solução foi arquitetada para ser leve e resiliente, dependendo externamente apenas do leitor de planilhas:
- **`openpyxl>=3.1`**: obrigatório para leitura e extração das planilhas `.xlsx` (tabela de taxas contratuais e borderô anexo do e-mail de câmbio).
- Todas as demais funcionalidades utilizam exclusivamente a **biblioteca padrão do Python** (`decimal` para aritmética financeira exata, `email` para extração MIME in-memory, `csv`, `pathlib`, `datetime`, `argparse`, `unittest`).

```bash
# Criação do ambiente virtual (recomendado)
python -m venv .venv

# Ativação do ambiente
# Linux/macOS:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Windows (CMD):
.venv\Scripts\activate.bat

# Instalação das dependências
pip install -r requirements.txt
```

### 3. Dados de Entrada
- Ter os arquivos brutos do fechamento posicionados na pasta `data_pack/` (padrão nativo do repositório) ou `data/`.
- Alternativamente, o caminho pode ser informado via argumento `--data-dir <caminho>` ou pela variável de ambiente `TARVO_DATA_DIR`.

### 4. Acesso a APIs / Conectividade
- **Nenhuma chave de API ou conexão à internet é obrigatória**. O pipeline é 100% autossuficiente em ambiente local e offline.
- A camada de classificação contábil (`classifier.py`) opera com regras determinísticas e fallback gracioso sem depender de provedores externos de LLM.

## Execução (comando único)

Para rodar o pipeline completo de ponta a ponta:

```bash
python src/main.py                 # gera os 6 CSVs em saida/ e audita ao final
python tests/validate_saida.py     # auditoria isolada dos arquivos de saida/
```

Esse comando único realiza todo o fluxo:
1. **Ingestão automática** dos arquivos brutos (localizados automaticamente em `data_pack/`, `data/` ou `Tarvo_Data_Pack_set2026/`);
2. **Cálculo determinístico** de comissões, divergências, notas fiscais e pendências;
3. **Classificação contábil** dos extratos bancários no ERP Fênix;
4. **Validação centavo a centavo** do `rastro.csv`;
5. **Gravação dos 6 arquivos CSV** em `saida/`;
6. **Disparo automático da auditoria cega** (`tests/validate_saida.py`).

A pasta de entrada é procurada nesta ordem: `--data-dir` > variável `TARVO_DATA_DIR` > `data_pack/` > `data/` > `Tarvo_Data_Pack_set2026/` (na raiz do repositório ou ao lado dele). Copie os arquivos do data pack, **sem editar**, para `data/` ou utilize o `data_pack/` já presente na raiz.

Opções úteis para execução e desenvolvimento em paralelo:

```bash
python src/main.py --modulos checkout          # roda só o módulo da sua responsabilidade (ex.: Checkout)
python src/main.py --data-dir C:\caminho\dados --saida-dir C:\tmp\saida
python tests/validate_saida.py -v              # lista todos os ids do rastro individualmente
python tests/validate_saida.py --estrito       # modo estrito: avisos viram erro
python -m unittest discover -s tests -p "test_*.py" # executa a suíte de testes unitários e de integração
```

Códigos de saída do `main.py`: `0` ok · `1` rastro/validação falhou · `2` erro de entrada ou de dados.

## Estrutura do projeto

| Caminho | Responsabilidade / Entregável | Dono |
|---|---|---|
| `src/config.py` | Configurações centrais, CNPJs, contratos dos 6 CSVs e regras do Slack | Compartilhado |
| `src/parsers/parse_orbe.py` | Leitura da Orbe e Tabela de Taxas vigentes | Pessoa 1 |
| `src/parsers/parse_ponte.py` | Extração do anexo `.xlsx` do e-mail `.eml` da Ponte Câmbio | Pessoa 2 |
| `src/parsers/parse_extratos.py` | Leitura dos extratos Aurora (`CSV`), Meridiano (`OFX`) e Plano Fênix | Pessoa 2 |
| `src/engine/comissoes.py` | ➔ Gera `comissoes_por_lojista.csv` (Checkout + Câmbio) | Pessoa 1 & 2 |
| `src/engine/divergencias.py` | ➔ Gera `divergencias_taxa.csv` (Orbe + Ponte Câmbio) | Pessoa 1 & 2 |
| `src/engine/notas.py` | ➔ Gera `notas_a_emitir.csv` (NFS-e lojistas e Nota Única Ponte) | Pessoa 2 |
| `src/engine/pendencias.py` | ➔ Gera `pendencias.csv` (as 7 anomalias catalogadas) | Pessoa 2 |
| `src/engine/rastro.py` | `RastroTracker` e ➔ grava `rastro.csv` (centavo a centavo) | Pessoa 1 |
| `src/ai/classifier.py` | ➔ Gera `lancamentos_classificados.csv` no ERP (Regra + IA) | Pessoa 2 / 3 |
| `src/main.py` | Orquestrador principal do pipeline | Compartilhado |
| `tests/validate_saida.py` | Auditoria cega dos arquivos de `saida/` (independente de `src/`) | Pessoa 3 (QA) |
| `saida/` | Os 6 CSVs gerados (entregáveis oficiais da banca) | Pipeline |
| `HIPOTESES.md`, `PROMPTS/`, `README.md` | Documentação formal e logs de IA exigidos pelo edital | Pessoa 3 |

Contrato de integração: cada módulo expõe uma função `processar_*(data_dir, tracker)` e devolve listas de dicionários com as chaves exatas dos cabeçalhos (`config.ARQUIVOS_SAIDA`). O `main.py` só chama, formata e grava; assim ninguém edita o arquivo de outra pessoa.

### Arquivos de saída (`saida/`, `;` como separador, ponto decimal, `AAAA-MM-DD`, CNPJ com 14 dígitos)

| Arquivo | Colunas |
|---|---|
| `comissoes_por_lojista.csv` | `id_saida;cnpj;lojista;linha_negocio;comissao_brl` |
| `divergencias_taxa.csv` | `id_saida;cnpj;linha_negocio;ref_origem;taxa_contratada_pct;taxa_aplicada_pct;diferenca_brl` |
| `notas_a_emitir.csv` | `id_saida;tomador_cnpj;tomador;linha_negocio;valor_brl;discriminacao` |
| `lancamentos_classificados.csv` | `id_saida;banco;ref_origem;data;descricao;valor;conta_codigo;metodo;confianca` |
| `pendencias.csv` | `id_saida;tipo;ref_origem;valor_brl;motivo;quem_decide` |
| `rastro.csv` | `id_saida;arquivo_origem;ref_origem;valor` |

## Variáveis de ambiente

| Variável | Uso | Obrigatória |
|---|---|---|
| `TARVO_DATA_DIR` | Pasta com os arquivos brutos (alternativa a `--data-dir`) | Não |
| `TARVO_SAIDA_DIR` | Pasta de saída (padrão: `saida/`) | Não |

Nenhuma chave de API é necessária para rodar. Se a camada opcional de IA for adicionada, a chave deve vir de variável de ambiente (`.env` está no `.gitignore`); **nunca** versione chaves.

## Resultados Consolidados do Fechamento (Setembro/2026)

Execução completa e validada com **zero erros e zero avisos** no auditor cego estrito (`python tests/validate_saida.py --estrito`):

| Entregável Oficial (`saida/*.csv`) | Registros Gerados | Montante Financeiro / Métrica | Nível de Entrega |
|---|---|---|---|
| `comissoes_por_lojista.csv` | 35 lojistas | **R$ 243.284,29** (Checkout: R$ 203.740,84 · Remessas: R$ 39.543,45) | Mínimo / Alvo ✅ |
| `divergencias_taxa.csv` | 238 divergências | **R$ 16.574,47** em cobranças incorretas de adquirente e parceiros | Alvo ✅ |
| `notas_a_emitir.csv` | 21 notas fiscais | **R$ 243.284,29** (20 NFS-e lojistas Checkout + 1 Nota Única Ponte Câmbio) | Alvo ✅ |
| `lancamentos_classificados.csv` | 184 lançamentos | 100% dos extratos Aurora (CC 4471) e Meridiano (CC 90233) classificados no Fênix | Alvo ✅ |
| `pendencias.csv` | 7 pendências | As 7 anomalias catalogadas com decisores atribuídos (Helena/Diego) | Extra ✅ |
| `rastro.csv` | 4.765 apontamentos | **56 de 56 IDs** de comissão/nota fecham centavo a centavo com origem | Central (Eliminatório) ✅ |

## Maturidade e Conformidade com o Edital

- **Nível Mínimo:** 100% concluído (Comissões de checkout por lojista apuradas pela taxa contratada com rastro atômico).
- **Nível Alvo:** 100% concluído (Comissões de ambas as linhas de negócio, divergências de taxa, notas a emitir com tomadores estritos e classificação contábil híbrida nos extratos bancários).
- **Nível Extra:** 100% concluído (Rastro completo para todos os números, governança e triagem das 7 pendências para deliberação humana e generalização dinâmica para execução de outubro sem alteração de código).

## Limitações conhecidas e salvaguardas de governança

- Os arquivos de entrada são localizados por padrão de nome (`config.PADROES_ENTRADA` via `glob`); se houver mais de um arquivo para o mesmo padrão em um mesmo diretório, o pipeline aborta em vez de escolher no chute.
- O casamento de lojistas é executado estritamente por **código (EC) e CNPJ sanitizado (14 dígitos)**, nunca por similaridade imprecisa de texto.
- Transações de estabelecimentos sem contrato assinado em 2026 (Atlas Idiomas) e exceções comerciais (tarifa zero da Casa do Estudante) não geram notas indevidas e são encaminhadas para `pendencias.csv` com seus respectivos decisores humanos (`Financeiro Tarvo (Helena)` ou `Comercial Tarvo (Diego)`).
- `tests/validate_saida.py` confere formato estrito e consistência matemática interna (rastro x saída) de forma desacoplada e independente de `src/`.

## Documentação adicional

- [`HIPOTESES.md`](HIPOTESES.md): regras confirmadas com o financeiro, premissas assumidas e perguntas feitas.
- [`especificacao_scripts.md`](especificacao_scripts.md): contratos técnicos, fluxo arquitetural e detalhamento dos componentes.
- [`PROMPTS/MOMENTOS.md`](PROMPTS/MOMENTOS.md): momentos críticos do uso de IA e histórico das sessões.
