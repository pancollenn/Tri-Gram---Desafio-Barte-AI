# Momentos que importaram (uso de IA)

> Exigência do edital: marque de **2 a 4 momentos** que importaram. Para cada um, uma ou duas frases: **o que pedimos**, **o que a IA devolveu** e **o que fizemos com isso**. **Pelo menos um** deve ser um momento em que a IA errou ou nos levou ao lugar errado.
>
> O histórico completo das sessões (transcript do Claude Code/Antigravity, link da conversa, export ou print) deve ficar nesta pasta `PROMPTS/`, sem edição (só remover chaves de API e dados pessoais).

## Histórico das sessões (arquivos nesta pasta)

| Arquivo / link | Ferramenta | Quem | Para quê |
|---|---|---|---|
| _(ex.: `sessao_01_planejamento.md`)_ | _(ex.: Claude / Antigravity)_ | _(Pessoa N)_ | _(ex.: análise do case e arquitetura)_ |

| `sessao_parse_orbe` | Antigravity | Victor | Implementação do parser de Checkout (`src/parsers/parse_orbe.py`) e script de testes (`tests/test_parse_orbe.py`): extração do CSV da Orbe, cruzamento com taxas vigentes em Excel (resolução de ECs faltantes, vigência temporal da Bridge Idiomas, acordo da Casa do Estudante e pendência da Atlas Idiomas). |

---

## Momento 1: _(título curto)_

- **Tipo:** ☐ Acerto da IA · ☐ **Erro/alucinação da IA corrigido por nós** · ☐ Decisão nossa contra a sugestão da IA
- **Quem / quando:** _(Pessoa N, hh:mm)_
- **O que pedimos:** _(1 a 2 frases)_
- **O que a IA devolveu:** _(1 a 2 frases)_
- **O que fizemos com isso:** _(1 a 2 frases: como verificamos e o que mudou no código, na regra ou na pergunta ao financeiro)_
- **Evidência:** _(link ou trecho do transcript, commit, número que não fechava)_

---

## Momento 2: ⚠️ _(erro/alucinação da IA que corrigimos, obrigatório)_

- **Tipo:** ☐ Acerto da IA · ☑ **Erro/alucinação da IA corrigido por nós** · ☐ Decisão nossa contra a sugestão da IA
- **Quem / quando:** _(Pessoa N, hh:mm)_
- **O que pedimos:** _(1 a 2 frases)_
- **O que a IA devolveu (e por que estava errado):** _(1 a 2 frases: a resposta incorreta e como percebemos, ex.: soma que não fechava com o rastro, regra inventada em vez de perguntada)_
- **O que fizemos com isso:** _(1 a 2 frases: como corrigimos e a salvaguarda adicionada)_
- **Evidência:** _(link ou trecho do transcript, commit, teste que passou a falhar/passar)_

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
