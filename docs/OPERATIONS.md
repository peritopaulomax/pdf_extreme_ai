# Operacao (local / sub-rede)

## 1) Infraestrutura

```bash
docker compose up -d qdrant
python scripts/test_qdrant_connection.py
curl -s http://127.0.0.1:11434/api/tags
```

## 2) Modelos Ollama

Catalogo fixo no codigo: `gemma4:26b`, `gemma4:e4b`.

```bash
ollama pull gemma4:26b
ollama pull gemma4:e4b
```

```bash
export OLLAMA_MODELS=gemma4:26b,gemma4:e4b
export OLLAMA_MODEL_DEFAULT=gemma4:26b
export OLLAMA_KEEP_ALIVE=-1
export OLLAMA_UNLOAD_ON_SWITCH=false
export INGEST_PAUSE_OLLAMA=true
export QUERY_EMBED_DEVICE=cpu
export OLLAMA_THINKING=true
export CHAT_MEMORY_TOKEN_LIMIT=16000
export RERANKER_DEVICE=cpu
```

- `OLLAMA_KEEP_ALIVE=-1` ou `24h`: mantem o LLM carregado entre consultas (menos picos de VRAM).
- `OLLAMA_THINKING=true`: pede raciocinio interno ao Ollama (modelos compativeis, ex. `gemma4:26b`); aparece no expander **Thinking do modelo** na UI. Use `false` se quiser respostas mais rapidas.
- `CHAT_MEMORY_TOKEN_LIMIT=16000`: teto de tokens do historico da **conversa ativa** no `CondensePlusContext` (condensacao + contexto). Valores maiores aumentam VRAM/latencia no Ollama.
- `RERANKER_DEVICE=cpu`: reranker na CPU libera VRAM na GPU para modelos grandes + thinking (`cuda`, `gpu` ou `auto` para GPU quando disponivel).
- `TORCH_NUM_THREADS`: numero de threads CPU usado pelo PyTorch no reranker (e OMP/MKL padrao quando nao definido); suba conforme nucleos fisicos.
- `OLLAMA_UNLOAD_ON_SWITCH=false`: nao executa `ollama stop` ao trocar de modelo (melhor para varios usuarios no mesmo Ollama).
- `OLLAMA_UNLOAD_ON_SWITCH=true`: libera VRAM agressivamente na troca (estacao isolada).
- `INGEST_PAUSE_OLLAMA=true`: antes da ingestao, descarrega o modelo Ollama ativo para liberar VRAM ao embedding em CUDA; prewarm apos o lote.
- `QUERY_EMBED_DEVICE=cpu`: embedding de consulta em CPU; ingestao continua em CUDA via `embedding_device()`.

### Uso simultaneo (varias abas / usuarios)

- O backend FastAPI (`uvicorn main:app`) e o frontend React (`npm run dev` / build estático) compartilham GPU e cache de modelos via processo do backend.
- Apenas **uma ingestao por vez** na GPU; outras abas veem o chat bloqueado ate terminar.
- Salvar regras do projeto **nao** recarrega modelos na GPU.
- Ruído `torchvision` no terminal (file watcher): opcional `streamlit run app.py --server.fileWatcherType poll`.

## 3) Ingestao

```bash
python scripts/ingest.py --data-dir ./data --project-id <project_id>
```

Rebuild do projeto: adicione `--rebuild --reprocess-all` quando necessario.

## 4) App Streamlit

```bash
streamlit run app.py
# opcional: menos ruido no terminal do watcher
streamlit run app.py --server.fileWatcherType poll
```

### 4.1) Projetos e fontes (painel esquerdo)

Criar/selecionar projeto, upload de PDFs, logs de ingestao, explorer de documentos, regras globais, **memoria do caso** (`data/projects/<project_id>/project_memory.md`), exclusao de projeto.

### 4.2) Tres modos de uso (painel direito)

Seletor **Modo de uso**, independente de haver PDFs no projeto:

| Modo | Funcao |
|------|--------|
| **Autos (RAG)** | Perguntas sobre PDFs indexados; prompts juridicos; trechos recuperados; perfil rapido/preciso/pericial |
| **Chat livre** | LLM direto, **sem** busca nos autos (mesmo com ingest feita) |
| **Corretor** | Colar texto; correcao ortografica/gramatical (JSON + destaques); sem RAG |

- **Autos (RAG)** exige base indexada (Qdrant + FTS). Sem ingest, o app avisa e nao abre o chat RAG.
- **Chat livre:** checkbox opcional para incluir memoria do caso (desligado por padrao).
- **Modo auditoria** (checkbox): so dentro de Autos (RAG), para buscas literais — **nao** para “resumo do caso”.
- `EMBEDDING_DIM=1024` (opcional): dimensao da colecao Qdrant em projeto novo.

### 4.3) Conversas (painel direito)

- Arquivos: `data/projects/<project_id>/conversations/<conversation_id>.json`
- **Historico salvo** + **Abrir** carrega mensagens na UI e **reidrata** a memoria do engine (o modelo volta a ver o fio da conversa ate o limite `CHAT_MEMORY_TOKEN_LIMIT`).
- Se a pagina Streamlit for recarregada com mensagens ja na sessao, a memoria e sincronizada automaticamente quando vazia.
- **Thinking do modelo**: expander recolhido apos cada resposta (quando `OLLAMA_THINKING=true` e o modelo suporta `think`).
- **Nova conversa** cria registro vazio.
- **Renomear conversa ativa** + **Salvar titulo**.
- **Nova pergunta:** `st.chat_input` (Enter envia, Shift+Enter nova linha); o texto e guardado em sessao e o processamento corre no proximo rerun; ao terminar a resposta o app faz **mais um rerun** para repintar historico + campo de pergunta.
- **Exportar .md** / **Copiar Markdown** (um clique no botao HTML ao lado do download; se o navegador bloquear, use Exportar .md).

### 4.3.1) Memoria do caso vs RAG

- **Memoria do caso** (painel esquerdo): contexto narrativo editavel (partes, teses, decisoes). Entra nos prompts de todas as conversas do projeto.
- **RAG (documentos)**: trechos recuperados por pergunta. Em conflito factual, **prevalecem os documentos** sobre a memoria do caso ou o chat.
- Orçamento orientativo por turno: historico da conversa ~32k tokens; RAG ~40–60k tokens via perfis (ajuste abaixo); nao encher o contexto ate 256k de uma vez (latencia e qualidade).

### 4.3.3) Trechos recuperados e validacao (Fase 1)

- Apos cada resposta RAG, expander **Trechos usados nesta resposta** (rank, arquivo, pagina, score, snippet).
- Perfil **preciso** usa validacao `light`: se a busca lexical encontrou ocorrencias e a resposta nega menção, o app refaz a pergunta automaticamente (retry).
- Telemetria com `fused < 5`: legenda sugere perfil **pericial** ou subir `PROFILE_PRECISO_*` (ver §4.3.2).

### 4.3.4) Alertas de ingestao

| Situacao | Limiar / status | Acao sugerida |
|----------|-----------------|---------------|
| PDF sem texto | `status=empty` ou `pages=0` | Aviso na UI; possivel scan |
| Chunks vazios | `status=empty_chunks` | Idem |
| Texto ruidoso | `quality < INGEST_QUALITY_WARN_THRESHOLD` (padrao **0.35**) | Aviso; considerar OCR |

Variavel: `INGEST_QUALITY_WARN_THRESHOLD=0.35`

### 4.3.5) Modo auditoria e indice por pagina (Fase 2)

- Checkbox **Modo auditoria** no painel direito ou termos como *varredura*, *exaustivo*, *todas as ocorrencias*.
- Varredura FTS paginada (`EXHAUSTIVE_BATCH_SIZE`, `EXHAUSTIVE_MAX_HITS`); sintese map-reduce quando paginas >= `AUDIT_MAP_REDUCE_THRESHOLD` (padrao 25).
- Indice `page_fts` agregado na ingestao (mesmo `LEXICAL_DB_PATH`); consultas com pagina/fls. priorizam retrieve por pagina.

### 4.3.6) OCR e avaliacao offline (Fase 3)

```bash
# OCR opcional (Tesseract + pymupdf + pytesseract + Pillow)
export ENABLE_OCR=false
export OCR_QUALITY_THRESHOLD=0.35
```

- UI: **Forcar OCR no proximo reprocessamento** na lista de documentos.
- Entidades: painel **Timeline / entidades** apos reingestao.
- Eval: `python scripts/eval_rag.py --gold eval/gold_questions.json`

### 4.3.2) Ajuste fino do RAG (sem mudar codigo)

Se a telemetria mostrar `fused` baixo ou respostas “nao encontrei” com PDFs relevantes no projeto:

1. Confirme o perfil na legenda (`rapido` / `preciso` / `pericial`) ou use modo **automatico**.
2. Suba gradualmente no `.env`, por exemplo no perfil **preciso**:
   - `PROFILE_PRECISO_SEMANTIC_TOP_K` (ex. 14 → 18)
   - `PROFILE_PRECISO_RERANKER_TOP_N` (ex. 10 → 12)
3. Para auditoria exaustiva, use perfil **pericial** ou fixo `pericial` no expander avancado.
4. Apos mudar `CHUNK_SIZE` / `INGEST_STRATEGY`, reindexe com `--reprocess-all`.

### 4.4) Troca de modelo

Fluxo: preload do novo modelo; `ollama stop` apenas se `OLLAMA_UNLOAD_ON_SWITCH=true`.

## 5) Checklist pos-atualizacao

1. `ollama pull gemma4:26b` e `ollama pull gemma4:e4b`
2. Ajustar `.env` (`OLLAMA_MODELS`, `OLLAMA_UNLOAD_ON_SWITCH`, etc.)
3. `docker compose up -d qdrant` se necessario
4. `python -m unittest discover -s tests -p 'test_*.py'`
5. `streamlit run app.py`
6. Criar projeto, ingerir um PDF, criar duas conversas, recarregar a pagina e abrir uma conversa salva; testar export/copiar.
7. **Fase 1:** pergunta com termo literal → expander de trechos + telemetria `literal_hits`; ingest de PDF scan → aviso de qualidade.
8. **Fase 2:** pergunta “onde aparece X” / “fls. N” → paginas coerentes; modo auditoria com muitas paginas → resposta em lotes.
9. **Fase 3 (opcional):** `ENABLE_OCR=true`, reprocessar documento; `python scripts/eval_rag.py`.
