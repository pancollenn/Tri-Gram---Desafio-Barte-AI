# Especificação Técnica dos Scripts Python (`src/`)

Este documento descreve detalhadamente as responsabilidades, entradas, lógica de negócio e saídas de cada script do projeto de fechamento financeiro automatizado da **Tarvo Pagamentos** (Hackathon Barte AI Services).

## 🏛️ Visão Geral da Arquitetura de Scripts

```
src/
├── main.py                     # Orquestrador principal do pipeline
├── parsers/                    # Camada de Ingestão e Padronização
│   ├── parse_orbe.py           # Ingestão de Checkout (Orbe)
│   ├── parse_ponte.py          # Ingestão de Remessas (Ponte Câmbio)
│   ├── parse_extratos.py       # Ingestão de Extratos (Aurora e Meridiano)
│   └── parse_taxas.py          # Ingestão de Contratos e Taxas (ERP Fênix)
├── engine/                     # Camada de Regras de Negócio e Cálculos
│   ├── comissoes.py            # Missão 1: Cálculo de Comissões por Lojista
│   ├── divergencias.py         # Missão 2: Identificação de Divergências de Taxa
│   ├── notas.py                # Missão 3: Consolidação e Emissão de NFs
│   ├── pendencias.py           # Missão 5: Consolidador de Pendências e Exceções Humanas
│   └── rastro.py               # Motor Central de Auditabilidade e Rastreabilidade
└── ai/                         # Camada de Inteligência Artificial
    └── classifier.py           # Missão 4: Classificação Contábil por IA

```

## 🚀 1. Orquestrador Principal

### `src/main.py`

* **Papel:** Ponto de entrada unificado da aplicação. Executa o pipeline completo do início ao fim com um único comando (`python src/main.py`).

* **Responsabilidades:**

  1. Inicializar ambiente e validar a existência dos arquivos de entrada em `data_pack/`.

  2. Executar em sequência os scripts da camada de `parsers/`.

  3. Chamar as engines determinísticas de cálculo (`comissoes.py` e `divergencias.py`).

  4. Disparar a classificação por IA nos extratos bancários (`classifier.py`).

  5. Processar o faturamento de NFs (`notas.py`).

  6. Consolidar todas as exceções e alertas humanos (`pendencias.py`).

  7. Acionar o consolidador de rastreabilidade (`rastro.py`) para garantir a integridade matemática de todas as saídas.

  8. Exportar os CSVs para a pasta `saida/` nos padrões exigidos (separador `;`, decimal `.`, datas `AAAA-MM-DD`, CNPJ sem formatação).

## 📥 2. Camada de Parsers (`src/parsers/`)

### `src/parsers/parse_orbe.py`

* **Papel:** Ingestão das transações de Checkout (cartão e Pix).
* **Entrada:** `data_pack/orbe_checkout.csv`
* **Responsabilidades:**
  * Ler o relatório bruto sem tratamento prévio manual.
  * Normalizar datas para formato ISO (`AAAA-MM-DD`).
  * Tratar e sanitizar CNPJs (manter apenas os 14 dígitos numéricos).
  * Isolar o identificador único de origem: **`id_transacao`**.
* **Saída Interna:** DataFrame padronizado de transações de Checkout.

### `src/parsers/parse_ponte.py`

* **Papel:** Ingestão das operações de câmbio/remessa internacional.
* **Entrada:** `data_pack/ponte_remessas.xlsx`
* **Responsabilidades:**
  * Ler os relatórios enviados pela parceira Ponte Câmbio.
  * Padronizar moedas, valores BRL/USD e taxas de spread aplicadas.
  * Isolar o identificador único de origem: **`Nº Operação`**.
* **Saída Interna:** DataFrame padronizado de remessas internacionais.

### `src/parsers/parse_extratos.py`

* **Papel:** Ingestão dos extratos dos bancos Aurora e Meridiano.
* **Entradas:** `data_pack/extrato_aurora.csv` e `data_pack/extrato_meridiano.ofx`
* **Responsabilidades:**
  * Processar o arquivo CSV do Banco Aurora criando referências por linha física (**`L10`**, **`L11`**, etc.).
  * Processar o arquivo OFX/XML do Banco Meridiano mantendo a chave única **`FITID`**.
  * Unificar a estrutura dos lançamentos bancários (data, banco, descrição, valor).
* **Saída Interna:** DataFrame unificado de lançamentos bancários com chave de origem preservada.

### `src/parsers/parse_taxas.py`

* **Papel:** Leitura dos parâmetros contratuais dos lojistas.
* **Entrada:** `data_pack/taxas_fenix.xlsx`
* **Responsabilidades:**
  * Mapear taxas contratadas por lojista (MDR %, taxa de antecipação % e % de participação no spread de câmbio).
  * Atrelar razão social, nome fantasia e CNPJ de cada lojista ativo.
* **Saída Interna:** Tabela de parâmetros comerciais por CNPJ/Lojista.

## ⚙️ 3. Camada de Regras de Negócio & Cálculos (`src/engine/`)

### `src/engine/comissoes.py`

* **Papel:** Resolução da **Missão 1** (Comissões por Lojista).
* **Entradas:** Outputs de `parse_orbe.py`, `parse_ponte.py` e `parse_taxas.py`.
* **Responsabilidades:**
  1. **Cálculo de Checkout:** Calcular a comissão da Tarvo com base na taxa MDR e antecipação sobre cada transação processada via Orbe.
  2. **Cálculo de Remessa:** Calcular a participação da Tarvo no spread cambial das operações da Ponte Câmbio.
  3. **Agregação por Lojista:** Agrupar os totais de comissão por CNPJ e linha de negócio (`CHECKOUT` ou `REMESSA`).
* **Saída Gerada:**
  * `saida/comissoes_por_lojista.csv`

### `src/engine/divergencias.py`

* **Papel:** Resolução da **Missão 2** (Divergências de Taxa).
* **Entradas:** Outputs de `parse_orbe.py`, `parse_ponte.py` e `parse_taxas.py`.
* **Responsabilidades:**
  1. Comparar, transação por transação, a taxa percentual contratada no ERP/planilha contra a taxa efetivamente aplicada nos relatórios operacionais.
  2. Identificar inconsistências operacionais (cobrança de taxas a mais, operações duplicadas da Ponte e spreads negativos).
  3. Calcular o valor financeiro exato da divergência em reais (`diferenca_brl`).
* **Saída Gerada:**
  * `saida/divergencias_taxa.csv`

### `src/engine/notas.py`

* **Papel:** Resolução da **Missão 3** (Notas Fiscais a Emitir).
* **Entradas:** Output consolidado de `comissoes.py` e cadastro do tomador via `parse_taxas.py`.
* **Responsabilidades:**
  1. Filtrar apurações que geram obrigação de faturamento por lojista e linha de negócio.
  2. Gerar a discriminação detalhada dos serviços prestados (ex: "Serviços de intermediação financeira - Checkout Setembro/2026").
  3. Formatar o tomador (`tomador_cnpj` e `tomador`) e calcular o valor final a faturar em reais.
* **Saída Gerada:**
  * `saida/notas_a_emitir.csv`

### `src/engine/pendencias.py`

* **Papel:** Resolução da **Missão 5** (Pendências que Exigem Decisão Humana).
* **Entradas:** Inconsistências apontadas por `classifier.py` (IA), `divergencias.py` e exceções de `comissoes.py`.
* **Responsabilidades:**
  1. Reunir em uma única estrutura todas as situações de exceção que o sistema não deve decidir autonomamente.
  2. Mapear a referência de origem (`ref_origem`), tipo de pendência, valor afetado em BRL e o motivo detalhado.
  3. Definir explicitamente quem é o tomador de decisão responsável (`quem_decide`, ex: *Analista Financeiro*, *Gerente de Operações*, *CFO*).
* **Saída Gerada:**
  * `saida/pendencias.csv`

### `src/engine/rastro.py`

* **Papel:** Garantia do **Requisito Central** do Hackathon (Rastreabilidade e Integridade).
* **Entradas:** Registros de saídas gerados por todos os scripts de negócio (`comissoes.py`, `divergencias.py`, `notas.py`, `classifier.py` e `pendencias.py`).
* **Responsabilidades:**
  1. Receber cada `id_saida` e vincular diretamente às linhas/chaves de origem do dado bruto (`id_transacao`, `Nº Operação`, `L10/L11` ou `FITID`).
  2. Executar validação matemática rigorosa: a soma de `valor` no rastro para determinado `id_saida` **precisa bater 100%** com o valor final reportado no CSV da saída correspondente.
  3. Levantar erro/alerta caso haja divergência de arredondamento ou inconsistência na origem.
* **Saída Gerada:**
  * `saida/rastro.csv`

## 🤖 4. Camada de Inteligência Artificial (`src/ai/`)

### `src/ai/classifier.py`

* **Papel:** Resolução da **Missão 4** (Classificação Contábil dos Extratos).
* **Entradas:** Output de `parse_extratos.py` + Plano de Contas da Tarvo.
* **Responsabilidades:**
  1. Enviar descrições de extrato bancário para a LLM (via API) para categorização no plano de contas.
  2. Aplicar regras determinísticas prévias para lançamentos recorrentes/padrão (`metodo = REGRA`) e usar LLM nos demais (`metodo = IA`).
  3. Atribuir um score de confiança (`confianca` entre `0.0` e `1.0`).
  4. Encaminhar lançamentos com baixa confiança ou ambiguidade para que o script `pendencias.py` registre a exceção.
* **Saída Gerada:**
  * `saida/lancamentos_classificados.csv`

## 📊 Resumo de De-Para (Scripts vs. Missões e Saídas)

| Missão do Case | Script Dedicado | Arquivo de Saída Gerado |
| ----- | ----- | ----- |
| **1. Comissões por Lojista** | `src/engine/comissoes.py` | `saida/comissoes_por_lojista.csv` |
| **2. Divergências de Taxa** | `src/engine/divergencias.py` | `saida/divergencias_taxa.csv` |
| **3. Notas Fiscais a Emitir** | `src/engine/notas.py` | `saida/notas_a_emitir.csv` |
| **4. Lançamentos Classificados** | `src/ai/classifier.py` | `saida/lancamentos_classificados.csv` |
| **5. Mapeamento de Pendências** | `src/engine/pendencias.py` | `saida/pendencias.csv` |
| **Regra Central: Rastreabilidade** | `src/engine/rastro.py` | `saida/rastro.csv` |
