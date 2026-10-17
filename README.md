# Tarvo Pagamentos: fechamento de setembro/2026 (Desafio Barte AI)

Time **Tri-Gram**. Solução que automatiza o fechamento mensal da Tarvo (checkout, remessas e conciliação bancária), com **todo número rastreável até a linha de origem**.

## Visão geral da arquitetura (híbrida)

```
 arquivos brutos (CSV, XLSX, EML, OFX)
            │
            ▼
 ┌──────────────────────────────┐   dinheiro = código determinístico
 │ src/checkout.py   (Orbe)     │   (Decimal, ROUND_HALF_UP, regras
 │ src/remessas.py   (Ponte)    │    confirmadas com o financeiro)
 │ src/bancos.py  (Aurora/Mer.) │
 └──────────────┬───────────────┘
                │  cada número → RastroTracker (src/rastro_tracker.py)
                ▼
 src/main.py → saida/*.csv (6 arquivos) → tests/validate_saida.py (auditoria)
```

- **Números (comissões, divergências, notas): 100% código determinístico.** Nenhuma IA calcula dinheiro, pois LLMs erram somas de centavos e quebram o rastro.
- **IA apenas onde há ambiguidade semântica** (classificação de lançamentos bancários atípicos, `metodo=IA` com `confianca < 1`) e como ferramenta de desenvolvimento. Sem chave de API, a solução roda por inteiro (fallback gracioso por regras).
- **Rastro**: `rastro.csv` liga cada número de saída às linhas de origem; a soma de `valor` por `id_saida` fecha centavo a centavo (validada em `main.py` e em `tests/validate_saida.py`).

## Instalação

Requer Python 3.9+ (testado em 3.12).

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    |    Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

## Execução (comando único)

```bash
python src/main.py                 # gera os 6 CSVs em saida/ e audita ao final
python tests/validate_saida.py     # auditoria isolada dos arquivos de saida/
```

A pasta de entrada é procurada nesta ordem: `--data-dir` > variável `TARVO_DATA_DIR` > `data/` > `Tarvo_Data_Pack_set2026/` (na raiz do repositório ou ao lado dele). Copie os arquivos do data pack, **sem editar**, para `data/`.

Opções úteis para desenvolvimento em paralelo:

```bash
python src/main.py --modulos checkout          # roda só o módulo da sua responsabilidade
python src/main.py --data-dir C:\caminho\dados --saida-dir C:\tmp\saida
python tests/validate_saida.py -v              # lista todos os ids do rastro
python tests/validate_saida.py --estrito       # avisos (ex.: arquivo vazio) viram erro
```

Códigos de saída do `main.py`: `0` ok · `1` rastro/validação falhou · `2` erro de entrada ou de dados.

## Estrutura do projeto

| Caminho | Conteúdo | Dono |
|---|---|---|
| `src/config.py` | Caminhos, contrato dos 6 CSVs, utilitários (`round_half_up`, `format_brl`, `clean_cnpj`) e regras de domínio confirmadas | compartilhado (mudanças pequenas e avisadas) |
| `src/rastro_tracker.py` | `RastroTracker`: gera `id_saida`, acumula e valida o rastro | Pessoa 1 |
| `src/checkout.py` | `processar_checkout(data_dir, tracker)` | Pessoa 1 |
| `src/remessas.py` | `processar_remessas(data_dir, tracker)` | Pessoa 2 |
| `src/bancos.py` | `processar_bancos(data_dir, tracker)` | Pessoa 2 |
| `src/main.py` | Orquestra módulos, grava CSVs, valida | Pessoa 2 |
| `tests/validate_saida.py` | Auditoria cega dos arquivos de `saida/` (independente de `src/`) | Pessoa 3 |
| `saida/` | Os 6 CSVs gerados (fazem parte da entrega) | gerado |
| `HIPOTESES.md`, `PROMPTS/`, `README.md` | Documentação exigida pelo edital | Pessoa 3 |

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

## Limitações conhecidas

- Estado atual: **esqueleto**. Os módulos de domínio retornam listas vazias até serem implementados; o pipeline roda e a auditoria passa com avisos de "arquivo sem linhas".
- Os arquivos de entrada são localizados por padrão de nome (`config.PADROES_ENTRADA`); se houver mais de um arquivo para o mesmo padrão, o pipeline aborta em vez de escolher um.
- O casamento de lojistas é por **código (EC) e CNPJ**, nunca por similaridade de nome. Lojista sem correspondência vira pendência, não palpite.
- Casos fora das regras confirmadas vão para `pendencias.csv` com `quem_decide`, em vez de serem decididos pelo código (veja `HIPOTESES.md`).
- `tests/validate_saida.py` confere formato e consistência interna (rastro x saída); **não** substitui o gabarito da banca.

## Documentação adicional

- [`HIPOTESES.md`](HIPOTESES.md): regras confirmadas com o financeiro, premissas assumidas e perguntas feitas.
- [`PROMPTS/MOMENTOS.md`](PROMPTS/MOMENTOS.md): momentos críticos do uso de IA (e histórico das sessões em `PROMPTS/`).
