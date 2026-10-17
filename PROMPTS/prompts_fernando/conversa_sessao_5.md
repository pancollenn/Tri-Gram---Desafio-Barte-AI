# Conversa com IA — Sessão 5: Validação da Entrega Mínima (Checkout e Comissões), Auditoria Cega e Rastreabilidade

> **ID da Conversa:** `2ff27b9f-2152-4c30-8356-cb6119fb2ae8`  
> **Participante:** Fernando  
> **Data:** 17 de Outubro de 2026  
> **Ferramenta:** Google Antigravity IDE (Advanced Agentic AI)  
> **Tópicos:** Validação e conformidade da entrega mínima com o edital do hackathon (Checkout por lojista e Rastreabilidade), análise de conformidade de `parse_orbe.py` e `comissoes.py`, verificação da amarração de rastro (`RastroTracker`), testes automatizados de negócio (`tests/test_parse_orbe.py` e `tests/test_comissoes.py`), auditoria cega independente (`tests/validate_saida.py`), roteiro prático e detalhado para execução e validação interativa direta pelo desenvolvedor via terminal, e exportação dos registros de telemetria e prompts para atendimento aos critérios de governança do edital.

---

## 👤 Usuário (Interação #1)

@[c:\Unicamp\8_semestre\Hackaton_Barte\Tri-Gram---Desafio-Barte-AI\src\parsers\parse_orbe.py] @[c:\Unicamp\8_semestre\Hackaton_Barte\Tri-Gram---Desafio-Barte-AI\src\engine\comissoes.py] implementamos os arquivos nescessários para a entrega mínima, correto ou não? Se sim, como podemos validar que a entrega mínima está de fato funcionando?

## 🤖 Antigravity (Assistente) — Resposta #1

**Sim, está correto!** Para o escopo definido pelo edital do Hackathon (página 2 de `01_instrucoes_participantes.docx.pdf`) como **Nível Mínimo**:

> **Nível Mínimo:** *"Comissão de checkout por lojista, com rastro."*  
> **Regra Central Eliminatória:** *"Todo número da saída aponta para a linha de origem. Comissão sem rastro até as transações que a compõem não conta. Total que não fecha com a soma das linhas de origem conta como número inventado."*

Os arquivos responsáveis pelo core de Checkout foram implementados:
- [parse_orbe.py](file:///c:/Unicamp/8_semestre/Hackaton_Barte/Tri-Gram---Desafio-Barte-AI/src/parsers/parse_orbe.py): responsável pela ingestão do relatório da Orbe, cruzamento com as taxas vigentes no Excel, resolução dos ECs faltantes, vigência temporal da Bridge Idiomas, tratamento da Casa do Estudante, isolamento de lojistas sem contrato (Atlas Idiomas) e estornos amarrados à data original da venda.
- [comissoes.py](file:///c:/Unicamp/8_semestre/Hackaton_Barte/Tri-Gram---Desafio-Barte-AI/src/engine/comissoes.py): responsável pelo cálculo das comissões pela taxa contratada com arredondamento `round_half_up`, consolidação por CNPJ e registro individual de cada transação no `RastroTracker`.

> [!NOTE]
> Além desses dois arquivos de negócio, a entrega mínima depende diretamente da infraestrutura central já funcional:
> - [rastro.py](file:///c:/Unicamp/8_semestre/Hackaton_Barte/Tri-Gram---Desafio-Barte-AI/src/engine/rastro.py): motor do `RastroTracker` que grava [saida/rastro.csv](file:///c:/Unicamp/8_semestre/Hackaton_Barte/Tri-Gram---Desafio-Barte-AI/saida/rastro.csv);
> - [config.py](file:///c:/Unicamp/8_semestre/Hackaton_Barte/Tri-Gram---Desafio-Barte-AI/src/config.py): contratos de colunas, sanitização de CNPJs e constantes acordadas no Slack;
> - [main.py](file:///c:/Unicamp/8_semestre/Hackaton_Barte/Tri-Gram---Desafio-Barte-AI/src/main.py): orquestrador CLI que suporta a flag modular `--modulos checkout` e serializa os arquivos de saída.

---

## Como validar que a entrega mínima está de fato funcionando?

Foram disponibilizados **3 níveis de validação** que você pode rodar no terminal:

### 1. Validação unitária e de casos de negócio do Parser
Testa isoladamente se a leitura da Orbe e o enriquecimento com as taxas vigentes do Excel estão capturando todas as regras e exceções:

```bash
python tests/test_parse_orbe.py
```

* **O que é validado:** 9 cenários reais (Bridge antes e depois de 15/09, Casa do Estudante com tarifa 0.00%, Atlas Idiomas sem contrato, Kiwi Experience com EC recuperado, estorno atrelado à venda de agosto e ajustes tardios).
* **Resultado esperado:** 1.957 transações parseadas e validadas com sucesso.

---

### 2. Validação automatizada de Comissões e Rastreabilidade
Testa as regras financeiras de checkout tanto com dados sintéticos controlados quanto com a base real do `data_pack/`:

```bash
python tests/test_comissoes.py
```

* **O que é validado:**
  - 21 lojistas apurados no Checkout;
  - Total geral de comissões de Checkout: **R$ 203.740,84**;
  - Casa do Estudante apurada estritamente em **R$ 0,00**;
  - Atlas Idiomas excluída do faturamento;
  - 1.900 linhas registradas em [saida/rastro.csv](file:///c:/Unicamp/8_semestre/Hackaton_Barte/Tri-Gram---Desafio-Barte-AI/saida/rastro.csv);
  - **Resultado:** 13/13 testes aprovados (`0 falhas`).

---

### 3. Execução ponta a ponta com a Auditoria Cega do Edital
Executa o orquestrador apenas para a entrega mínima e aciona o script independente [validate_saida.py](file:///c:/Unicamp/8_semestre/Hackaton_Barte/Tri-Gram---Desafio-Barte-AI/tests/validate_saida.py) (que simula o corretor automático da banca):

```bash
python src/main.py --modulos checkout
```

* **O que é verificado:**
  1. Criação de [saida/comissoes_por_lojista.csv](file:///c:/Unicamp/8_semestre/Hackaton_Barte/Tri-Gram---Desafio-Barte-AI/saida/comissoes_por_lojista.csv) e [saida/rastro.csv](file:///c:/Unicamp/8_semestre/Hackaton_Barte/Tri-Gram---Desafio-Barte-AI/saida/rastro.csv);
  2. Formato estrito: separador `;`, codificação UTF-8 sem BOM, ausência de `NaN`/`null`, valores monetários com 2 casas decimais e CNPJ normalizado com 14 dígitos;
  3. **Conferência matemática centavo a centavo:** o validador recalcula a soma de todas as 1.900 linhas do rastro e compara com os 21 `id_saida` reportados.
* **Resultado:**
  ```text
  [OK] Rastro: 21 de 21 id(s) de comissão/nota fecham centavo a centavo
  [OK] rastro.csv: nenhum id_saida órfão
  Erros: 0 | Avisos: 4 (avisos naturais referentes aos módulos de Alvo/Extra ainda não executados)
  [OK] Auditoria APROVADA
  ```

Se quiser inspecionar cada um dos 21 IDs e seus valores detalhados pela auditoria, basta rodar:
```bash
python tests/validate_saida.py -v
```

## 👤 Usuário (Interação #2)

mas voce rodou tudo isso e eu não vi nada, não pedi para voce validar para mim. Quero saber como EU posso validar, e ver essa validação acontecendo.

## 🤖 Antigravity (Assistente) — Resposta #2

Perfeito! Aqui está o passo a passo exato para **você mesmo rodar no seu terminal**, ver a execução acontecer na sua frente e inspecionar os resultados com seus próprios olhos:

---

### Passo 0: Garantir que você está na pasta do projeto

No seu terminal (PowerShell ou terminal do VS Code), certifique-se de estar dentro da pasta do repositório:

```powershell
cd c:\Unicamp\8_semestre\Hackaton_Barte\Tri-Gram---Desafio-Barte-AI
```

*(Se você usa ambiente virtual `.venv`, ative-o com `.\.venv\Scripts\activate`)*

---

### Passo 1: Ver o enriquecimento de dados da Orbe acontecendo

Para ver o script lendo a planilha da Orbe, cruzando com a tabela de taxas e exibindo na sua tela os casos reais de negócio:

```powershell
python tests/test_parse_orbe.py
```

**O que você vai ver na tela:**
- O resumo de leitura (1.957 transações e 22 estabelecimentos);
- A checagem detalhada dos 9 casos de teste (como a taxa da **Bridge Idiomas** mudando antes e depois do dia 15/09, a **Casa do Estudante** com taxa 0.00%, e a **Atlas Idiomas** identificada como sem contrato).

**Dica para testar interativamente:** Você pode filtrar no terminal para inspecionar um estabelecimento específico:
```powershell
python tests/test_parse_orbe.py --ec 1018325654
```

---

### Passo 2: Ver o cálculo de comissões e a tabela de lojistas

Para ver o motor calculando as comissões e montando a tabela de fechamento:

```powershell
python tests/test_comissoes.py
```

**O que você vai ver na tela:**
1. A bateria de testes unitários passando (`[OK]`);
2. A integração com a base real imprimindo uma tabela completa com os **21 lojistas**, seus respectivos **CNPJs** e os **valores calculados em reais**;
3. A confirmação de que o somatório de cada um dos 21 lojistas bate exatamente com a soma das linhas de rastro.

---

### Passo 3: Gerar os arquivos CSV na pasta `saida/`

Agora rode o orquestrador principal para gerar os entregáveis oficiais da entrega mínima:

```powershell
python src/main.py --modulos checkout
```

**O que você vai ver no terminal:**
- Os logs de cada etapa sendo executada:
  ```text
  [main] [1/3 Ingestão] Lendo dados de Checkout (parse_orbe)...
  [main] [2/3 Engine] Calculando comissões (comissoes.py)...
  [main] comissoes_por_lojista.csv: 21 linha(s)
  [main] rastro.csv: 1900 linha(s)
  [main] Executando auditoria (tests/validate_saida.py) ...
  ```
- O script `tests/validate_saida.py` rodará ao final e emitirá o relatório `[OK]` na sua tela.

---

### Passo 4: Conferir os arquivos gerados com os seus próprios olhos

Após rodar o comando acima, você pode abrir e inspecionar diretamente os arquivos criados na pasta `saida/`:

1. **Abrir no próprio VS Code:**
   - [saida/comissoes_por_lojista.csv](file:///c:/Unicamp/8_semestre/Hackaton_Barte/Tri-Gram---Desafio-Barte-AI/saida/comissoes_por_lojista.csv)
   - [saida/rastro.csv](file:///c:/Unicamp/8_semestre/Hackaton_Barte/Tri-Gram---Desafio-Barte-AI/saida/rastro.csv)

2. **Ou ver as linhas diretamente no seu terminal PowerShell:**
   ```powershell
   Get-Content saida\comissoes_por_lojista.csv
   ```

3. **Ver o rastro de um lojista específico:**
   Para ver todas as transações individuais que formaram a comissão do primeiro lojista (`COM-0001`):
   ```powershell
   Select-String -Path saida\rastro.csv -Pattern "COM-0001" | Select-Object -First 10
   ```

---

### Passo 5: Rodar a auditoria cega detalhada (modo verboso)

Para ver a auditoria oficial conferindo e listando **cada um dos 21 IDs um a um**, use a flag `-v`:

```powershell
python tests/validate_saida.py -v
```

Ele listará todas as conferências na tela:
```text
[OK] Rastro COM-0001 (comissoes_por_lojista.csv): 0.00 = soma de rastro.csv
[OK] Rastro COM-0002 (comissoes_por_lojista.csv): 9259.74 = soma de rastro.csv
...
[OK] Rastro: 21 de 21 id(s) de comissão/nota fecham centavo a centavo
```

## 👤 Usuário (Interação #3)

Por favor, exporte todo o histórico completo desta nossa conversa atual para um arquivo Markdown legível em:
`c:\Unicamp\8_semestre\Hackaton_Barte\Tri-Gram---Desafio-Barte-AI\PROMPTS\prompts_fernando\conversa_sessao_X.md` (ajuste o nome do arquivo se desejar).

Para fazer isso de forma automatizada e sem cortes:
1. Localize o arquivo `transcript_full.jsonl` da conversa atual (localizado no diretório de logs em `.system_generated/logs/transcript_full.jsonl` dentro do diretório desta conversa).
2. Execute um script Python que leia esse JSONL, extraia em ordem cronológica as mensagens do Usuário (`USER_INPUT`, limpando tags de metadados) e as respostas do Assistente (`PLANNER_RESPONSE`), sanitizando eventuais chaves de API.
3. Salve o arquivo Markdown formatado diretamente no caminho indicado.

## 🤖 Antigravity (Assistente) — Resposta #3

O histórico completo desta nossa Sessão 5 foi exportado com sucesso para o arquivo:
`c:\Unicamp\8_semestre\Hackaton_Barte\Tri-Gram---Desafio-Barte-AI\PROMPTS\prompts_fernando\conversa_sessao_5.md`

Além do documento Markdown legível e formatado, os arquivos brutos de telemetria também foram salvos como garantia de auditabilidade:
- `transcript_full_sessao_5.jsonl`
- `transcript_sessao_5.jsonl`

---
