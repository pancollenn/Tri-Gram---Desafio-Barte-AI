# Registro de Sessão e Momentos com IA — Fernando

> Este documento registra as discussões, decisões de arquitetura e momentos marcantes (acertos, erros e correções) ocorridos durante as sessões de planejamento, estruturação de pastas e modelagem de regras de negócio.
> 
> **Objetivo:** Servir de base para posterior seleção e consolidação dos momentos finais em `PROMPTS/MOMENTOS.md`.

---

## 📋 Resumo da Sessão (O que foi desenvolvido neste chat)

1. **Análise Comparativa de Arquiteturas:**
   - Confronto entre a abordagem por domínio de negócio (`checkout.py`, `remessas.py`, `bancos.py`) e a proposta do outro integrante em camadas técnicas (`parsers/`, `engine/`, `ai/`).
   - Veredito técnico unânime: **Eliminação de Frontend e Backend REST** (foco 100% no motor de dados CLI e nos 6 CSVs avaliados pelo regulamento).
   - Escolha do **Python** para manipulação determinística de centavos (`Decimal`) e automação de arquivos complexos (`.eml` com anexo em base64 e extrato bancário `.ofx`).

2. **Refinamento Arquitetural Conduzido pelo Usuário (A Arquitetura Híbrida 1:1):**
   - O usuário contestou a estrutura por domínio, apontando que concentrar múltiplas responsabilidades em arquivos genéricos (`checkout.py`) tornava a visualização opaca.
   - Criação da **Arquitetura Híbrida 2.0**: cada script em `src/engine/` passa a ter mapeamento **1 para 1 direto com o arquivo CSV de saída** exigido pela banca:
     - `engine/comissoes.py` ➔ `comissoes_por_lojista.csv`
     - `engine/divergencias.py` ➔ `divergencias_taxa.csv`
     - `engine/notas.py` ➔ `notas_a_emitir.csv` *(resgatando item omitido na proposta paralela)*
     - `engine/pendencias.py` ➔ `pendencias.csv` *(resgatando item omitido na proposta paralela)*
     - `engine/rastro.py` ➔ `rastro.csv` *(com `RastroTracker` para garantir soma exata de centavos)*
     - `ai/classifier.py` ➔ `lancamentos_classificados.csv`

3. **Modelagem Visual e Conceitual de Negócio:**
   - Criação de diagramas Mermaid em `FLUXO_NEGOCIO_E_ARQUITETURA.md` e `diagrama.md` mapeando a circulação financeira e o pipeline técnico.
   - Desmistificação do módulo **Bancos & ERP**: distinção entre regime de competência vs caixa (salários e tributos de agosto pagos em setembro baixam passivo `2.1.xx`, em vez de virarem despesa do mês).

4. **Reorganização Física do Repositório (`Tri-Gram---Desafio-Barte-AI`):**
   - Criação dos pacotes `src/parsers/`, `src/engine/`, `src/ai/`.
   - Esqueletos modulares criados com type hints e docstrings das regras do edital.
   - Atualização do orquestrador `src/main.py` e do `README.md`.
   - Limpeza dos arquivos obsoletos do domínio anterior.

5. **Auditoria e Saneamento da Documentação da Equipe (Sessão Atual):**
   - Identificação de divergências críticas no documento de especificação trazido do Git (`especificacao_scripts.md`) em relação aos dados reais do `data_pack/` (nomes fictícios de arquivos, ausência do e-mail `.eml`, premissa falsa de CNPJ na Orbe e omissão do `src/config.py`).
   - Diagnóstico e saneamento de arquivos duplicados gerados por conflito de encoding (`especifica_o_dos_scripts_python.md` vs. `especificacao_scripts.md`), com posterior remoção e commit limpo pelo usuário.

6. **Blindagem de Contratos de Dados entre Integrantes:**
   - Definição do schema formal e tipos estritos do dicionário `dados_checkout` entregue pelo `parse_orbe.py` para o `comissoes.py`.
   - Adoção da estratégia de enriquecimento direto: o parser já anexa o CNPJ e a `taxa_contratada_pct` (em `Decimal`), liberando o cálculo para ser puramente matemático e focado no rastro.

7. **Desacoplamento e Modularização da Versão Mínima:**
   - Refatoração conceitual de `comissoes.calcular_comissoes` para aceitar `dados_remessas = {}` sem falhar, permitindo a execução isolada do Nível Mínimo via `python src/main.py --modulos checkout`.
   - Clarificação do papel de `parse_ponte.py` (que é o próprio parser de remessas da parceira Ponte Câmbio).

---

## 🎯 Candidatos a Momentos (Para seleção posterior em `MOMENTOS.md`)

---

### Candidato 1: 💡 Usuário corrige visão da IA e força arquitetura com mapeamento direto 1:1

- **Tipo:** ☐ Acerto da IA · ☐ Erro/alucinação da IA corrigido por nós · ☑ **Decisão nossa contra a sugestão da IA**
- **Quem / quando:** Fernando
- **O que pedimos:** A IA inicialmente defendia agrupar o código por domínio vertical (`checkout.py`, `remessas.py`, `bancos.py`) para evitar gargalos em equipe. Questionamos essa abordagem: *"o argumento é que ter um arquivo que faz comissões, divergências, classifier e rastro fica bem definido; no modelo que você fez fica difícil de visualizar e entender. Teria como a versão híbrida adaptar essas características mais bem definidas?"*.
- **O que a IA devolveu:** A IA reconheceu a opacidade do modelo anterior, acatou a crítica e estruturou a "Arquitetura Híbrida 2.0", reorganizando a pasta `src/engine/` para que cada script seja o responsável exclusivo por exatamente um CSV do gabarito (`comissoes.py`, `divergencias.py`, `notas.py`, `pendencias.py`, `rastro.py`).
- **O que fizemos com isso:** Adotamos essa estrutura modular, adicionando os módulos `notas.py` e `pendencias.py` que o colega havia esquecido, garantindo clareza total de responsabilidades sem risco de omissão de arquivos exigidos pela banca.
- **Evidência:** Prompt do usuário: *"no modelo que voce fez, com arquivos banco, checkout, config, isso não está muito claro, está difícil de vizualizar e entender..."* e posterior criação das pastas `src/parsers/`, `src/engine/` e `src/ai/`.

---

### Candidato 2: ⚠️ Precipitação da IA ao rodar pipeline sem solicitação do usuário

- **Tipo:** ☐ Acerto da IA · ☑ **Erro/alucinação da IA corrigido por nós** · ☐ Decisão nossa contra a sugestão da IA
- **Quem / quando:** Fernando
- **O que pedimos:** Pedimos estritamente para a IA editar a base de pastas e arquivos no repositório para refletir o novo plano híbrido desenhado.
- **O que a IA devolveu (e por que estava errado):** Além de criar as pastas e arquivos, a IA tomou a iniciativa não solicitada de executar `python src/main.py` contra o diretório de dados brutos e rodar o script de validação de saída, gerando logs extensos e confusão sobre o que havia sido de fato implementado ou testado prematuramente.
- **O que fizemos com isso:** Interrompemos imediatamente a postura autônoma da IA com a instrução direta: *"o que você executou e pra que? não entendi o que foi testado, sendo que eu tinha pedido a mudança de estrutura. Não rode nem edite mais nada, só explique rapidamente o que acabou de fazer"*. Isso fez a IA recuar, esclarecer que se tratava apenas de um teste de fumaça de imports e manter o código intacto para que o time assumisse a implementação real.
- **Evidência:** Transcript do usuário pontuando a execução indevida e exigência de explicação objetiva sobre o escopo da ação.

---

### Candidato 3: 🌟 Alinhamento conceitual contábil: Baixa de Passivo vs. Nova Despesa (Bancos & ERP)

- **Tipo:** ☑ **Acerto da IA** · ☐ Erro/alucinação da IA corrigido por nós · ☐ Decisão nossa contra a sugestão da IA
- **Quem / quando:** Fernando
- **O que pedimos:** Solicitamos uma explicação simplificada e compreensível do que era o módulo "Bancos & ERP", pois o conceito de conciliação bancária e classificação contábil no plano de contas do ERP Fênix não estava claro.
- **O que a IA devolveu:** A IA utilizou uma metáfora prática (extrato bancário pessoal vs. plano de contas corporativo) e identificou a principal armadilha contábil do desafio: pagamentos de folha de salários e tributos (DARF, GPS, FGTS) feitos no início de setembro referem-se à competência de **agosto**, devendo ser classificados como **baixa de passivo provisionado** (`2.1.04.xxx` e `2.1.03.xxx`), e não como despesa corrente do mês de setembro (`4.2.xxx`).
- **O que fizemos com isso:** Incorporamos essa regra diretamente na especificação do `src/ai/classifier.py` e do `parse_extratos.py`, evitando erros graves de duplicidade de despesas e garantindo o fechamento contábil exigido pelo case.
- **Evidência:** Arquivo `FLUXO_NEGOCIO_E_ARQUITETURA.md` e regras implementadas no `src/ai/classifier.py`.

---

### Candidato 4: 🛠️ Mitigação de dependência de equipe (Efeito Cascata / Waterfall)

- **Tipo:** ☑ **Acerto da IA** · ☐ Erro/alucinação da IA corrigido por nós · ☐ Decisão nossa contra a sugestão da IA
- **Quem / quando:** Fernando
- **O que pedimos:** Questionamos se a divisão por camadas proposta pelo colega (`parsers` -> `engine` -> `ai`) não geraria uma esteira onde "cada um faz de um jeito e temos que confiar no outro".
- **O que a IA devolveu:** A IA analisou o risco de um hackathon com prazo curto (18h30) e demonstrou que a camada pura em cascata geraria um gargalo em que os desenvolvedores da `engine` ficariam ociosos esperando os `parsers`. Propôs como salvaguarda:
  1. Contratos estritos de tipos no `config.py`;
  2. Implementação do `RastroTracker` na memória (para não perder centavos a posteriori);
  3. Script de teste cego independente (`tests/validate_saida.py`) que audita as saídas sem depender de confiança cega entre os integrantes.
- **O que fizemos com isso:** Adotamos os contratos e a auditoria cega como regra do squad, permitindo que os integrantes avançassem com segurança e feedback imediato de conformidade.
- **Evidência:** Implementação de `tests/validate_saida.py` e documentação em `especificacao_scripts.md`.

---

### Candidato 5: 🔍 Usuário desafia acoplamento de código e exige execução isolada do Nível Mínimo

- **Tipo:** ☐ Acerto da IA · ☐ Erro/alucinação da IA corrigido por nós · ☑ **Decisão nossa contra a sugestão da IA**
- **Quem / quando:** Fernando
- **O que pedimos:** Ao inspecionar a assinatura `calcular_comissoes(dados_checkout, dados_remessas, tracker)` em `src/main.py`, identificamos que a função dependia de `dados_remessas`. Questionamos incisivamente: *"mas a função comissoes.calcular_comissoes usa o dados_remessas e tracker, é possível fazer a função funcionar só com o dados_checkout para o mínimo?"*.
- **O que a IA devolveu:** A IA inicialmente tratava a função como um bloco conjunto. Diante da nossa provocação, a IA demonstrou como desacoplar a lógica interna através de condicionais independentes (`if dados_checkout.get("transacoes"): ...` e `if dados_remessas.get("operacoes"): ...`), mantendo o `tracker` ativo para fechar o rastro obrigatório do nível mínimo.
- **O que fizemos com isso:** Garantimos que a versão mínima pudesse ser executada e validada de forma 100% autônoma via `python src/main.py --modulos checkout`, sem que o time dependesse de ter o módulo de remessas pronto para garantir a primeira nota da banca.
- **Evidência:** Trecho de código refatorado em `src/engine/comissoes.py` com separação explícita entre Parte 1 (Checkout) e Parte 2 (Remessas).

---

### Candidato 6: 📐 Usuário cobra contrato de interface e schema formal entre integrantes para evitar quebra

- **Tipo:** ☐ Acerto da IA · ☐ Erro/alucinação da IA corrigido por nós · ☑ **Decisão nossa contra a sugestão da IA**
- **Quem / quando:** Fernando
- **O que pedimos:** Ao observar a transição entre o parser de checkout e o motor de comissões, cobramos garantias contra inconsistências: *"pelo que você disse um vai usar a saída do outro? estão corretas as saídas e entradas? explique como é feita essa conexão para garantir que não haja conflitos ou outros problemas."*
- **O que a IA devolveu:** A IA mapeou o fluxo através do orquestrador `main.py` e formalizou o contrato estrito de dados do dicionário `dados_checkout["transacoes"]` (nomes exatos das chaves, tipos `Decimal`, datas ISO `AAAA-MM-DD` e CNPJs limpos). Apresentou ainda a solução arquitetural de embutir a `taxa_contratada_pct` diretamente em cada transação no `parse_orbe.py`, evitando cálculos redundantes na engine.
- **O que fizemos com isso:** Estabelecemos esse schema como a interface imutável de trabalho entre os integrantes da squad, permitindo que quem implementava o parser e quem implementava a engine avançassem em paralelo com risco zero de `KeyError` ou divergência de tipos.
- **Evidência:** Schema documentado em `especificacao_scripts.md` e implementado fielmente em `src/parsers/parse_orbe.py` e `src/engine/comissoes.py`.

---

### Candidato 7: 💡 Questionamento crítico do usuário sobre o Edital ("Consumir arquivos como vêm")

- **Tipo:** ☑ **Acerto da IA** · ☐ Erro/alucinação da IA corrigido por nós · ☐ Decisão nossa contra a sugestão da IA
- **Quem / quando:** Fernando
- **O que pedimos:** Confrontamos uma dúvida regulatória que poderia custar a desclassificação do time: *"pode ter o parser mesmo? ja que ele fala que tem usar o formato original ou algo assim"*.
- **O que a IA devolveu:** A IA esclareceu com clareza jurídica e técnica a diferença entre "limpeza manual prévia" (proibida pelo edital: uma pessoa abrir o Excel ou e-mail e salvar manualmente um CSV limpo) e "parsing programático" (obrigatório: o código Python ler os arquivos brutos intactos do disco e normalizar em memória).
- **O que fizemos com isso:** Validamos a legitimidade da camada `src/parsers/` e mantivemos a diretriz de não tocar nos arquivos brutos da pasta `data_pack/`, garantindo que a execução seja 100% autônoma e à prova do teste cego de outubro.
- **Evidência:** Manutenção dos parsers nativos consumindo diretamente `.eml`, `.ofx`, `.xlsx` e `.csv` brutos.

---

### Candidato 8: 👥 Usuário exige plano tático orientado a pessoas e saneia duplicatas do repositório

- **Tipo:** ☐ Acerto da IA · ☐ Erro/alucinação da IA corrigido por nós · ☑ **Decisão nossa contra a sugestão da IA**
- **Quem / quando:** Fernando
- **O que pedimos:** A IA havia apresentado um planejamento por fases temporais genéricas. Reclamamos da falta de foco operacional: *"o planejamento tatico não é para executar as tarefas estabelecidas por integrante em 'Divisão de Trabalho entre Integrantes'? se sim separe o Planejamento Tático entre cada integrante"*. Além disso, questionamos a existência de dois arquivos de especificação idênticos trazidos pelo Git.
- **O que a IA devolveu:** A IA reestruturou o planejamento tático em três roteiros individuais acionáveis (Integrante 1: Ingestão Orbe; Integrante 2: Cálculo & Rastro; Integrante 3: QA & Validação) e identificou que o arquivo `especifica_o_dos_scripts_python.md` era uma duplicata gerada por problemas de acentuação no commit do colega.
- **O que fizemos com isso:** Excluímos o arquivo duplicado com `git rm`, comitamos a documentação correta (`commit ffa5128`) e distribuímos os papéis táticos com tarefas e testes unitários bem definidos para cada membro da equipe.
- **Evidência:** Commit `ffa5128: fix: especificacoes corretas` e divisão pessoa a pessoa documentada no chat.
