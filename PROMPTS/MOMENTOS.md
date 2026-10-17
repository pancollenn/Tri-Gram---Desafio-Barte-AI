# Momentos que importaram (uso de IA)

> Exigência do edital: marque de **2 a 4 momentos** que importaram. Para cada um, uma ou duas frases: **o que pedimos**, **o que a IA devolveu** e **o que fizemos com isso**. **Pelo menos um** deve ser um momento em que a IA errou ou nos levou ao lugar errado.
>
> O histórico completo das sessões (transcript do Claude Code/Antigravity, link da conversa, export ou print) deve ficar nesta pasta `PROMPTS/`, sem edição (só remover chaves de API e dados pessoais).

## Histórico das sessões (arquivos nesta pasta)

| Arquivo / link | Ferramenta | Quem | Para quê |
|---|---|---|---|
| _(ex.: `sessao_01_planejamento.md`)_ | _(ex.: Claude / Antigravity)_ | _(Pessoa N)_ | _(ex.: análise do case e arquitetura)_ |

| `sessao_parse_orbe` | Antigravity | Victor | Implementação do parser de Checkout (`src/parsers/parse_orbe.py`) e script de testes (`tests/test_parse_orbe.py`): extração do CSV da Orbe, cruzamento com taxas vigentes em Excel (resolução de ECs faltantes, vigência temporal da Bridge Idiomas, acordo da Casa do Estudante e pendência da Atlas Idiomas). |

| `sessao_classifier` | Antigravity (Claude Sonnet) | Victor | Implementação do motor híbrido de classificação contábil (`src/ai/classifier.py`): análise da arquitetura do projeto, mapeamento das regras RC-17 a RC-21 do `HIPOTESES.md`, construção do sistema em cascata (regra por `ref_origem` → regex por descrição → fallback conta transitória), atribuição dos métodos `REGRA`/`IA`/`HUMANO` por nível de confiança, integração com `RastroTracker` e discussão sobre a distinção entre decisão do time e requisito do edital no uso de API externa. |

---

## Momento 1: _(título curto)_

- **Tipo:** ☐ Acerto da IA · ☐ **Erro/alucinação da IA corrigido por nós** · ☐ Decisão nossa contra a sugestão da IA
- **Quem / quando:** _(Pessoa N, hh:mm)_
- **O que pedimos:** _(1 a 2 frases)_
- **O que a IA devolveu:** _(1 a 2 frases)_
- **O que fizemos com isso:** _(1 a 2 frases: como verificamos e o que mudou no código, na regra ou na pergunta ao financeiro)_
- **Evidência:** _(link ou trecho do transcript, commit, número que não fechava)_

---

## Momento 2: ⚠️ Confusão entre premissa de arquitetura do time e restrição imposta pelo edital

- **Tipo:** ☐ Acerto da IA · ☑ **Erro/alucinação da IA corrigido por nós** · ☐ Decisão nossa contra a sugestão da IA
- **Quem / quando:** Victor, 15:30
- **O que pedimos:** Questionamos por que a camada de IA utilizava heurísticas com regex para classificar transações em vez de uma chamada direta a um modelo de linguagem (LLM).
- **O que a IA devolveu (e por que estava errado):** A IA afirmou que não usar chamadas de LLM externas ou chaves de API era um "requisito formal do desafio". Isso estava incorreto: a regra presente no `README.md` ("sem chave de API, a solução roda por inteiro") tratava-se de uma diretriz arquitetural de resiliência e fallback adotada pelo próprio time, e não de uma proibição imposta pelo edital da Barte.
- **O que fizemos com isso:** Questionamos a IA sobre onde tal restrição estava escrita nas instruções do desafio. Diante do questionamento, a IA inspecionou a documentação, reconheceu a confusão entre premissa interna e restrição externa, mantendo a arquitetura de fallback gracioso como boa prática de engenharia, mas esclarecendo a liberdade de integração com LLMs reais quando chaves forem disponibilizadas.
- **Evidência:** Trecho do transcript da sessão em que o usuário indaga: *"onde nas instrucoes esta escrito que isso é um requisito do desafio?"* e a IA confirma a origem no README do repositório ([README.md#L33](file:///home/victor/Documents/Tri-Gram---Desafio-Barte-AI/README.md#L33-L34)).

---

## Momento 3: _(opcional)_

- **Tipo:** ☐ Acerto da IA · ☐ Erro/alucinação da IA corrigido por nós · ☐ Decisão nossa contra a sugestão da IA
- **Quem / quando:**
- **O que pedimos:**
- **O que a IA devolveu:**
- **O que fizemos com isso:**
- **Evidência:**

---

## Momento 4: _(opcional)_

- **Tipo:** ☐ Acerto da IA · ☐ Erro/alucinação da IA corrigido por nós · ☐ Decisão nossa contra a sugestão da IA
- **Quem / quando:**
- **O que pedimos:**
- **O que a IA devolveu:**
- **O que fizemos com isso:**
- **Evidência:**
