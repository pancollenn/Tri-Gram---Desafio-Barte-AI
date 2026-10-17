# Momentos que importaram (uso de IA)

> Exigência do edital: marque de **2 a 4 momentos** que importaram. Para cada um, uma ou duas frases: **o que pedimos**, **o que a IA devolveu** e **o que fizemos com isso**. **Pelo menos um** deve ser um momento em que a IA errou ou nos levou ao lugar errado.
>
> O histórico completo das sessões (transcript do Claude Code/Antigravity, link da conversa, export ou print) está preservado nesta pasta `PROMPTS/`, sem edição (com chaves de API e dados pessoais removidos).

## Histórico das sessões de IA registradas

| Arquivo / Pasta | Ferramenta | Autor | Objetivo / Escopo da Sessão |
|---|---|---|---|
| `sessao_parse_orbe.md` | Antigravity (Claude Sonnet) | Victor | Implementação do parser de Checkout (`src/parsers/parse_orbe.py`) e suíte de testes (`tests/test_parse_orbe.py`): extração do CSV da Orbe, cruzamento com taxas vigentes em Excel, mapeamento de ECs faltantes, vigência temporal da Bridge Idiomas, acordo taxa zero da Casa do Estudante e pendência da Atlas Idiomas. |
| `sessao_classifier.md` | Antigravity (Claude Sonnet) | Victor | Implementação do motor híbrido de classificação contábil (`src/ai/classifier.py`): análise das regras contábeis RC-17 a RC-21, sistema em cascata (regra determinística → regex heurístico → conta transitória), atribuição dos métodos `REGRA`/`IA`/`HUMANO` e integração com `RastroTracker`. |
| `sessao_parse_extratos.md` | Antigravity (Claude Sonnet) | Victor | Implementação do parser de extratos bancários Aurora CSV (`ref_origem = L<n>`), Meridiano OFX (`ref_origem = <FITID>`) e plano analítico Fênix ERP (`src/parsers/parse_extratos.py`). |
| `momentos_fernando.md` | Antigravity | Fernando | Planejamento tático, concepção da Arquitetura Híbrida 1:1, modelagem financeira das regras de negócio, blindagem dos contratos de dados, desacoplamento do Nível Mínimo e catalogação das pendências. |
| `prompts_fernando/conversa_*.md` | Antigravity | Fernando | Transcripts completos das sessões 1 a 5 cobrindo desde a arquitetura de alto nível até a orquestração de testes e blindagem de contratos de integração entre integrantes do squad. |

---

## Momento 1: 💡 Usuário corrige visão da IA e força arquitetura com mapeamento direto 1:1

- **Tipo:** ☐ Acerto da IA · ☐ Erro/alucinação da IA corrigido por nós · ☑ **Decisão nossa contra a sugestão da IA**
- **Quem / quando:** Fernando, Sessão de Arquitetura
- **O que pedimos:** A IA inicialmente defendia agrupar o código por domínio vertical (`checkout.py`, `remessas.py`, `bancos.py`) acumulando regras em arquivos genéricos. Questionamos incisivamente: *"no modelo que você fez fica difícil de visualizar e entender; ter um arquivo que faz comissões, divergências, notas, classifier e pendências mapeadas 1:1 para cada CSV de saída da banca não é muito mais limpo e auditável?"*.
- **O que a IA devolveu:** A IA reconheceu a opacidade da proposta anterior, acatou a crítica estrutural e desenhou a **Arquitetura Híbrida 2.0**, reorganizando `src/engine/` para que cada script seja o responsável exclusivo por exatamente um CSV do gabarito oficial (`comissoes.py`, `divergencias.py`, `notas.py`, `pendencias.py`, `rastro.py`).
- **O que fizemos com isso:** Adotamos essa separação estrita, resgatando os módulos `notas.py` e `pendencias.py` que estavam diluídos, eliminando riscos de sobreposição entre integrantes e simplificando drasticamente a auditoria da banca.
- **Evidência:** Transcript em `PROMPTS/momentos_fernando.md#L54-L63` e estrutura consolidada em `especificacao_scripts.md`.

---

## Momento 2: ⚠️ Confusão entre premissa de arquitetura do time e restrição imposta pelo edital

- **Tipo:** ☐ Acerto da IA · ☑ **Erro/alucinação da IA corrigido por nós** · ☐ Decisão nossa contra a sugestão da IA
- **Quem / quando:** Victor, 15:30
- **O que pedimos:** Questionamos por que a camada de IA utilizava heurísticas com regex para classificar transações em vez de uma chamada direta a um modelo de linguagem (LLM).
- **O que a IA devolveu (e por que estava errado):** A IA afirmou categoricamente que não usar chamadas de LLM externas ou chaves de API era um "requisito formal do desafio". Isso estava incorreto: a premissa de executar localmente sem depender de chave de API externa era uma salvaguarda de resiliência e fallback adotada pelo time, e não uma proibição imposta pelo edital da Barte.
- **O que fizemos com isso:** Confrontamos a IA exigindo a referência textual das instruções (*"onde nas instruções está escrito que isso é um requisito do desafio?"*). Diante do questionamento, a IA inspecionou o PDF do edital, admitiu o engano e ajustou a implementação para permitir chamadas de LLM reais via chave de ambiente com fallback garantido por regras determinísticas.
- **Evidência:** `PROMPTS/sessao_classifier.md` e trecho documentado em `PROMPTS/MOMENTOS.md`.

---

## Momento 3: 🌟 Alinhamento contábil de competência: Baixa de Passivo vs. Nova Despesa (Bancos & ERP)

- **Tipo:** ☑ **Acerto da IA** · ☐ Erro/alucinação da IA corrigido por nós · ☐ Decisão nossa contra a sugestão da IA
- **Quem / quando:** Fernando, Sessão Contábil
- **O que pedimos:** Solicitamos uma explicação simplificada e de negócio do módulo "Bancos & ERP", pois a classificação contábil no plano de contas do ERP Fênix apresentava ambiguidades entre movimentação de caixa e regime de competência.
- **O que a IA devolveu:** A IA explicou a distinção de competência e identificou a principal armadilha contábil do case: pagamentos de folha de salários e tributos (DARF, GPS, FGTS) realizados nos primeiros dias de setembro referem-se à competência de **agosto**, devendo ser classificados como **baixa de passivo já provisionado** (`2.1.04.xxx` e `2.1.03.xxx`), e não como nova despesa do mês (`4.2.xxx`).
- **O que fizemos com isso:** Formalizamos a regra em `HIPOTESES.md` (RC-18) e a implementamos nas regras prioritárias de `src/ai/classifier.py`, evitando duplicidade indevida de despesas no resultado contábil da Tarvo.
- **Evidência:** Regra implementada em `src/ai/classifier.py#L82-L140` e documentada em `PROMPTS/momentos_fernando.md#L76-L84`.

---

## Momento 4: 🔍 Usuário desafia acoplamento de código e exige execução isolada do Nível Mínimo

- **Tipo:** ☐ Acerto da IA · ☐ Erro/alucinação da IA corrigido por nós · ☑ **Decisão nossa contra a sugestão da IA**
- **Quem / quando:** Fernando, Sessão de Integração
- **O que pedimos:** Ao inspecionar a assinatura conjunta `calcular_comissoes(dados_checkout, dados_remessas, tracker)` em `src/main.py`, identificamos uma dependência cruzada e cobramos: *"a função usa dados_remessas e tracker; como garantir que ela rode perfeitamente apenas com dados_checkout para validar o nível mínimo de forma isolada?"*.
- **O que a IA devolveu:** A IA inicialmente tratava a função como um bloco indissociável. Provocada pelo usuário, refatorou a lógica interna com condicionais independentes (`if transacoes: ...` e `if operacoes: ...`), assegurando que `dados_remessas={}` execute de ponta a ponta sem falhas.
- **O que fizemos com isso:** Criamos o flag de CLI `python src/main.py --modulos checkout`, garantindo que o Nível Mínimo pudesse ser testado e auditado de forma autônoma antes do término dos módulos de câmbio.
- **Evidência:** Separação em `src/engine/comissoes.py` e registro em `PROMPTS/momentos_fernando.md#L101-L109`.
