# Hipóteses, regras confirmadas e perguntas

Este documento separa **o que sabemos** (confirmado pelo financeiro da Tarvo, Helena, no canal `#tarvo-financeiro`) **do que assumimos** (premissas nossas, sujeitas a revisão). Regra de ouro do time: se a resposta estava a uma pergunta de distância, perguntamos em vez de assumir.

Legenda de status: ✅ confirmada · ⚠️ assumida (revisar) · ❓ aberta (decisão humana)

---

## 1. Regras confirmadas pelo financeiro (Helena, Slack)

### 1.1 Checkout (Orbe x tabela de taxas)

| ID | Regra confirmada | Impacto no código | Status |
|---|---|---|---|
| RC-01 | A comissão e a nota do checkout são calculadas pela **taxa contratada** (`valor_bruto × taxa_contratada / 100`), linha a linha, **não** pela taxa aplicada pela Orbe. | `checkout.py` | ✅ |
| RC-02 | Diferença entre taxa aplicada e contratada é **divergência**: não altera a comissão; é reportada em `divergencias_taxa.csv` (valor devolvido ao lojista/cobrado da adquirente). | `checkout.py` | ✅ |
| RC-03 | **Estornos** abatem a comissão de setembro pela taxa contratada **vigente na data da venda original** (inclusive vendas de agosto). **Reversão de antecipação** anula a taxa da antecipação que reverte. | `checkout.py` | ✅ |
| RC-04 | **Casa do Estudante** (EC `1018325654`): taxa contratada de checkout = **0,00%** (setembro a dezembro/2026, acordo comercial). Tudo que a Orbe cobrou dela é divergência; comissão = R$ 0,00; não emite nota. | `config.py`, `checkout.py` | ✅ |
| RC-05 | **Atlas Idiomas** (EC `1076801732`): sem contrato assinado em 2026. **Não faturar**; isolar em `pendencias.csv`. | `config.py`, `checkout.py` | ✅ |
| RC-06 | ECs ausentes na planilha de taxas: `1043300981` = Novo Horizonte Intercâmbio; `1043396662` = Horizonte Viagens e Turismo; `1038867654` = Kiwi Experience. | `config.py` | ✅ |
| RC-07 | Arredondamento comum para o centavo, meio centavo para cima (`0,005 → 0,01`). A **Orbe trunca** os centavos; diferença de 1 centavo causada por isso **não é divergência**. | `config.round_half_up` | ✅ |
| RC-08 | Spread/taxas em branco ou "padrão" na planilha equivalem a **1,50%**. Aba `ANTIGO 2025 - nao usar` é ignorada. | `checkout.py`, `remessas.py` | ✅ |
| RC-09 | Uma nota por lojista com comissão total positiva; saldo zero ou negativo **não emite** nota. | `checkout.py` | ✅ |

### 1.2 Remessas (Ponte Câmbio x tabela de taxas)

| ID | Regra confirmada | Impacto no código | Status |
|---|---|---|---|
| RC-10 | Comissão da Tarvo = **50% do `Spread R$`** realizado, calculada e arredondada **operação por operação**. | `remessas.py` | ✅ |
| RC-11 | Para a competência vale a **Data de Contratação**. | `remessas.py` | ✅ |
| RC-12 | **Operação repetida** (`PC-0926-0162`, Bagagem Livre Turismo, marcada "reprocessada"): conta **uma única vez**; a linha duplicada entra na lista de correção da Ponte (pendência). | `remessas.py` | ✅ |
| RC-13 | **4 spreads negativos** (`PC-0926-0210`, `-0326`, `-0491`, `-0545`): trava D-1 expirada (> 2h). Ficam **fora da comissão e fora da nota**; vão para contestação em `pendencias.csv` (e `divergencias_taxa.csv`). | `remessas.py` | ✅ |
| RC-14 | **Mundo Aberto Intercâmbio**: Ponte cobrou 1,50% e o contrato prevê 1,20%. A nota sai pelo realizado; a diferença **cheia** é divergência e pendência de contestação com a Ponte. | `remessas.py` | ✅ |
| RC-15 | Status de compliance "aprovado com ressalva" **não** altera liquidação nem comissão. | `remessas.py` | ✅ |
| RC-16 | **Uma única nota** de remessa, contra a **Ponte Câmbio S.A.** (CNPJ `75374179000146`), pelo total das comissões válidas. | `remessas.py`, `main.py` | ✅ |

### 1.3 Bancos (Aurora e Meridiano x plano de contas Fênix)

| ID | Regra confirmada | Impacto no código | Status |
|---|---|---|---|
| RC-17 | `conta_codigo` é a **contrapartida** do lançamento bancário no plano de contas. | `bancos.py` | ✅ |
| RC-18 | **Folha e tributos de agosto pagos em setembro baixam passivos já provisionados** (ex.: `2.1.04.001`, grupo `2.1.03.xxx`); não são despesa de setembro. | `bancos.py` | ✅ |
| RC-19 | Comissão de câmbio de agosto recebida em 04/09 (FITID `MRD2026090132`) baixa o ativo `1.1.03.002` (comissões a receber). | `bancos.py` | ✅ |
| RC-20 | Despesas correntes não provisionadas entram diretamente em `4.2.xxx`. | `bancos.py` | ✅ |
| RC-21 | Transferências entre contas próprias (Aurora ↔ Meridiano) vão para a transitória `1.1.09.001`. Crédito sem identificação (R$ 7.350,00) vai para `1.1.09.002` e vira pendência. | `bancos.py` | ✅ |
| RC-22 | A liquidação da Orbe no Aurora não fecha com o relatório analítico do mês (débito/Pix no dia seguinte, crédito ao longo dos meses). Não é erro. | (informativo) | ✅ |

---

## 2. Exceções encaminhadas a pessoas (`pendencias.csv`)

| # | Pendência | `ref_origem` | Quem decide |
|---|---|---|---|
| 1 | Contestar com a Ponte os 4 spreads negativos | `PC-0926-0210`, `-0326`, `-0491`, `-0545` | Financeiro Tarvo (Helena) |
| 2 | Retificação do relatório da Ponte (operação repetida) | `PC-0926-0162` | Financeiro Tarvo (Helena) |
| 3 | Contestar excesso de spread da Mundo Aberto (1,50% x 1,20%) | operações da Mundo Aberto | Financeiro Tarvo (Helena) |
| 4 | Devolver taxas cobradas da Casa do Estudante (contrato = 0,00%) | transações da Casa do Estudante | Financeiro Tarvo (Helena) |
| 5 | Confirmar/assinar contrato da Atlas Idiomas | EC `1076801732` | Comercial Tarvo (Diego) |
| 6 | Identificar remetente de Pix de R$ 7.350,00 | Aurora `L50` | Financeiro Tarvo (Helena) |
| 7 | Investigar devolução de Pix de R$ 12.400,00 da Mundo Aberto | Aurora `L65` | Financeiro Tarvo (Helena) |

---

## 3. Premissas assumidas (arquitetura e interpretação)

Premissas do time. Cada uma deve ser validada com o financeiro quando possível.

| ID | Premissa | Justificativa | Risco se estiver errada | Status |
|---|---|---|---|---|
| PA-01 | A solução rodará em outubro com arquivos de **mesmo formato e nomes similares**; por isso os arquivos de entrada são localizados por padrão (`config.PADROES_ENTRADA`), sem datas fixas no código. | LEIA-ME do data pack. | Nome muito diferente exige ajustar o padrão. | ⚠️ |
| PA-02 | Cada linha de `rastro.csv` registra a **contribuição** da linha de origem ao número reportado (ex.: comissão da transação), não o valor bruto. | O edital exige que a soma de `valor` por `id_saida` feche com o reportado. | Gabarito poderia esperar o bruto no rastro. | ⚠️ |
| PA-03 | Cada comissão por lojista e cada nota têm `id_saida` próprios; a nota repete o rastro da comissão correspondente. | Permite auditar comissão e nota separadamente. | Nenhum material. | ⚠️ |
| PA-04 | O casamento de lojistas é **por EC/CNPJ**, nunca por similaridade de nome. | O edital cita casamento aproximado como erro comum. | Lojista não mapeado vira pendência. | ⚠️ |
| PA-05 | Valores monetários são gravados com 2 casas e ponto decimal; percentuais com no mínimo 2 casas (`2.59`). | Contrato do edital. | Nenhum. | ⚠️ |
| PA-06 | Casos novos não cobertos pelas regras (outubro) vão para `pendencias.csv` em vez de serem decididos pelo código. | Evita "alarme falso" e decisão sem aval do financeiro. | Mais pendências manuais. | ⚠️ |

### Modelo para novas premissas

Copie a linha abaixo para a tabela acima (próximo `PA-NN`) sempre que assumirmos algo sem confirmação:

```
| PA-NN | <o que assumimos> | <por que assumimos / fonte> | <o que quebra se estiver errado> | ⚠️ |
```

---

## 4. Perguntas feitas ao financeiro

Registrar toda pergunta (data, hora, canal). Perguntas boas têm impacto financeiro explícito.

| # | Data/hora | Canal | Pergunta | Resposta | Impacto da decisão |
|---|---|---|---|---|---|
| Q-01 | 2026-10-16 | #tarvo-financeiro | Na divergência de taxa, comissão e nota são calculadas pela taxa aplicada ou pela contratada? | Pela **taxa contratada** (RC-01, RC-02). | Define o valor de toda a comissão de checkout. |
| Q-02 | 2026-10-16 | #tarvo-financeiro | Como estornos e reversões afetam a comissão? A Tarvo devolve a comissão no estorno? | Estorno abate pela taxa da data da venda original (RC-03). | Estornos de agosto abatem setembro. |
| Q-03 | 2026-10-16 | #tarvo-financeiro | Regra de divisão do spread; critério de "operação repetida"; quem aprova spread negativo? | 50% do spread; duplicata computada uma vez; negativos excluídos e contestados (RC-10, RC-12, RC-13). | Base da comissão de remessa. |
| Q-04 | 2026-10-16 | #tarvo-financeiro | Quem é o tomador da NF de remessa (lojista ou Ponte Câmbio)? | Uma única nota contra a Ponte Câmbio (RC-16). | Define destinatário e quantidade de notas. |
| Q-05 | 2026-10-16 | #tarvo-financeiro | Quais lançamentos não têm conta clara no plano de contas? Como tratar transferências entre contas próprias? | Contrapartida do banco; mútuos em `1.1.09.001` (RC-17 a RC-21). | Classificação de 188 lançamentos. |
| Q-06 | 2026-10-16 | #tarvo-financeiro | EC não encontrado na tabela de taxas (3 casos) e Atlas Idiomas. | Mapeamento por EC (RC-06); Atlas não fatura (RC-05). | Comissão de 4 lojistas. |

> Ajustar data/hora exatas das perguntas conforme o registro do Slack. O log do canal é a fonte oficial.

---

## 5. Questões abertas (atualizar durante o dia)

- [ ] _(adicionar aqui o que ainda depende de resposta do financeiro)_
