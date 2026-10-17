Especificação Técnica dos Scripts Python (`src/`)
Desafio Barte AI · Hackathon de AI Services  
Squad de Operações Financeiras, Conciliação e Fechamento Contábil  
Caso Tarvo Pagamentos · Fechamento de Setembro/2026
---
🏛️ 1. Visão Geral da Arquitetura
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
⚙️ 2. Módulo Central Compartilhado: `src/config.py`
Papel: Núcleo de contratos e regras de domínio da aplicação. Todos os demais módulos importam deste arquivo para garantir integridade e evitar duplicação.
Responsabilidades:
Contrato dos 6 CSVs de Saída: Define colunas exatas, tipos de dados, delimitador (`;`), encoding (`utf-8`) e formatação obrigatória (`AAAA-MM-DD` para datas, ponto `.` para decimal, 14 dígitos numéricos para CNPJs com zeros à esquerda preservados).
Localização Dinâmica de Arquivos (`PADROES_ENTRADA` / `localizar_arquivo`): Localiza os arquivos brutos via padrão `glob` (ex: `01_orbe_relatorio_comissoes_*.csv`, `03_email_ponte_cambio_relatorio_*.eml`). Isso garante que a solução rode para setembro/2026 e execute perfeitamente para outubro/2026 sem alteração de código.
Aritmética Financeira Precisa:
`para_decimal(val)`: Converte entradas para `Decimal` evitando erros de ponto flutuante binário.
`round_half_up(val)`: Arredondamento comum para 2 casas decimais (`ROUND_HALF_UP`, onde `0.005 -> 0.01` e `-0.005 -> -0.01`).
`clean_cnpj(val)`: Sanitização estrita para 14 dígitos numéricos (`00520815000100`).
`parse_decimal_ptbr(texto)`: Converte números no formato brasileiro (`1.234,56` ou `-389,00`) para `Decimal`.
Parâmetros e Regras de Negócio Confirmadas (Helena / Slack `#tarvo-financeiro`):
Mapeamento de ECs faltantes na tabela: `1043300981` (Novo Horizonte), `1043396662` (Horizonte Viagens), `1038867654` (Kiwi Experience).
Exceção de contrato ausente: `1076801732` (Atlas Idiomas - não faturar, enviar para pendências).
Exceção comercial: `1018325654` (Casa do Estudante - taxa de checkout 0.00%).
Tomador único de remessas: `Ponte Câmbio S.A.` (CNPJ `75.374.179/0001-46`).
Contas contábeis-chave do ERP Fênix (`1.1.03.002` comissões a receber câmbio, `1.1.09.001` mútuo Aurora/Meridiano, `1.1.09.002` créditos não identificados, passivos `2.1.04.001` e `2.1.03.xxx`).
---
🚀 3. Orquestrador Principal: `src/main.py`
Papel: Ponto de entrada unificado da aplicação (`python src/main.py`).
Responsabilidades:
Suportar execução total ou modular via CLI:
`python src/main.py`: Executa o pipeline completo e audita ao final.
`python src/main.py --modulos checkout`: Executa apenas Checkout (Nível Mínimo do edital).
`python src/main.py --data-dir <pasta>` e `--saida-dir <pasta>`: Parametrização de pastas.
`python src/main.py --estrito`: Trata avisos da auditoria como erros.
Coordenar a execução em etapas: Ingestão (`parsers/`) ➔ Cálculos (`engine/`) ➔ IA (`classifier.py`) ➔ Pendências (`pendencias.py`).
Validar a integridade do rastro através do `tracker.validar_todos()` antes da gravação.
Gravar os CSVs finais em `saida/` obedecendo rigorosamente à formatação de colunas de `config.ARQUIVOS_SAIDA`.
Acionar o auditor cego `tests/validate_saida.py` e reportar código de saída (0 = sucesso; 1 = falha de validação/rastro; 2 = erro de entrada).
---
📥 4. Camada de Ingestão e Padronização (`src/parsers/`)
`src/parsers/parse_orbe.py`
Papel: Leitura das transações brutas de Checkout (adquirência Orbe) e enriquecimento com os dados cadastrais e taxas contratuais.
Ponto de Entrada: `parse_orbe.parse_orbe_e_taxas(data_dir: Union[str, Path]) -> Dict[str, Any]` (invocado pelo `main.py`).
Entradas:
`01_orbe_relatorio_comissoes_*.csv` (delimitador `;`, valores monetários com vírgula pt-BR).
`02_tabela_taxas_contratadas*.xlsx` (aba `Taxas vigentes`, ignorando a aba antiga de 2025).
`06_orbe_ajustes_tardios_*.csv` (opcional: ajustes de fechamento em 30/09).
Particularidades dos Dados e Regras:
O CSV da Orbe não possui coluna de CNPJ; contém `cod_estabelecimento` (EC) e `nome_estabelecimento`.
O CNPJ e as taxas contratuais por modalidade (Débito, Crédito à vista, Crédito 2-6x, Crédito 7-12x, Pix, Antecipação) são cruzados a partir do `cod_estabelecimento`.
Para os ECs ausentes na planilha, aplica o mapeamento `config.EC_FALTANTES_TABELA` (Novo Horizonte, Horizonte Viagens, Kiwi Experience).
Trata vigência temporal de taxas na planilha (ex.: Bridge Idiomas possui uma linha até 14/09/2026 e nova taxa a partir de 15/09/2026).
Normaliza datas para formato ISO (`AAAA-MM-DD`) e converte valores financeiros para `Decimal`.
Preserva o identificador único de origem: `id_transacao` (ex: `TX88410932`).
Contrato Exato do Retorno (`Dict[str, Any]`):
`"transacoes"`: `List[Dict[str, Any]]` com todas as transações normalizadas e enriquecidas (1957 registros em setembro/2026), cada uma contendo:
`"id_transacao"`: `str` (ex: `'TX88410932'`, referência de origem para o `rastro.csv`).
`"data_movimento"`: `str` ISO (`AAAA-MM-DD`).
`"cod_estabelecimento"`: `str` (código EC da Orbe).
`"nome_estabelecimento"`: `str` (nome fantasia na adquirente).
`"tipo_lancamento"`: `str` (`'VENDA'`, `'ESTORNO'`, `'ANTECIPACAO'`, `'REVERSAO ANTECIPACAO'`).
`"modalidade"`: `str` (`'DEBITO'`, `'PIX'`, `'CREDITO A VISTA'`, `'CREDITO PARCELADO'` ou `''`).
`"qtd_parcelas"`: `Optional[int]` (número de parcelas para crédito parcelado).
`"bandeira"`: `str` (bandeira do cartão ou `'N/A'`).
`"valor_bruto"`: `Decimal` (valor transacionado; negativo em estornos).
`"taxa_aplicada_pct"`: `Decimal` (taxa cobrada pela Orbe em pontos percentuais).
`"valor_taxa"`: `Decimal` (tarifa retida pela Orbe).
`"valor_liquido"`: `Decimal` (valor repassado ao lojista).
`"id_referencia"`: `str` (referência do pedido/autorização).
`"data_venda_original"`: `str` (data ISO da venda original em estornos, ou `''`).
`"data_efetiva"`: `str` ISO (data usada na busca de taxa contratual: venda original p/ estornos, senão data_movimento).
`"cnpj"`: `Optional[str]` (14 dígitos numéricos, ou `None` se sem contrato).
`"lojista"`: `str` (razão social / nome canônico do lojista na tabela de taxas).
`"taxa_contratada_pct"`: `Optional[Decimal]` (taxa contratada aplicável em pontos percentuais; `0.00` p/ Casa do Estudante; `None` p/ Atlas Idiomas).
`"modalidade_contrato"`: `Optional[str]` (chave da coluna correspondente: `'debito'`, `'pix'`, `'credito_a_vista'`, `'credito_2_6x'`, `'credito_7_12x'`, `'antecipacao'`).
`"sem_contrato"`: `bool` (`True` para Atlas Idiomas / ECs não mapeados em 2026).
`"arquivo_origem"`: `str` (nome do arquivo CSV físico de onde a transação foi lida).
`"taxas_contrato"`: `Dict[str, Any]` (mapa de contratos estruturados indexado por EC).
`"arquivo_origem"`: `str` (nome do CSV principal lido).
`"arquivo_ajustes"`: `Optional[str]` (nome do arquivo de ajustes tardios, se presente).
`"caminho_orbe"` / `"caminho_taxas"` / `"caminho_ajustes"`: `Path` dos arquivos correspondentes.
`src/parsers/parse_ponte.py`
Papel: Ingestão das operações internacionais de câmbio a partir da mensagem de e-mail MIME e conferência de spreads com a tabela contratual.
Ponto de Entrada: `parse_ponte.parse_ponte_e_taxas(data_dir: Union[str, Path]) -> Dict[str, Any]` (invocado pelo `main.py`).
Entradas:
`03_email_ponte_cambio_relatorio_*.eml` (mensagem de e-mail MIME da parceira contendo anexo `.xlsx`).
`02_tabela_taxas_contratadas*.xlsx` (aba `Taxas vigentes`, coluna `Spread remessa`).
Particularidades dos Dados e Regras:
Extração Automatizada do Anexo: Extrair o arquivo `.xlsx` de dentro do `.eml` em memória via biblioteca nativa `email` e processá-lo com `openpyxl` (proibida extração manual em disco).
Seleção de Aba e Cabeçalho: Na planilha, selecionar a aba `Operações` (ignorar a aba `Resumo` para fechamento). As linhas 1 a 3 contêm título institucional, a linha 4 é vazia, o cabeçalho real situa-se na linha 5 e os dados iniciam na linha 6.
Spread Padrão Contratual: Células de spread de remessa vazias (`None`) ou com texto `'padrão'` na tabela de taxas assumem o valor contratual padrão `config.SPREAD_PADRAO_PCT` (`1.50%`), conforme nota de rodapé da planilha.
Normalização Estrita: Datas convertidas para formato ISO (`AAAA-MM-DD`), valores monetários e taxas para `Decimal`, e `CNPJ Cliente` sanitizado para exatamente 14 dígitos numéricos com zeros à esquerda.
Identificador de Origem Obrigatório: Preservar a coluna `Nº Operação` (ex: `PC-0926-0002`) como `ref_origem` indispensável para o `rastro.csv`.
Pré-classificação de Negócio (Facilitadores para a Engine):
Operação Repetida: Sinalizar a duplicata `PC-0926-0162` (`is_duplicada = True`).
Spreads Negativos: Sinalizar as 4 operações com estouro de trava D-1 (`PC-0926-0210`, `-0326`, `-0491`, `-0545`) com `is_spread_negativo = True`.
Operações Válidas: Marcar `is_valida_comissao = True` (228 operações sem duplicata e sem spread negativo).
Divergência de Taxa: Sinalizar as 23 operações da Mundo Aberto (`is_divergente_taxa = True`, cobrança de ~1.50% vs 1.20% contratado).
Contrato Exato do Retorno (`Dict[str, Any]`):
`"operacoes"`: Lista completa de todas as 233 operações enriquecidas com `ref_origem`, `cnpj`, `lojista`, `data`, `moeda`, `valor_brl`, `spread_brl`, `spread_pct`, `spread_contratado_pct`, `comissao_tarvo_brl` (50% se válida) e as flags booleanas (`is_valida_comissao`, `is_duplicada`, `is_spread_negativo`, `is_divergente_taxa`).
`"operacoes_validas"`: Lista das 228 operações válidas para cálculo de receita no `src/engine/comissoes.py` e notas no `src/engine/notas.py`.
`"operacoes_duplicadas"`: Lista com a duplicata para isolamento em `src/engine/pendencias.py`.
`"operacoes_spread_negativo"`: Lista com as 4 operações de spread negativo para contestação em `src/engine/pendencias.py` e `divergencias.py`.
`"operacoes_divergentes"`: Lista com as 23 operações da Mundo Aberto prontas para `src/engine/divergencias.py`.
`"spreads_contrato"` / `"spreads_contratados"`: Mapa `{cnpj_14_digitos: SpreadContratado}` onde cada item se comporta simultaneamente como `Decimal` em cálculos aritméticos e como dicionário de metadados cadastrais.
`"arquivo_origem"`: Nome exato do arquivo `.eml` (ex: `03_email_ponte_cambio_relatorio_set2026.eml`) para amarração no `rastro.csv`.
`"nome_anexo_xlsx"`: Nome do anexo extraído do e-mail para auditoria.
`"email_metadata"`: Metadados do e-mail recebido (`assunto`, `remetente`, `data_envio`, `corpo_texto`).
`src/parsers/parse_extratos.py`
Papel: Leitura dos extratos das duas contas bancárias da Tarvo e do plano de contas contábil.
Ponto de Entrada: `parse_extratos.parse_extratos_e_plano(data_dir: Union[str, Path]) -> Dict[str, Any]` (invocado pelo `main.py`).
Entradas:
`05a_extrato_banco_aurora_*.csv` (conta principal C/C 4471-0).
`05b_extrato_banco_meridiano_*.ofx` (conta de câmbio C/C 90233-5, formato OFX SGML 1.02).
`04_plano_de_contas_fenix_erp*.csv` (plano de contas analítico do ERP Fênix).
Particularidades dos Dados e Regras:
Banco Aurora (CSV): As primeiras 6 linhas contêm metadados da conta; os dados iniciam após o cabeçalho na linha 7. A referência de origem obrigatória pelo edital é o número da linha física do arquivo (`L8`, `L9`, `L50`, etc.).
Banco Meridiano (OFX): Fazer parse das tags SGML/XML (`<STMTTRN>`). A referência de origem obrigatória é a tag `<FITID>` (ex: `MRD2026090132`).
Converter valores para `Decimal` (débitos negativos, créditos positivos) e padronizar datas para formato ISO `AAAA-MM-DD`.
Contrato Exato do Retorno (`Dict[str, Any]`):
`"lancamentos_aurora"`: `List[Dict[str, Any]]`, cada item contendo:
`"banco"`: `config.BANCO_AURORA` (`'AURORA'`).
`"ref_origem"`: `str` no padrão `'L<n>'` (ex: `'L8'`, `'L10'`).
`"linha_arquivo"`: `int` (número da linha física original no CSV).
`"data"`: `str` ISO (`AAAA-MM-DD`).
`"descricao"`: `str` (histórico bancário original).
`"documento"`: `str` (número do documento / código de transação).
`"valor"`: `Decimal` (débito negativo, crédito positivo com 2 casas).
`"arquivo_origem"`: `str` (nome do arquivo físico `05a_extrato_banco_aurora_*.csv`).
`"lancamentos_meridiano"`: `List[Dict[str, Any]]`, cada item contendo:
`"banco"`: `config.BANCO_MERIDIANO` (`'MERIDIANO'`).
`"ref_origem"`: `str` extraída da tag `<FITID>` (ex: `'MRD2026090132'`).
`"data"`: `str` ISO (`AAAA-MM-DD`, extraída de `<DTPOSTED>`).
`"descricao"`: `str` (tag `<MEMO>`).
`"tipo_transacao"`: `str` (tag `<TRNTYPE>`, ex: `'CREDIT'`, `'DEBIT'`, `'OTHER'`).
`"valor"`: `Decimal` (tag `<TRNAMT>`, débito negativo, crédito positivo).
`"arquivo_origem"`: `str` (nome do arquivo físico `05b_extrato_banco_meridiano_*.ofx`).
`"plano_contas"`: `Dict[str, Dict[str, Any]]` (mapa indexado por `conta_codigo`), com:
`"conta_codigo"`: `str` (ex: `'1.1.03.002'`).
`"descricao"`: `str` (ex: `'Comissões a Receber - Câmbio'`).
`"natureza"`: `str` (`'DEVEDORA'` ou `'CREDORA'`).
`"grupo"`: `str` (`'ATIVO'`, `'PASSIVO'`, `'RECEITA'`, `'DESPESA'`).
`"arquivos"`: `Dict[str, str]` com os nomes dos arquivos lidos (`aurora`, `meridiano`, `plano`).
---
🧮 5. Camada de Regras de Negócio e Cálculos (`src/engine/`)
`src/engine/comissoes.py` (Missão 1)
Papel: Calcular a comissão líquida devida à Tarvo por lojista e por linha de negócio, registrando cada transação no `RastroTracker`.
Ponto de Entrada: `comissoes.calcular_comissoes(dados_checkout: Dict[str, Any], dados_remessas: Dict[str, Any], tracker: RastroTracker) -> List[config.Linha]` (invocado pelo `main.py`).
Entradas:
`dados_checkout`: dicionário retornado por `parse_orbe.parse_orbe_e_taxas`.
`dados_remessas`: dicionário retornado por `parse_ponte.parse_ponte_e_taxas`.
`tracker`: instância ativa de `RastroTracker`.
Regras de Negócio:
Checkout:
A comissão é calculada linha a linha pela taxa contratada (`valor_bruto × taxa_contratada_pct / 100`), e não pela taxa que a Orbe aplicou.
Arredondar cada linha para 2 casas com `round_half_up`.
Estornos: Abatem a comissão pela taxa vigente na data da venda original (`data_venda_original`).
Reversão de Antecipação: Anula a taxa da antecipação correspondente.
Casa do Estudante (EC `1018325654`): Taxa contratada 0.00% ➔ Comissão = `R$ 0.00`.
Atlas Idiomas (EC `1076801732`): Sem contrato 2026 ➔ Isolar em pendências, comissão não entra no faturamento.
Registra cada transação no rastro: `tracker.registrar(id_saida, tx["arquivo_origem"], tx["id_transacao"], comissao_linha)`.
Remessas:
Itera sobre `dados_remessas["operacoes_validas"]` (228 operações sem duplicata e sem spreads negativos).
Comissão Tarvo = 50% do `Spread R$` de cada operação válida (`round_half_up` por operação).
Expurgo de Duplicata: A operação repetida `PC-0926-0162` conta uma única vez.
Exclusão de Spreads Negativos: As 4 operações com estouro de trava D-1 (`PC-0926-0210`, `-0326`, `-0491`, `-0545`) ficam fora da comissão e fora da nota (enviadas para contestação).
Agrupa a comissão por lojista de remessa (ou consolida por CNPJ).
Registra cada operação no rastro: `tracker.registrar(id_saida, dados_remessas["arquivo_origem"], op["ref_origem"], comissao_linha)`.
Contrato Exato da Saída (`List[config.Linha]` para `saida/comissoes_por_lojista.csv`):
`"id_saida"`: `str` gerado via `tracker.novo_id(config.PREFIXO_COMISSAO)` (ex: `'COM-0001'`).
`"cnpj"`: `str` (14 dígitos numéricos com zeros à esquerda preservados).
`"lojista"`: `str` (razão social / nome do estabelecimento).
`"linha_negocio"`: `str` (`'CHECKOUT'` ou `'REMESSA'`).
`"comissao_brl"`: `Decimal` (soma das comissões líquidas do lojista na linha de negócio, arredondada em 2 casas).
`src/engine/divergencias.py` (Missão 2)
Papel: Apurar transação por transação as divergências entre a taxa contratada e a aplicada por parceiros e adquirentes.
Ponto de Entrada: `divergencias.apurar_divergencias(dados_checkout: Dict[str, Any], dados_remessas: Dict[str, Any], tracker: RastroTracker) -> List[config.Linha]` (invocado pelo `main.py`).
Entradas:
`dados_checkout`: retorno de `parse_orbe.parse_orbe_e_taxas`.
`dados_remessas`: retorno de `parse_ponte.parse_ponte_e_taxas`.
`tracker`: instância ativa de `RastroTracker`.
Regras de Negócio:
Checkout:
Apurar onde `abs(taxa_aplicada_pct - taxa_contratada_pct) > config.TOLERANCIA_TAXA_PP` (0.01 p.p.).
Calcular `diferenca_brl = round_half_up(valor_bruto * (taxa_aplicada_pct - taxa_contratada_pct) / 100)`.
Truncamento de 1 centavo da Orbe não é divergência de taxa.
Toda a cobrança da Orbe sobre a Casa do Estudante é divergência (`taxa_contratada_pct = Decimal("0.00")`).
Pula transações sem contrato (Atlas Idiomas).
Remessas:
Mundo Aberto Intercâmbio: Consome `dados_remessas["operacoes_divergentes"]` (23 operações onde a Ponte cobrou ~1.50% vs 1.20% contratado). `diferenca_brl` calculada sobre o volume da operação.
Spreads Negativos: Consome `dados_remessas["operacoes_spread_negativo"]` (4 operações com trava estourada). `diferenca_brl` reportada como o spread negativo em reais.
Contrato Exato da Saída (`List[config.Linha]` para `saida/divergencias_taxa.csv`):
`"id_saida"`: `str` gerado via `tracker.novo_id(config.PREFIXO_DIVERGENCIA)` (ex: `'DIV-0001'`).
`"cnpj"`: `str` (14 dígitos numéricos).
`"linha_negocio"`: `str` (`'CHECKOUT'` ou `'REMESSA'`).
`"ref_origem"`: `str` (`id_transacao` para Checkout, `num_operacao` para Remessas).
`"taxa_contratada_pct"`: `Decimal` (taxa contratada com no mínimo 2 casas).
`"taxa_aplicada_pct"`: `Decimal` (taxa aplicada pela adquirente/parceira com no mínimo 2 casas).
`"diferenca_brl"`: `Decimal` (impacto financeiro em reais, arredondado em 2 casas).
`src/engine/notas.py` (Missão 3)
Papel: Gerar a lista formal de Notas Fiscais de Serviços (NFS-e) a emitir pela Tarvo.
Ponto de Entrada: `notas.gerar_notas_a_emitir(comissoes: List[config.Linha], dados_checkout: Dict[str, Any], dados_remessas: Dict[str, Any], tracker: RastroTracker) -> List[config.Linha]` (invocado pelo `main.py`).
Entradas:
`comissoes`: lista de linhas geradas por `comissoes.calcular_comissoes`.
`dados_checkout`: retorno de `parse_orbe_e_taxas`.
`dados_remessas`: retorno de `parse_ponte.parse_ponte_e_taxas`.
`tracker`: instância ativa de `RastroTracker`.
Regras de Negócio:
Checkout: Emitir uma nota fiscal para cada lojista ativo cujo saldo de comissão líquida seja estritamente positivo (`> R$ 0.00`). Lojistas com saldo zero (Casa do Estudante) ou negativo não emitem nota.
Atlas Idiomas: Bloqueada de faturamento por falta de contrato assinado em 2026.
Remessas: Emitir exatamente UMA ÚNICA NOTA FISCAL contra a Ponte Câmbio S.A. (CNPJ `config.PONTE_CAMBIO_CNPJ` = `'75374179000146'`) pelo valor total consolidado das comissões válidas de remessa (`R$ 39.543,45`).
Discriminação textual formal do serviço prestado (ex.: `"Serviços de intermediação e agenciamento - Checkout competência 09/2026"` e `"Serviços de intermediação e agenciamento de remessas internacionais competência 09/2026"`).
Cada nota deve ter seu rastro registrado amarrando as transações/operações que compõem o faturamento, para que `tracker.validar_todos()` passe na auditoria.
Contrato Exato da Saída (`List[config.Linha]` para `saida/notas_a_emitir.csv`):
`"id_saida"`: `str` gerado via `tracker.novo_id(config.PREFIXO_NOTA)` (ex: `'NF-0001'`).
`"tomador_cnpj"`: `str` (14 dígitos numéricos do tomador da nota).
`"tomador"`: `str` (razão social do tomador do serviço).
`"linha_negocio"`: `str` (`'CHECKOUT'` ou `'REMESSA'`).
`"valor_brl"`: `Decimal` (valor total da nota, estritamente `> 0.00`).
`"discriminacao"`: `str` (descrição detalhada do serviço prestado).
`src/engine/pendencias.py` (Missão 5)
Papel: Catalogar de forma estruturada todas as anomalias, disputas e exceções que exigem intervenção e deliberação humana.
Ponto de Entrada: `pendencias.consolidar_pendencias(dados_checkout: Dict[str, Any], dados_remessas: Dict[str, Any], dados_extratos: Dict[str, Any], tracker: RastroTracker) -> List[config.Linha]` (invocado pelo `main.py`).
Entradas:
`dados_checkout`: retorno de `parse_orbe_e_taxas`.
`dados_remessas`: retorno de `parse_ponte.parse_ponte_e_taxas`.
`dados_extratos`: retorno de `parse_extratos.parse_extratos_e_plano`.
`tracker`: instância ativa de `RastroTracker`.
Catálogo Oficial das 7 Pendências:
Spreads Negativos (Ponte): 4 operações com trava expirada da Ponte Câmbio (`PC-0926-0210`, `-0326`, `-0491`, `-0545`) ➔ `tipo = config.PEND_SPREAD_NEGATIVO`, `quem_decide = config.QUEM_FINANCEIRO`.
Operação Repetida (Ponte): Retificação da duplicata `PC-0926-0162` ➔ `tipo = config.PEND_OPERACAO_DUPLICADA`, `quem_decide = config.QUEM_FINANCEIRO`.
Spread Indevido Mundo Aberto (Ponte): Cobrança de 1.50% vs 1.20% contratado ➔ `tipo = config.PEND_DIVERGENCIA_SPREAD`, `quem_decide = config.QUEM_FINANCEIRO`.
Ressarcimento Casa do Estudante (Orbe): Devolução de taxas de checkout retidas indevidamente pela Orbe ➔ `tipo = config.PEND_DEVOLUCAO_TAXA`, `quem_decide = config.QUEM_FINANCEIRO`.
Contrato Atlas Idiomas (Orbe): Regularização comercial do contrato pendente de 2026 (EC `1076801732`) ➔ `tipo = config.PEND_CONTRATO_AUSENTE`, `quem_decide = config.QUEM_COMERCIAL`.
Pix Não Identificado (Aurora L50): Lançamento de R$ 7.350,00 sem remetente ➔ `tipo = config.PEND_PIX_NAO_IDENTIFICADO`, `quem_decide = config.QUEM_FINANCEIRO`.
Devolução de Pix Mundo Aberto (Aurora L65): Investigação de devolução de R$ 12.400,00 ➔ `tipo = config.PEND_DEVOLUCAO_PIX`, `quem_decide = config.QUEM_FINANCEIRO`.
Contrato Exato da Saída (`List[config.Linha]` para `saida/pendencias.csv`):
`"id_saida"`: `str` gerado via `tracker.novo_id(config.PREFIXO_PENDENCIA)` (ex: `'PEN-0001'`).
`"tipo"`: `str` (tipo formal da pendência em `config.py`).
`"ref_origem"`: `str` (identificador unívoco de origem: número de operação, ID de transação, EC ou linha de extrato).
`"valor_brl"`: `Decimal` (montante financeiro envolvido, com 2 casas).
`"motivo"`: `str` (descrição clara do motivo da retenção/disputa e impacto).
`"quem_decide"`: `str` (`'Financeiro Tarvo (Helena)'` ou `'Comercial Tarvo (Diego)'`).
`src/engine/rastro.py` (Regra Central do Case)
Papel: Garantir o requisito eliminatório da banca: todo número de saída aponta para as linhas de origem que o compõem, e a soma no rastro fecha centavo a centavo.
Ponto de Entrada: Classe `RastroTracker` instanciada em `main.py` e injetada em todos os módulos da Engine.
Métodos Públicos Obrigatórios:
`tracker.novo_id(prefixo: str) -> str`: Devolve o próximo identificador sequencial único (`COM-0001`, `NF-0001`, `DIV-0001`, `LAN-0001`, `PEN-0001`).
`tracker.registrar(id_saida: str, arquivo_origem: str, ref_origem: str, valor: Union[Decimal, int, float, str]) -> None`: Registra a contribuição individual de uma transação/operação para aquele `id_saida`. Valida se `valor` tem precisão de centavos (`<= 2 casas`).
`tracker.validar_todos(totais_reportados: Dict[str, Decimal]) -> None`: Valida se o somatório dos registros de cada `id_saida` fecha exatamente centavo a centavo com o total reportado. Levanta `AssertionError` se houver discrepância.
`tracker.linhas() -> List[Dict[str, Any]]`: Devolve a lista de todas as linhas registradas prontas para gravação no CSV final.
Contrato Exato da Saída (`saida/rastro.csv`):
`"id_saida"`: `str` (chave de saída correspondente).
`"arquivo_origem"`: `str` (nome do arquivo bruto de onde veio o dado).
`"ref_origem"`: `str` (referência atômica da linha de origem).
`"valor"`: `Decimal` (valor em reais daquela linha com 2 casas).
---
🤖 6. Camada de Inteligência Artificial: `src/ai/classifier.py` (Missão 4)
Papel: Classificar 100% dos lançamentos bancários dos bancos Aurora e Meridiano no Plano de Contas Analítico do ERP Fênix.
Ponto de Entrada: `classifier.classificar_lancamentos(dados_extratos: Dict[str, Any], tracker: RastroTracker) -> List[config.Linha]` (invocado pelo `main.py`).
Entradas:
`dados_extratos`: dicionário retornado por `parse_extratos.parse_extratos_e_plano`.
`tracker`: instância ativa de `RastroTracker`.
Estratégia Híbrida Recomendada (Robustez + IA Explicável):
Regras Determinísticas (`metodo = 'REGRA'`, `confianca = Decimal('1.00')`):
Pagamento de folha de salários e encargos de agosto baixam passivos já provisionados (`2.1.04.001`, grupo `2.1.03.xxx`), não são despesa de setembro.
Recebimento de comissão de câmbio em 04/09 (Meridiano `MRD2026090132`) baixa o ativo `config.CONTA_COMISSOES_A_RECEBER` (`'1.1.03.002'`).
Transferências entre contas próprias (Aurora ↔ Meridiano) vão para a conta transitória de mútuo `config.CONTA_TRANSITORIA_MUTUO` (`'1.1.09.001'`).
Despesas correntes administrativas padronizadas vão diretamente para as contas de despesa do grupo `4.2.xxx`.
Classificação por IA (`metodo = 'IA'`):
Utilizar a LLM com prompt estruturado contendo o plano de contas analítico para desambiguar lançamentos com descrições atípicas ou não previstas em regras simples.
Retornar o código analítico exato da conta e o score de confiança (ex: `0.85`).
Exceções Humanas (`metodo = 'HUMANO'` ou conta transitória):
Lançamentos não identificáveis (ex: Pix recebido de R$ 7.350,00 no Aurora L50) são direcionados para a conta transitória `config.CONTA_TRANSITORIA_NAO_IDENTIFICADO` (`'1.1.09.002'`) e integrados ao `pendencias.csv`.
Contrato Exato da Saída (`List[config.Linha]` para `saida/lancamentos_classificados.csv`):
`"id_saida"`: `str` gerado via `tracker.novo_id(config.PREFIXO_LANCAMENTO)` (ex: `'LAN-0001'`).
`"banco"`: `str` (`'AURORA'` ou `'MERIDIANO'`).
`"ref_origem"`: `str` (`'L8'`, `'L9'`... para Aurora; `<FITID>` para Meridiano).
`"data"`: `str` ISO (`AAAA-MM-DD`).
`"descricao"`: `str` (histórico original do extrato bancário).
`"valor"`: `Decimal` (débito negativo, crédito positivo com 2 casas).
`"conta_codigo"`: `str` (código analítico no plano de contas Fênix, ex: `'1.1.03.002'`).
`"metodo"`: `str` (`'REGRA'`, `'IA'` ou `'HUMANO'`).
`"confianca"`: `Decimal` (entre `0.00` e `1.00`).
---
🧪 7. Auditoria Cega e Validação: `tests/validate_saida.py`
Papel: Replica de forma independente a rotina automática que a banca avaliadora da Barte usará para corrigir a entrega.
Características:
Desenvolvido exclusivamente com a biblioteca padrão do Python (`csv`, `re`, `decimal`).
Não importa módulos de `src/` para evitar reproduzir eventuais bugs de implementação.
Valida:
Existência e nomes exatos dos 6 arquivos CSV em `saida/`.
Cabeçalhos e ordem das colunas obrigatórias.
Formatos estritos: separador `;`, ausência de valores `NaN`/`null`/`None`, formato de dinheiro (`-?123.45`), formato de percentual, CNPJ com 14 dígitos e datas em formato ISO `AAAA-MM-DD`.
Domínios restritos (`linha_negocio`: `CHECKOUT`/`REMESSA`; `banco`: `AURORA`/`MERIDIANO`; `metodo`: `REGRA`/`IA`/`HUMANO`).
Integridade matemática total: valida se a soma das linhas de `rastro.csv` fecha com os totais de `comissoes_por_lojista.csv` e `notas_a_emitir.csv`.
---
📊 8. Matriz De-Para (Missões do Edital vs. Componentes)
Missão do Case	Módulo Implementador	Arquivo de Saída Gerado	Nível de Entrega
1. Comissões por Lojista	`src/engine/comissoes.py`	`saida/comissoes_por_lojista.csv`	Mínimo (Checkout) / Alvo (Remessa)
2. Divergências de Taxa	`src/engine/divergencias.py`	`saida/divergencias_taxa.csv`	Alvo
3. Notas Fiscais a Emitir	`src/engine/notas.py`	`saida/notas_a_emitir.csv`	Alvo
4. Lançamentos Classificados	`src/ai/classifier.py`	`saida/lancamentos_classificados.csv`	Alvo
5. Mapeamento de Pendências	`src/engine/pendencias.py`	`saida/pendencias.csv`	Extra
Regra Central: Rastreabilidade	`src/engine/rastro.py`	`saida/rastro.csv`	Obrigatória em todos os níveis
---
🏁 9. Roteiro de Implementação Sugerido
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