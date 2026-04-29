# Operacao minima (local/sub-rede)

## 1) Subir infraestrutura

```bash
docker compose up -d qdrant
```

## 2) Validar servicos

```bash
python scripts/test_qdrant_connection.py
curl -s http://127.0.0.1:11434/api/tags
```

## 2.1) Modelos recomendados (RTX 3080 10GB)

- Rapido (interativo): `gemma4:e4b`
- Equilibrio (QA geral): `qwen2.5:7b-instruct`
- Profundo (lento): `gemma4-pericia:latest`
- Profundo alternativo: `deepseek-r1:14b`

Download:

```bash
ollama pull gemma4:e4b
ollama pull qwen2.5:7b-instruct
ollama pull gemma4-pericia:latest
ollama pull deepseek-r1:14b
```

Configurar catalogo no ambiente:

```bash
export OLLAMA_MODELS=gemma4:e4b,qwen2.5:7b-instruct,gemma4-pericia:latest,deepseek-r1:14b
export OLLAMA_MODEL_DEFAULT=gemma4:e4b
```

## 3) Ingestao

Incremental (padrao):

```bash
python scripts/ingest.py --data-dir ./data
```

Rebuild completo (destrutivo):

```bash
python scripts/ingest.py --data-dir ./data --rebuild
```

## 3.1) Ingestao hibrida (Qdrant + FTS5 lexical)

- O `ingest.py` agobashra envia nodes para o Qdrant (semantico) e para o banco local
`LEXICAL_DB_PATH` (SQLite FTS5).
- Em `--rebuild`, a colecao vetorial e o indice lexical sao recriados.
- Se mudar `CHUNK_SIZE`, `CHUNK_OVERLAP` ou `SENTENCE_WINDOW_SIZE`, rode:

```bash
python scripts/ingest.py --data-dir ./data --rebuild --reprocess-all
```

## 3.2) Perfis de recuperacao (chat unico automatico)

- `rapido`: triagem com baixa latencia.
- `preciso` (padrao): equilibrio entre cobertura e velocidade.
- `pericial`: cobertura alta para perguntas exaustivas ("todas as mencoes", "onde aparece").

No modo `PLANNER_MODE=auto`, o sistema escolhe o perfil pela pergunta.
No app ha override manual (expander "Opcao avancada de estrategia").

## 4) App

```bash
streamlit run app.py
```

## 4.0) Fluxo por projeto (obrigatorio)

1. Criar projeto na sidebar ("Projetos" -> "Novo projeto" -> "Criar projeto").
2. Confirmar projeto ativo (nome/colecao/lexical DB exibidos na sidebar).
3. Fazer upload + ingestao na seção "Base de conhecimento".
4. Salvar instrucoes globais no bloco "Instrucoes globais do projeto" (opcional).
5. Consultar no chat. O contexto e estanque ao projeto ativo.

Isolamento:

- cada projeto usa propria colecao no Qdrant;
- cada projeto usa proprio arquivo lexical SQLite;
- rebuild afeta somente o projeto ativo.

No app:

- selecione o modelo no dropdown;
- opcionalmente fixe um perfil (`rapido`, `preciso`, `pericial`);
- verifique a telemetria por resposta (estrategia, contagem lexical/semantica, fused).

## 4.1) Ingestao direto pela UI (sidebar)

Na sidebar "Base de conhecimento":

- arraste 1..N arquivos PDF;
- `Auto-ingest ao subir arquivo(s)` fica ligado por padrao;
- marque `Rebuild da base` apenas quando quiser recriar indices (destrutivo);
- com auto-ingest ON, o processamento inicia automaticamente apos upload;
- com auto-ingest OFF, use `Ingerir arquivos enviados`.

Durante a ingestao:

- barra de progresso exibe avancos por arquivo;
- expander "Logs de ingestao" mostra etapas (`extracting`, `chunking`, `indexing_vector`, `indexing_lexical`);
- ao concluir, o app invalida caches automaticamente para refletir a base nova.

Observacoes:

- limites padrao de upload: `UI_INGEST_MAX_FILES` e `UI_INGEST_MAX_FILE_MB`;
- arquivos sao persistidos em `projects_data/<project_id>/uploads/`;
- documentos enviados ficam registrados no metadata do projeto (lista lateral/explorer).

Explorer de arquivos:

- selecione arquivos por checkbox/lista para reprocessar ou remover em lote;
- a acao `Remover` apaga indexacao vetorial, indexacao lexical e arquivo fisico.

## 4.2) Regras globais do projeto

Na sidebar "Instrucoes globais do projeto":

- escreva instrucoes extras para a resposta do projeto ativo;
- clique `Salvar regras do projeto` para persistir;
- `Limpar regras do projeto` remove as regras.

Comportamento:

- regras valem para o projeto ativo e persistem no `projects_registry.json`;
- regras padrao juridicas e de citacao continuam prioritarias.

## 5) Testes de aceite rapidos

- Qdrant responde em `127.0.0.1:6333`
- Ollama responde em `127.0.0.1:11434`
- Ingestao grava vetorial + lexical (`.lexical_index.db`)
- App responde 3 perguntas de controle com latencia estavel
- Pergunta exaustiva ("todas as mencoes a pericia") mostra `literal_hits` na telemetria
- Upload + ingest via sidebar conclui e permite consulta sem reiniciar manualmente
- Regras globais afetam respostas e permanecem ao retornar ao mesmo projeto
- Projeto A nao retorna dados/regras do Projeto B

## 5.1) Calibracao para RTX 3080 (10GB)

Parta do perfil `preciso`:

- `PROFILE_PRECISO_SEMANTIC_TOP_K=14`
- `PROFILE_PRECISO_LEXICAL_TOP_K=16`
- `PROFILE_PRECISO_RERANKER_CANDIDATE_K=28`
- `PROFILE_PRECISO_RERANKER_TOP_N=10`

Se perder mencoes literais:

- aumente `PROFILE_PERICIAL_LEXICAL_TOP_K` e `PROFILE_PERICIAL_RERANKER_CANDIDATE_K`.

Se ficar lento:

- reduza `*_RERANKER_CANDIDATE_K`, depois `*_SEMANTIC_TOP_K`.

## 5.2) CLI por projeto

Ingestao por projeto no terminal:

```bash
python scripts/ingest.py --project-id <project_id> --data-dir ./data
```

Com rebuild do projeto:

```bash
python scripts/ingest.py --project-id <project_id> --data-dir ./data --rebuild --reprocess-all
```

## 6) Backup

Backup do volume vetorial:

```bash
tar -czf qdrant_backup_$(date +%F).tgz qdrant_data
```

