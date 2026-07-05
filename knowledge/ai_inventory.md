# PDF Extreme AI — AI Inventory

## Modelos

| Modelo | Provedor | Tipo | Uso | Criticidade |
|---|---|---|---|---|
| `BAAI/bge-m3` | HuggingFace local | Embedding (1024 dim) | Indexação e busca semântica | Crítica |
| `BAAI/bge-reranker-base` | HuggingFace local | Cross-encoder reranker | Refinar ranking de trechos | Alta |
| `gemma4:26b` | Ollama | LLM gerativo | Geração de respostas padrão | Crítica |
| `gemma4:e4b` | Ollama | LLM gerativo | Geração de respostas alternativa | Crítica |

## Datasets

| Dataset | Origem | Uso |
|---|---|---|
| `eval/gold_questions.json` | Manual | Avaliação offline de recall@k (apenas 2 perguntas) |
| Documentos do usuário | Upload | Corpus de cada projeto |

## Treinamento

- Não há treinamento de modelos próprios.
- Modelos de embedding/reranker são pré-treinados do HuggingFace.
- LLMs são modelos de Ollama já quantizados.

## Inferência

### Pipeline de Embedding
- Modelo: `BAAI/bge-m3`
- Caminho: `EMBEDDING_MODEL_PATH` (default `/home/labfaces/.cache/huggingface/...`)
- Dispositivo ingest: CUDA/CPU conforme disponibilidade
- Dispositivo query: `QUERY_EMBED_DEVICE=cpu` por padrão

### Pipeline de Reranker
- Modelo: `BAAI/bge-reranker-base`
- Caminho: `RERANKER_MODEL_PATH`
- Dispositivo: `RERANKER_DEVICE=cpu` por padrão

### Pipeline de LLM
- Provedor: Ollama HTTP API
- Modelos permitidos: `gemma4:26b`, `gemma4:e4b`
- Configuração: `OLLAMA_HOST`, `OLLAMA_TIMEOUT_DEFAULT`, `OLLAMA_TIMEOUT_HEAVY`, `OLLAMA_KEEP_ALIVE`, `OLLAMA_THINKING`

## Métricas

| Métrica | Onde | Descrição |
|---|---|---|
| `fused` | Telemetria de retrieval | Score de fusão RRF |
| `literal_hits` | Telemetria | Hits no índice lexical |
| `semantic_hits` | Telemetria | Hits no índice semântico |
| `reranker_top_n` | Config | Quantos trechos após rerank |
| `recall@k` | `scripts/eval_rag.py` | Avaliação offline |

## Riscos de IA

| Risco | Impacto | Probabilidade | Mitigação |
|---|---|---|---|
| Modelos hardcoded | Dificuldade de trocar modelo | Alta | Alterar `runtime_config.py` e frontend |
| Dependência de Ollama | Sem LLM, sistema inútil | Alta | Nenhuma (externo) |
| Embedding lento/VRAM | Ingestão lenta ou OOM | Média | `QUERY_EMBED_DEVICE=cpu`, pausa Ollama |
| Reranker CPU lento | Latência alta no chat | Média | Fallback sem reranker |
| Resposta alucinada | Informação incorreta ao usuário | Média | Validação de citações e retry |
| Thinking mal capturado | UX ruim ou resposta vazia | Média | Patches em `llama_index_stream_queue_patch.py` |

## Gate

**IA compreendida?** Sim. O sistema usa embeddings BGE-M3, reranker BGE e LLMs Gemma4 via Ollama para RAG jurídico, com inferência local e configuração centralizada em `.env`.

## Evidências

- `core/runtime_config.py`
- `core/ollama_thinking_stream.py`
- `core/llm_thinking.py`
- `backend/services/stack_manager.py`
- `.env.example`
- `scripts/eval_rag.py`
- `eval/gold_questions.json`
