# PDF Extreme AI — Domain Model

## Resumo

Domínio de **assistente RAG para documentos jurídicos/periciais**. O sistema organiza o trabalho em projetos isolados; cada projeto contém documentos PDF, conversas, memória do caso e entidades extraídas. Usuários autenticados (admin ou consultor) interagem via chat RAG, chat livre ou corretor ortográfico.

## Atores

| Ator | Papel |
|---|---|
| Admin | Gerencia usuários (admins/consultores), reset de senhas, acesso total |
| Consultor | Cria projetos, faz upload de PDFs, conversa com documentos |
| Sistema (motor RAG) | Indexa PDFs, recupera trechos, gera respostas, valida |
| Ollama | Serviço externo de LLM |
| Qdrant | Serviço externo de banco vetorial |

## Entidades

| Entidade | Responsabilidade |
|---|---|
| Usuário | Credenciais, perfil (admin/consultor), projetos de propriedade |
| Projeto | Container isolado de documentos, conversas, memória e índices |
| Documento | PDF enviado, com metadados (file_id, sha256, pages, chunks, status, quality) |
| Chunk | Trecho de texto extraído de um documento, com referência de página |
| Conversa | Sequência de mensagens entre usuário e assistente em um projeto |
| Mensagem / Turno | Unidade de interação; inclui status, thinking, telemetry, retrieved_chunks |
| Memória do Caso | Texto narrativo editável sobre o projeto |
| Regras Globais | Instruções do projeto injetadas nos prompts |
| Entidade (NER) | CPF, CNPJ, nomes extraídos dos documentos |
| Grafo Cross-Doc | Referências cruzadas entre documentos (doc_type:doc_number) |

## Estados

### Projeto
| Estado | Significado |
|---|---|
| Ativo | Projeto existe e pode ser usado |
| Sem documentos | Projeto criado, mas sem PDFs indexados |
| Com documentos indexados | Pronto para chat RAG |
| Excluído | Removido do registry e assets limpos |

### Documento
| Estado | Significado |
|---|---|
| indexed | Indexado com sucesso |
| empty | PDF sem texto extraído |
| empty_chunks | Texto extraído, mas sem chunks válidos |
| error | Falha na ingestão |

### Turno / Mensagem
| Estado | Significado |
|---|---|
| running | Em andamento |
| completed | Finalizado com sucesso |
| failed | Falhou |
| cancelled | Cancelado pelo usuário |

## Eventos

| Evento | Consequência |
|---|---|
| Usuário cria projeto | Registry atualizado; diretórios de dados criados |
| Usuário faz upload de PDF | Arquivos persistidos; ingest pode iniciar automaticamente |
| Ingest concluída | Documentos indexados em Qdrant + FTS5; entidades extraídas |
| Usuário envia pergunta | Planejamento, retrieval, geração, validação, persistência |
| Resposta gerada | Mensagem salva; telemetry disponível |
| Usuário cancela turno | Status atualizado para cancelled |
| Usuário exclui projeto | Assets Qdrant, SQLite, uploads e registry removidos |

## Regras de Negócio

| Regra | Criticidade |
|---|---|
| Cada projeto pertence a um único `owner_id` | Alta |
| Usuário só visualiza projetos onde é owner | Alta |
| Admin não pode ser cadastrado como consultor | Média |
| Não é possível remover o último admin | Alta |
| Respostas RAG devem conter citações `[arquivo, pag]` | Média |
| Retry automático quando resposta nega menções encontradas | Média |
| Modo auditoria só deve ser usado para perguntas literais/exaustivas | Média |
| Chat livre não usa documentos | Alta |
| Corretor não indexa texto colado | Alta |

## Contratos

- `ProjectRecord`: `project_id`, `name`, `created_at`, `updated_at`, `qdrant_collection`, `lexical_db_path`, `checkpoint_path`, `global_rules`, `documents[]`, `owner_id`
- `ConversationRecord`: `conversation_id`, `title`, `created_at`, `updated_at`, `messages[]`, `model_name`, `active_turn_id`
- `ChatRequest`: `message`, `conversation_id`, `model`, `profile`, `audit_mode`, `deep_mode`, `use_project_memory`, `session_rules`
- `IngestResult`: estatísticas por arquivo (`per_file` com `status`, `quality`, `pages`, `chunks`)
- `QueryPlan`: perfil (`rapido`, `preciso`, `pericial`), intent, página/faixa, arquivo, seção

## Restrições

- Máximo de arquivos por upload: `UI_INGEST_MAX_FILES` (default 12)
- Tamanho máximo por arquivo: `UI_INGEST_MAX_FILE_MB` (default 512 MB)
- Modelos permitidos: `gemma4:26b`, `gemma4:e4b`
- Perfis RAG: `rapido`, `preciso`, `pericial`
- Chat assíncrono controlado por `CHAT_ASYNC_TURNS`

## Invariantes

- `project_id` é único no registry
- Cada projeto tem sua própria coleção Qdrant e banco lexical
- Conversas pertencem a um único projeto
- Mensagens de um turno compartilham o mesmo `turn_id`

## Erros de Domínio

| Erro | Causa |
|---|---|
| Projeto não encontrado | `project_id` inexistente ou não pertence ao usuário |
| Documento vazio | PDF sem texto ou OCR desabilitado |
| Falha de ingestão | Erro no embedding, Qdrant ou extração |
| Resposta vazia | LLM retornou conteúdo vazio |
| Validação falhou | Citações ausentes ou negação de menções presentes |
| Cancelamento cooperativo | Turno não verificou evento de cancelamento |

## Evidências

- `core/project_store.py`
- `core/conversation_store.py`
- `backend/api/schemas.py`
- `backend/services/project_access.py`
- `backend/services/documents_service.py`
- `core/retrieval_pipeline.py`
- `core/query_planner.py`
- `core/answer_validator.py`
- `docs/AUTH_SPEC.md`
- `docs/CHAT_TURN_PERSISTENCE_SPEC.md`
