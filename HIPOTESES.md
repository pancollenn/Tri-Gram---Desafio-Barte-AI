# Hipóteses, Regras Confirmadas e Estado do Projeto
**Desafio Barte AI · Hackathon de AI Services**  
*Squad de Operações Financeiras, Conciliação e Fechamento Contábil*  
*Caso Tarvo Pagamentos · Fechamento de Setembro/2026*

Este documento separa **o que sabemos** (confirmado pelo financeiro da Tarvo, Helena, no canal `#tarvo-financeiro` ou especificado no edital) **do que assumimos** (premissas de engenharia e modelagem financeira).

Legenda de status: ✅ confirmada / implementada · ⚠️ assumida (em validação) · ❓ aberta (decisão humana)

---

## 1. Regras Confirmadas pelo Financeiro (Helena, Slack)

### 1.1 Checkout (Adquirência Orbe x Tabela de Taxas Contratadas)

| ID | Regra confirmada | Módulos implementadores | Status |
|---|---|---|---|
| **RC-01** | A comissão e a nota do checkout são calculadas pela **taxa contratada** (`valor_bruto × taxa_contratada / 100`), linha a linha, **não** pela taxa aplicada pela Orbe. | `src/parsers/parse_orbe.py`, `src/engine/comissoes.py` | ✅ |
| **RC-02** | Diferença entre taxa aplicada e contratada é **divergência**: não altera a comissão devida; é reportada em `divergencias_taxa.csv`. | `src/engine/divergencias.py` | ✅ |
| **RC-03** | **Estornos** abatem a comissão de setembro pela taxa contratada **vigente na data da venda original** (`data_venda_original`). **Reversão de antecipação** anula a taxa da antecipação que reverte. | `src/parsers/parse_orbe.py`, `src/engine/comissoes.py` | ✅ |
| **RC-04** | **Casa do Estudante** (EC `1018325654`): taxa contratada de checkout = **0,00%** (setembro a dezembro/2026, acordo comercial). Tudo que a Orbe cobrou dela é divergência; comissão = R$ 0,00; não emite nota fiscal. | `src/config.py`, `src/parsers/parse_orbe.py`, `src/engine/comissoes.py` | ✅ |
| **RC-05** | **Atlas Idiomas** (EC `1076801732`): sem contrato assinado em 2026. **Não faturar**; isolar em `pendencias.csv` com `sem_contrato = True`. | `src/config.py`, `src/parsers/parse_orbe.py`, `src/engine/pendencias.py` | ✅ |
| **RC-06** | **ECs ausentes na planilha de taxas**: `1043300981` = Novo Horizonte Intercâmbio; `1043396662` = Horizonte Viagens e Turismo; `1038867654` = Kiwi Experience. Mapeados via `config.EC_FALTANTES_TABELA`. | `src/config.py`, `src/parsers/parse_orbe.py` | ✅ |
| **RC-07** | Arredondamento comum para o centavo (`ROUND_HALF_UP`, onde `0,005 → 0,01`). A **Orbe trunca** os centavos; diferença de 1 centavo causada por isso **não é divergência**. | `src/config.py`, `src/engine/divergencias.py` | ✅ |
| **RC-08** | Spread/taxas em branco ou com texto `"padrão"` na planilha equivalem a **1,50%** (`config.SPREAD_PADRAO_PCT`). Aba antiga de 2025 é ignorada. | `src/parsers/parse_orbe.py`, `src/parsers/parse_ponte.py` | ✅ |
| **RC-09** | Emissão de uma nota por lojista ativo cujo saldo de comissão líquida seja estritamente positivo (`> R$ 0,00`); saldo zero ou negativo **não emite** nota. | `src/engine/notas.py` | ✅ |
| **RC-23** | **Ajustes Tardios (30/09):** Ingestão complementar de `06_orbe_ajustes_tardios_*.csv` para capturar estornos de fechamento (ex: Dublin Hub Intercâmbio). | `src/parsers/parse_orbe.py` | ✅ |

### 1.2 Remessas (Ponte Câmbio x Tabela de Taxas Contratadas)

| ID | Regra confirmada | Módulos implementadores | Status |
|---|---|---|---|
| **RC-10** | Comissão da Tarvo = **50% do `Spread R$`** realizado, calculada e arredondada **operação por operação** (`round_half_up`). | `src/parsers/parse_ponte.py`, `src/engine/comissoes.py` | ✅ |
| **RC-11** | Para a competência vale a **Data de Contratação** (ou data de liquidação como fallback). | `src/parsers/parse_ponte.py` | ✅ |
| **RC-12** | **Operação repetida** (`PC-0926-0162`, Bagagem Livre Turismo): computada **uma única vez**; a duplicata é isolada para retificação em `pendencias.csv`. | `src/parsers/parse_ponte.py`, `src/engine/pendencias.py` | ✅ |
| **RC-13** | **4 spreads negativos** (`PC-0926-0210`, `-0326`, `-0491`, `-0545`): trava D-1 expirada (> 2h). Ficam **fora da comissão e fora da nota**; vão para contestação em `pendencias.csv` e `divergencias_taxa.csv`. | `src/parsers/parse_ponte.py`, `src/engine/divergencias.py`, `src/engine/pendencias.py` | ✅ |
| **RC-14** | **Mundo Aberto Intercâmbio**: Ponte cobrou ~1,50% e o contrato prevê 1,20%. As 23 operações geram divergência financeira apurada sobre o volume e vão para contestação. | `src/parsers/parse_ponte.py`, `src/engine/divergencias.py`, `src/engine/pendencias.py` | ✅ |
| **RC-15** | Status de compliance "aprovado com ressalva" **não** altera liquidação nem comissão. | `src/parsers/parse_ponte.py` | ✅ |
| **RC-16** | **Uma única nota de remessa**, emitida contra a **Ponte Câmbio S.A.** (CNPJ `75374179000146`), pelo valor consolidado das 228 operações válidas (**R$ 39.543,45**). | `src/parsers/parse_ponte.py`, `src/engine/notas.py` | ✅ |
| **RC-24** | **Extração Automatizada em Memória:** O relatório `.xlsx` da Ponte é extraído do e-mail MIME `.eml` estritamente em memória via biblioteca nativa `email` e `io.BytesIO`, sem gravação em disco. | `src/parsers/parse_ponte.py` | ✅ |

### 1.3 Bancos (Extratos Aurora e Meridiano x Plano de Contas ERP Fênix)

| ID | Regra confirmada | Módulos implementadores | Status |
|---|---|---|---|
| **RC-17** | `conta_codigo` representa a **contrapartida contábil** do lançamento bancário no Plano de Contas Analítico Fênix. | `src/parsers/parse_extratos.py`, `src/ai/classifier.py` | ✅ |
| **RC-18** | **Folha de salários e tributos de agosto pagos em setembro baixam passivos já provisionados** (`2.1.04.001`, grupo `2.1.03.xxx`), não são despesa de setembro. | `src/ai/classifier.py` | ✅ |
| **RC-19** | Comissão de câmbio de agosto recebida em 04/09 (Meridiano `MRD2026090132`, R$ 61.884,12) baixa o ativo `1.1.03.002` (comissões a receber). | `src/ai/classifier.py` | ✅ |
| **RC-20** | Despesas administrativas correntes não provisionadas entram diretamente no grupo de despesas `4.2.xxx`. | `src/ai/classifier.py` | ✅ |
| **RC-21** | Transferências entre contas próprias (Aurora ↔ Meridiano) vão para a conta transitória de mútuo `1.1.09.001`. Crédito sem identificação vai para `1.1.09.002` e vira pendência. | `src/ai/classifier.py`, `src/engine/pendencias.py` | ✅ |
| **RC-22** | A liquidação da Orbe no Aurora não fecha com o relatório analítico do mês (débito/Pix no dia seguinte, crédito ao longo dos meses). Não é inconsistência. | (informativo / auditoria) | ✅ |
| **RC-25** | **Referências Atômicas de Origem:** Banco Aurora utiliza obrigatoriamente a linha física do CSV (`ref_origem = 'L<n>'`, ex: `L50`); Banco Meridiano utiliza a tag SGML `<FITID>` (`ref_origem = 'MRD...'`). | `src/parsers/parse_extratos.py` | ✅ |
| **RC-26** | **Mútuo Aurora → Meridiano (Liquidação D+1):** Aurora debitou 4 transferências (R$ 1.450.000,00); Meridiano creditou 3 transferências em setembro (R$ 1.150.000,00). A 4ª TED (30/09, R$ 300.000,00) liquida em outubro no Meridiano. | `src/parsers/parse_extratos.py`, `tests/test_parse_extratos.py` | ✅ |

---

## 2. Catálogo Oficial das 7 Pendências Operacionais (`pendencias.csv`)

| # | Pendência | `ref_origem` | Montante Envolvido | Decisor (`quem_decide`) |
|---|---|---|---|---|
| **1** | Contestar com a Ponte os 4 spreads negativos (trava D-1 expirada) | `PC-0926-0210`, `-0326`, `-0491`, `-0545` | R$ -1.890,20 | Financeiro Tarvo (Helena) |
| **2** | Retificação de relatório da Ponte Câmbio (operação duplicada) | `PC-0926-0162` | R$ 10.420,00 | Financeiro Tarvo (Helena) |
| **3** | Contestar cobrança indevida de spread da Mundo Aberto (1,50% vs 1,20%) | 23 operações da Mundo Aberto | R$ 688,14 | Financeiro Tarvo (Helena) |
| **4** | Devolver taxas retidas indevidamente pela Orbe da Casa do Estudante (taxa 0,00%) | transações EC `1018325654` | R$ 13.916,77 | Financeiro Tarvo (Helena) |
| **5** | Regularização e assinatura de contrato com a Atlas Idiomas | EC `1076801732` | A definir | Comercial Tarvo (Diego) |
| **6** | Identificar remetente de Pix sem identificação | Aurora `L50` | R$ 7.350,00 | Financeiro Tarvo (Helena) |
| **7** | Investigar motivo de devolução de Pix da Mundo Aberto | Aurora `L65` | R$ 12.400,00 | Financeiro Tarvo (Helena) |

---

## 3. Premissas de Engenharia e Arquitetura

| ID | Premissa | Justificativa | Status |
|---|---|---|---|
| **PA-01** | A solução deve rodar para setembro/2026 e executar em outubro com arquivos de mesmo formato sem alteração de código. Localização por padrão `glob` (`config.PADROES_ENTRADA`). | Exigência explícita do edital / generalização. | ✅ Confirmada e testada |
| **PA-02** | Cada linha de `rastro.csv` registra a **contribuição financeira líquida** da linha de origem para o `id_saida` correspondente, fechando rigorosamente centavo a centavo com o total reportado. | Requisito eliminatório de auditabilidade da banca. | ✅ Confirmada e auditada |
| **PA-03** | Cada comissão e cada nota fiscal possuem identificadores sequenciais próprios (`COM-0001`, `NF-0001`, etc.); a nota fiscal repete no rastro a amarração das transações que a compõem. | Permite auditoria independente de comissões e notas fiscais. | ✅ Confirmada e implementada |
| **PA-04** | O cruzamento cadastral de lojistas é executado estritamente por **código EC / CNPJ sanitizado** (14 dígitos), nunca por similaridade imprecisa de texto. | Evita contaminação de bases e erros de conciliação. | ✅ Confirmada e implementada |
| **PA-05** | Formatação estrita nos 6 CSVs: separador `;`, encoding `utf-8`, valores monetários com 2 casas e ponto (`123.45`), percentuais com ponto e datas ISO `AAAA-MM-DD`. | Contrato formal de entrega do hackathon. | ✅ Confirmada e validada |
| **PA-06** | Transações atípicas ou ambíguas são catalogadas em `pendencias.csv` para intervenção humana em vez de serem forçadas por decisões arbitrárias do código. | Governança corporativa e mitigação de risco financeiro. | ✅ Confirmada e implementada |

---

## 4. Estado Atual de Implementação dos Componentes

| Camada / Componente | Arquivo Principal | Status Atual | Suite de Testes Dedicada |
|---|---|---|---|
| **Ingestão Checkout** | `src/parsers/parse_orbe.py` | 100% Concluído | `tests/test_parse_orbe.py` (9 cenários com `assert` aprovados) |
| **Ingestão Remessas** | `src/parsers/parse_ponte.py` | 100% Concluído | `tests/test_parse_ponte.py` (30 testes com `assert` aprovados) |
| **Ingestão Extratos e Plano** | `src/parsers/parse_extratos.py` | 100% Concluído | `tests/test_parse_extratos.py` (84 Aurora, 100 Meridiano, 32 analíticas) |
| **Missão 1: Comissões** | `src/engine/comissoes.py` | Checkout 100% / Remessa integrada | `src/main.py --modulos checkout` (Auditoria 100% aprovada) |
| **Missão 2: Divergências** | `src/engine/divergencias.py` | Regras mapeadas e prontas | Validado via `parse_orbe` e `parse_ponte` |
| **Missão 3: Notas Fiscais** | `src/engine/notas.py` | Regras mapeadas e prontas | Validado via `comissoes` e `parse_ponte` |
| **Missão 4: Classificação IA** | `src/ai/classifier.py` | Extratos e plano integrados | Estrutura híbrida (regras + LLM) |
| **Missão 5: Pendências** | `src/engine/pendencias.py` | Catálogo das 7 pendências mapeado | Mapeamento pronto para consolidação final |
| **Motor de Rastreabilidade** | `src/engine/rastro.py` | 100% Concluído e Operante | `RastroTracker.validar_todos()` em execução |
| **Auditoria Cega Independente** | `tests/validate_saida.py` | 100% Concluído | Valida gabarito sem dependência de `src/` |

---

## 5. Histórico de Alinhamentos com o Financeiro (Slack `#tarvo-financeiro`)

| # | Data | Pergunta / Ponto Alinhado | Decisão Confirmada | Impacto no Projeto |
|---|---|---|---|---|
| **Q-01** | 2026-10-16 | Base de cálculo da comissão de checkout na ocorrência de divergência. | Calculada sempre pela **taxa contratada** (RC-01). A diferença vai para `divergencias_taxa.csv`. | Garante receita legítima da Tarvo. |
| **Q-02** | 2026-10-16 | Impacto de estornos e reversões de antecipação na comissão. | Estorno abate comissão pela taxa vigente na data da venda original (RC-03). | Trata estornos de competências passadas. |
| **Q-03** | 2026-10-16 | Divisão de spread, operação duplicada e trava expirada em Remessas. | Tarvo fica com 50% do spread; duplicata expurgada; spreads negativos fora da nota (RC-10 a RC-13). | Define receita exata de remessa (R$ 39.543,45). |
| **Q-04** | 2026-10-16 | Tomador da Nota Fiscal de serviços de remessa. | Uma única nota fiscal faturada contra a parceira **Ponte Câmbio S.A.** (RC-16). | Simplificação de faturamento (1 única NF). |
| **Q-05** | 2026-10-16 | Lançamentos de mútuo e comissões anteriores nos extratos bancários. | Lançamentos de mesma titularidade vão para `1.1.09.001`; comissão recebida baixa `1.1.03.002`. | Evita distorção de receita no resultado. |
| **Q-06** | 2026-10-16 | Estabelecimentos ausentes na planilha de taxas e Atlas Idiomas. | Mapeamento por EC confirmado (RC-06); Atlas Idiomas sem contrato fica retida (RC-05). | Elimina 100% das transações órfãs. |
