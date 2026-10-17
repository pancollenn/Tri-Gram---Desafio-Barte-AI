# Especificação Técnica dos Scripts Python (`src/`)
**Desafio Barte AI · Hackathon de AI Services**  
*Squad de Operações Financeiras, Conciliação e Fechamento Contábil*  
*Caso Tarvo Pagamentos · Fechamento de Setembro/2026*

---

## 🏛️ 1. Visão Geral da Arquitetura

O sistema foi desenhado em uma arquitetura em 3 camadas desacopladas, com um módulo compartilhado de contratos e utilitários (`config.py`), um motor central de rastreabilidade matemática (`RastroTracker`) e um script independente de auditoria cega (`tests/validate_saida.py`).

```
Tri-Gram---Desafio-Barte-AI/
├── src/
│   ├── config.py                  # Contratos estritos dos 6 CSVs, regras de domínio e utilitários financeiros
│   ├── main.py                    # Orquestrador do pipeline (CLI, serialização e gravação dos CSVs)
│   ├── parsers/                   # Camada 1: Ingestão e Padronização
│   │   ├── parse_orbe.py          # Ingestão de Checkout (Orbe CSV) + Cruzamento com Taxas
│   │   ├── parse_ponte.py         # Ingestão de Remessas (extração do .xlsx do e-mail .eml) + Spreads
│   │   └── parse_extratos.py      # Ingestão de Extratos (Aurora CSV, Meridiano OFX) + Plano ERP Fênix
│   ├── engine/                    # Camada 2: Regras Determinísticas e Cálculos Financeiros
│   │   ├── comissoes.py           # Missão 1: Comissões líquidas por lojista e linha de negócio
│   │   ├── divergencias.py        # Missão 2: Identificação de divergências de taxas e spreads
│   │   ├── notas.py               # Missão 3: Faturamento e emissão de Notas Fiscais (NFS-e)
│   │   ├── pendencias.py          # Missão 5: Consolidação de pendências para decisão humana
│   │   └── rastro.py              # Requisito Central: Motor de Rastreabilidade Matemática Absoluta
│   └── ai/                        # Camada 3: Inteligência Artificial
│       └── classifier.py          # Missão 4: Classificação contábil dos lançamentos bancários no ERP
├── tests/
│   └── validate_saida.py          # Auditor independente que valida o gabarito cego do edital
└── data_pack/                     # Arquivos brutos fornecidos pela Tarvo (mesmo formato em outubro)
```

---

## ⚙️ 2. Módulo Central Compartilhado: `src/config.py`

* **Papel:** Núcleo de contratos e regras de domínio da aplicação. Todos os demais módulos importam deste arquivo para garantir integridade e evitar duplicação.
* **Responsabilidades:**
  1. **Contrato dos 6 CSVs de Saída:** Define colunas exatas, tipos de dados, delimitador (`;`), encoding (`utf-8`) e formatação obrigatória (`AAAA-MM-DD` para datas, ponto `.` para decimal, 14 dígitos numéricos para CNPJs com zeros à esquerda preservados).
  2. **Localização Dinâmica de Arquivos (`PADROES_ENTRADA` / `localizar_arquivo`):** Localiza os arquivos brutos via padrão `glob` (ex: `01_orbe_relatorio_comissoes_*.csv`, `03_email_ponte_cambio_relatorio_*.eml`). Isso garante que a solução rode para setembro/2026 e execute perfeitamente para outubro/2026 sem alteração de código.
  3. **Aritmética Financeira Precisa:**
     * `para_decimal(val)`: Converte entradas para `Decimal` evitando erros de ponto flutuante binário.
     * `round_half_up(val)`: Arredondamento comum para 2 casas decimais (`ROUND_HALF_UP`, onde `0.005 -> 0.01` e `-0.005 -> -0.01`).
     * `clean_cnpj(val)`: Sanitização estrita para 14 dígitos numéricos (`00520815000100`).
     * `parse_decimal_ptbr(texto)`: Converte números no formato brasileiro (`1.234,56` ou `-389,00`) para `Decimal`.
  4. **Parâmetros e Regras de Negócio Confirmadas (Helena / Slack `#tarvo-financeiro`):**
     * Mapeamento de ECs faltantes na tabela: `1043300981` (Novo Horizonte), `1043396662` (Horizonte Viagens), `1038867654` (Kiwi Experience).
     * Exceção de contrato ausente: `1076801732` (*Atlas Idiomas* - não faturar, enviar para pendências).
     * Exceção comercial: `1018325654` (*Casa do Estudante* - taxa de checkout 0.00%).
     * Tomador único de remessas: `Ponte Câmbio S.A.` (CNPJ `75.374.179/0001-46`).
     * Contas contábeis-chave do ERP Fênix (`1.1.03.002` comissões a receber câmbio, `1.1.09.001` mútuo Aurora/Meridiano, `1.1.09.002` créditos não identificados, passivos `2.1.04.001` e `2.1.03.xxx`).

---

## 🚀 3. Orquestrador Principal: `src/main.py`

* **Papel:** Ponto de entrada unificado da aplicação (`python src/main.py`).
* **Responsabilidades:**
  1. Suportar execução total ou modular via CLI:
     * `python src/main.py`: Executa o pipeline completo e audita ao final.
     * `python src/main.py --modulos checkout`: Executa apenas Checkout (Nível Mínimo do edital).
     * `python src/main.py --data-dir <pasta>` e `--saida-dir <pasta>`: Parametrização de pastas.
     * `python src/main.py --estrito`: Trata avisos da auditoria como erros.
  2. Coordenar a execução em etapas: Ingestão (`parsers/`) ➔ Cálculos (`engine/`) ➔ IA (`classifier.py`) ➔ Pendências (`pendencias.py`).
  3. Validar a integridade do rastro através do `tracker.validar_todos()` antes da gravação.
  4. Gravar os CSVs finais em `saida/` obedecendo rigorosamente à formatação de colunas de `config.ARQUIVOS_SAIDA`.
  5. Acionar o auditor cego `tests/validate_saida.py` e reportar código de saída (0 = sucesso; 1 = falha de validação/rastro; 2 = erro de entrada).

---

## 📥 4. Camada de Ingestão e Padronização (`src/parsers/`)

### `src/parsers/parse_orbe.py`
* **Papel:** Leitura das transações brutas de Checkout e enriquecimento com os dados cadastrais e taxas contratuais.
* **Entradas:**
  * `01_orbe_relatorio_comissoes_*.csv` (delimitador `;`, valores em pt-BR).
  * `02_tabela_taxas_contratadas*.xlsx` (aba `Taxas vigentes`, ignorando a aba antiga de 2025).
* **Particularidades dos Dados e Regras:**
  * O CSV da Orbe **não possui coluna de CNPJ**; contém `cod_estabelecimento` (EC) e `nome_estabelecimento`.
  * O CNPJ e as taxas contratuais por modalidade (Débito, Crédito à vista, Crédito 2-6x, Crédito 7-12x, Pix, Antecipação) devem ser cruzados a partir do `cod_estabelecimento`.
  * Para os ECs ausentes na planilha, aplicar o mapeamento `config.EC_FALTANTES_TABELA`.
  * Tratar vigência temporal de taxas na planilha (ex.: *Bridge Idiomas* possui uma linha até 14/09/2026 e nova taxa a partir de 15/09/2026).
  * Normalizar datas para formato ISO (`AAAA-MM-DD`) e converter valores financeiros para `Decimal`.
  * Preservar o identificador único de origem: **`id_transacao`** (ex: `TX88410932`).
* **Retorno:** Dicionário com lista de transações normalizadas, tabela de taxas contratuais por EC/data e nome do arquivo de origem.

### `src/parsers/parse_ponte.py`
* **Papel:** Ingestão das operações internacionais de câmbio a partir da mensagem de e-mail e conferência de spreads.
* **Entradas:**
  * `03_email_ponte_cambio_relatorio_*.eml` (mensagem de e-mail MIME da parceira).
  * `02_tabela_taxas_contratadas*.xlsx` (coluna de spread de remessa por CNPJ da agência).
* **Particularidades dos Dados e Regras:**
  * Extrair o anexo `.xlsx` contido no arquivo `.eml` via biblioteca nativa `email` (proibida extração manual).
  * No anexo Excel, selecionar a aba **`Operações`** (ignorar aba `Resumo`).
  * Pular as 3 primeiras linhas institucionais e iniciar a leitura do cabeçalho na linha 4.
  * Converter datas de número de série do Excel (ex: `46295`) para formato ISO (`AAAA-MM-DD`).
  * Sanitizar o `CNPJ Cliente` para 14 dígitos numéricos (o relatório traz formatos mistos com e sem pontuação).
  * Preservar o identificador único de origem: **`Nº Operação`** (ex: `PC-0926-0002`).
* **Retorno:** Dicionário com lista de operações de remessa estruturadas, mapa de spreads contratados e nome do arquivo de origem.

### `src/parsers/parse_extratos.py`
* **Papel:** Leitura dos extratos das duas contas bancárias da Tarvo e do plano de contas contábil.
* **Entradas:**
  * `05a_extrato_banco_aurora_*.csv` (conta principal C/C 4471-0).
  * `05b_extrato_banco_meridiano_*.ofx` (conta de câmbio C/C 90233-5, formato OFX SGML 102).
  * `04_plano_de_contas_fenix_erp*.csv` (plano de contas analítico do ERP Fênix).
* **Particularidades dos Dados e Regras:**
  * **Banco Aurora (CSV):** As primeiras 6 linhas contêm metadados da conta; os dados iniciam após o cabeçalho na linha 7. A referência de origem obrigatória pelo edital é o **número da linha física do arquivo** (`L10`, `L11`, etc.).
  * **Banco Meridiano (OFX):** Fazer parse das tags SGML/XML (`<STMTTRN>`). A referência de origem obrigatória é a tag **`<FITID>`** (ex: `MRD2026090132`).
  * Converter valores para `Decimal` (débitos negativos, créditos positivos) e padronizar datas.
* **Retorno:** Dicionário com listas de lançamentos do Aurora, lançamentos do Meridiano e tabela do plano de contas.

---

## 🧮 5. Camada de Regras de Negócio e Cálculos (`src/engine/`)

### `src/engine/comissoes.py` (Missão 1)
* **Papel:** Calcular a comissão líquida devida à Tarvo por lojista e por linha de negócio.
* **Regras de Negócio:**
  1. **Checkout:**
     * A comissão é calculada **linha a linha pela taxa contratada** (`valor_bruto × taxa_contratada / 100`), e **não** pela taxa que a Orbe aplicou.
     * Arredondar cada linha para 2 casas com `round_half_up`.
     * **Estornos:** Abatem a comissão pela taxa vigente na data da venda original (`data_venda_original`).
     * **Reversão de Antecipação:** Anula a taxa da antecipação correspondente.
     * **Casa do Estudante (EC `1018325654`):** Taxa contratada 0.00% ➔ Comissão = `R$ 0.00`.
     * **Atlas Idiomas (EC `1076801732`):** Sem contrato 2026 ➔ Isolar em pendências, comissão não entra no faturamento.
  2. **Remessas:**
     * Comissão Tarvo = **50% do `Spread R$`** de cada operação válida (`round_half_up` por operação).
     * **Expurgo de Duplicata:** A operação repetida `PC-0926-0162` (Bagagem Livre) conta uma única vez.
     * **Exclusão de Spreads Negativos:** As 4 operações com estouro de trava D-1 (`PC-0926-0210`, `-0326`, `-0491`, `-0545`) ficam **fora da comissão e fora da nota** (são enviadas para contestação).
  3. **Rastreabilidade Obrigatória:** Cada transação/operação incluída no cálculo deve registrar sua contribuição via `tracker.registrar(id_saida, arquivo_origem, ref_origem, valor_comissao)`.
* **Saída:** `saida/comissoes_por_lojista.csv` (`id_saida;cnpj;lojista;linha_negocio;comissao_brl`).

### `src/engine/divergencias.py` (Missão 2)
* **Papel:** Apurar transação por transação as divergências entre a taxa contratada e a aplicada.
* **Regras de Negócio:**
  1. **Checkout:**
     * Apurar onde `taxa_aplicada_pct != taxa_contratada_pct` (acima da tolerância de 0.01 p.p.).
     * Calcular `diferenca_brl = round_half_up(valor_bruto * (taxa_aplicada - taxa_contratada) / 100)`.
     * Truncamento de 1 centavo da Orbe **não** é divergência de taxa.
     * Toda a cobrança da Orbe sobre a *Casa do Estudante* é divergência (taxa contratada 0.00%).
  2. **Remessas:**
     * *Mundo Aberto Intercâmbio:* Ponte cobrou 1.50% de spread enquanto o contrato previa 1.20%. A diferença financeira total calculada sobre o volume da operação é reportada como divergência.
     * Os 4 spreads negativos da Ponte Câmbio são registrados como divergência operacional.
* **Saída:** `saida/divergencias_taxa.csv` (`id_saida;cnpj;linha_negocio;ref_origem;taxa_contratada_pct;taxa_aplicada_pct;diferenca_brl`).

### `src/engine/notas.py` (Missão 3)
* **Papel:** Gerar a lista de Notas Fiscais de Serviços (NFS-e) a emitir pela Tarvo.
* **Regras de Negócio:**
  1. **Checkout:** Emitir uma nota fiscal para cada lojista ativo cujo saldo de comissão líquida seja estritamente positivo (`> R$ 0.00`). Lojistas com saldo zero (*Casa do Estudante*) ou negativo não emitem nota.
  2. **Atlas Idiomas:** Bloqueada de faturamento por falta de contrato assinado em 2026.
  3. **Remessas:** Emitir **exatamente UMA ÚNICA NOTA FISCAL** contra a **Ponte Câmbio S.A.** (CNPJ `75.374.179/0001-46`) pelo valor total consolidado das comissões válidas de remessa.
  4. Discriminação textual formal do serviço prestado (ex.: `"Serviços de intermediação e agenciamento - Checkout competência 09/2026"`).
  5. Cada nota deve ter seu rastro registrado amarrando as operações que compõem o faturamento.
* **Saída:** `saida/notas_a_emitir.csv` (`id_saida;tomador_cnpj;tomador;linha_negocio;valor_brl;discriminacao`).

### `src/engine/pendencias.py` (Missão 5)
* **Papel:** Catalogar de forma estruturada todas as anomalias e exceções que exigem intervenção e deliberação humana.
* **Catálogo Oficial das 7 Pendências:**
  1. **Spreads Negativos:** 4 operações com trava expirada da Ponte Câmbio (`PC-0926-0210`, `-0326`, `-0491`, `-0545`) ➔ Decisão: *Financeiro Tarvo (Helena)*.
  2. **Operação Repetida:** Retificação da operação duplicada `PC-0926-0162` ➔ Decisão: *Financeiro Tarvo (Helena)*.
  3. **Spread Indevido Mundo Aberto:** Cobrança de 1.50% vs 1.20% contratado ➔ Decisão: *Financeiro Tarvo (Helena)*.
  4. **Ressarcimento Casa do Estudante:** Devolução de taxas de checkout retidas indevidamente pela Orbe ➔ Decisão: *Financeiro Tarvo (Helena)*.
  5. **Contrato Atlas Idiomas:** Regularização comercial do contrato pendente de 2026 ➔ Decisão: *Comercial Tarvo (Diego)*.
  6. **Pix Não Identificado:** Lançamento no Aurora L50 de R$ 7.350,00 sem remetente ➔ Decisão: *Financeiro Tarvo (Helena)*.
  7. **Devolução de Pix Mundo Aberto:** Investigação de devolução de R$ 12.400,00 no Aurora L65 ➔ Decisão: *Financeiro Tarvo (Helena)*.
* **Saída:** `saida/pendencias.csv` (`id_saida;tipo;ref_origem;valor_brl;motivo;quem_decide`).

### `src/engine/rastro.py` (Regra Central do Case)
* **Papel:** Garantir o requisito eliminatório da banca: **todo número de saída aponta para as linhas de origem que o compõem, e a soma no rastro fecha centavo a centavo**.
* **Mecanismo:**
  * Instância do `RastroTracker` repassada por todo o fluxo.
  * Gera IDs determinísticos com prefixos padronizados (`COM-0001`, `NF-0001`, `DIV-0001`, `LAN-0001`, `PEN-0001`).
  * Método `registrar(id_saida, arquivo_origem, ref_origem, valor)` valida que cada lançamento tem precisão máxima de 2 casas decimais (`tem_precisao_de_centavos`).
  * Método `validar_todos()` compara o somatório acumulado contra o valor das comissões e notas reportadas, levantando erro caso haja discrepância de qualquer centavo.
* **Saída:** `saida/rastro.csv` (`id_saida;arquivo_origem;ref_origem;valor`).

---

## 🤖 6. Camada de Inteligência Artificial: `src/ai/classifier.py` (Missão 4)

* **Papel:** Classificar 100% dos lançamentos bancários dos bancos Aurora e Meridiano no Plano de Contas Analítico do ERP Fênix.
* **Estratégia Híbrida Recomendada (Robustez + IA Explicável):**
  1. **Regras Determinísticas (`metodo = REGRA`, `confianca = 1.0`):**
     * Pagamento de folha de salários e encargos de agosto baixam passivos já provisionados (`2.1.04.001`, grupo `2.1.03.xxx`), não são despesa de setembro.
     * Recebimento de comissão de câmbio em 04/09 (Meridiano `MRD2026090132`) baixa o ativo `1.1.03.002` (comissões a receber).
     * Transferências entre contas próprias (Aurora ↔ Meridiano) vão para a conta transitória de mútuo `1.1.09.001`.
     * Despesas correntes administrativas padronizadas vão diretamente para as contas de despesa do grupo `4.2.xxx`.
  2. **Classificação por IA (`metodo = IA`):**
     * Utilizar a LLM com prompt estruturado contendo o plano de contas analítico para desambiguar lançamentos com descrições atípicas ou não previstas em regras simples.
     * Retornar o código analítico exato da conta e o score de confiança (ex: `0.85`).
  3. **Exceções Humanas (`metodo = HUMANO` ou conta transitória):**
     * Lançamentos não identificáveis (ex: Pix recebido de R$ 7.350,00) são direcionados para a conta transitória `1.1.09.002` (Créditos não identificados) e integrados ao `pendencias.csv`.
* **Saída:** `saida/lancamentos_classificados.csv` (`id_saida;banco;ref_origem;data;descricao;valor;conta_codigo;metodo;confianca`).

---

## 🧪 7. Auditoria Cega e Validação: `tests/validate_saida.py`

* **Papel:** Replica de forma independente a rotina automática que a banca avaliadora da Barte usará para corrigir a entrega.
* **Características:**
  * Desenvolvido exclusivamente com a biblioteca padrão do Python (`csv`, `re`, `decimal`).
  * Não importa módulos de `src/` para evitar reproduzir eventuais bugs de implementação.
  * Valida:
    * Existência e nomes exatos dos 6 arquivos CSV em `saida/`.
    * Cabeçalhos e ordem das colunas obrigatórias.
    * Formatos estritos: separador `;`, ausência de valores `NaN`/`null`/`None`, formato de dinheiro (`-?123.45`), formato de percentual, CNPJ com 14 dígitos e datas em formato ISO `AAAA-MM-DD`.
    * Domínios restritos (`linha_negocio`: `CHECKOUT`/`REMESSA`; `banco`: `AURORA`/`MERIDIANO`; `metodo`: `REGRA`/`IA`/`HUMANO`).
    * Integridade matemática total: valida se a soma das linhas de `rastro.csv` fecha com os totais de `comissoes_por_lojista.csv` e `notas_a_emitir.csv`.

---

## 📊 8. Matriz De-Para (Missões do Edital vs. Componentes)

| Missão do Case | Módulo Implementador | Arquivo de Saída Gerado | Nível de Entrega |
|---|---|---|---|
| **1. Comissões por Lojista** | `src/engine/comissoes.py` | `saida/comissoes_por_lojista.csv` | **Mínimo** (Checkout) / **Alvo** (Remessa) |
| **2. Divergências de Taxa** | `src/engine/divergencias.py` | `saida/divergencias_taxa.csv` | **Alvo** |
| **3. Notas Fiscais a Emitir** | `src/engine/notas.py` | `saida/notas_a_emitir.csv` | **Alvo** |
| **4. Lançamentos Classificados** | `src/ai/classifier.py` | `saida/lancamentos_classificados.csv` | **Alvo** |
| **5. Mapeamento de Pendências** | `src/engine/pendencias.py` | `saida/pendencias.csv` | **Extra** |
| **Regra Central: Rastreabilidade** | `src/engine/rastro.py` | `saida/rastro.csv` | **Obrigatória em todos os níveis** |

---

## 🏁 9. Roteiro de Implementação Sugerido

```
PASSO 1: NÍVEL MÍNIMO (Garante a nota de partida)
├── 1. Implementar `src/parsers/parse_orbe.py` (leitura Orbe + taxas vigentes)
├── 2. Implementar `src/engine/comissoes.py` para checkout com `tracker.registrar()`
└── 3. Validar execução com `python src/main.py --modulos checkout` e conferir `validate_saida.py`

PASSO 2: NÍVEL ALVO (Garante disputa no topo)
├── 4. Implementar `src/parsers/parse_ponte.py` (extração do .xlsx do .eml da Ponte)
├── 5. Concluir comissões de remessas em `comissoes.py`
├── 6. Implementar `src/engine/divergencias.py` e `src/engine/notas.py`
├── 7. Implementar `src/parsers/parse_extratos.py` (Aurora CSV e Meridiano OFX)
└── 8. Implementar `src/ai/classifier.py` (regras contábeis + IA)

PASSO 3: NÍVEL EXTRA E DOCUMENTAÇÃO
├── 9. Implementar `src/engine/pendencias.py` (as 7 pendências mapeadas)
├── 10. Executar auditoria final completa: `python src/main.py --estrito`
└── 11. Atualizar `HIPOTESES.md`, `README.md` e preparar o pitch executivo
```
