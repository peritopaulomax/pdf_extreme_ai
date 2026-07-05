# PDF Extreme AI — Risks

## Matriz de Riscos

| ID | Categoria | Risco | Impacto | Probabilidade | Prioridade | Mitigação |
|---|---|---|---|---|---|---|
| R01 | Segurança | `SESSION_SECRET` default em produção | Sessões previsíveis | Alta | Alta | Configurar `SESSION_SECRET` obrigatório |
| R02 | Segurança | `/proofread` e `/proofread/stream` públicos | Uso não autorizado de LLM | Média | Alta | Adicionar autenticação |
| R03 | Segurança | `/export/markdown` público | Possível exposição de dados formatados | Baixa | Média | Adicionar autenticação |
| R04 | Segurança | Rate limit de login em memória | Não funciona com múltiplos workers; reinicia com processo | Média | Média | Rate limit persistente ou WAF |
| R05 | Segurança | Uso de `dangerouslySetInnerHTML` no corretor | XSS se conteúdo comprometido | Média | Média | Sanitizar HTML ou usar diff seguro |
| R06 | Disponibilidade | Processo FastAPI único | Indisponibilidade total em queda | Alta | Alta | Load balancing / múltiplas instâncias |
| R07 | Disponibilidade | Qdrant single container | Sem busca semântica se cair | Alta | Alta | Cluster Qdrant ou backup |
| R08 | Disponibilidade | Ollama único | Sem geração se indisponível | Alta | Alta | Monitoramento + failover manual |
| R09 | Disponibilidade | Jobs em threads daemon | Perda de job em queda | Média | Média | Fila persistente (RQ/Celery) |
| R10 | Escalabilidade | JSON registry carregado inteiro | Gargalo com muitos projetos | Média | Média | Migrar para banco relacional |
| R11 | Escalabilidade | Stack LRU limitado a 16 | Cache thrashing com muitos projetos ativos | Baixa | Baixa | Ajustar tamanho ou invalidar menos |
| R12 | Performance | Reranker CPU lento | Latência alta no chat | Média | Média | CUDA ou fallback |
| R13 | Performance | Embedding na query disputa GPU | OOM ou lentidão | Média | Média | `QUERY_EMBED_DEVICE=cpu` |
| R14 | Observabilidade | Logs não estruturados | Dificuldade de debugging | Média | Média | Logger estruturado (JSON) |
| R15 | Observabilidade | Sem tracing | Difícil rastrear falhas em RAG | Média | Baixa | Adicionar tracing |
| R16 | Dados | `projects_registry.json` sem lock | Corrupção em concorrência | Média | Alta | Lock de arquivo ou banco |
| R17 | Dados | Dados de produção em `data/` no repo | Risco de vazamento | Alta | Alta | Mover para fora do VCS |
| R18 | Dados | Conversas JSON sem lock | Corrupção em concorrência | Média | Média | Lock de arquivo ou banco |
| R19 | Dependências Externas | Ollama indisponível | Sistema sem respostas | Alta | Alta | Monitoramento |
| R20 | Dependências Externas | Qdrant indisponível | Sem recuperação semântica | Alta | Alta | Cluster/backup |
| R21 | Operação | Caminhos de modelos hardcoded | Quebra em novos ambientes | Alta | Alta | Configurar paths via env |
| R22 | Operação | `upgrade_nvidia_driver.sh` operações destrutivas | Quebra sistema se mal usado | Média | Baixa | Documentar riscos |
| R23 | Integridade | Respostas alucinadas | Informação errada ao usuário | Média | Média | Validação + retry |
| R24 | Integridade | Testes quebrados em chat | Regressões não detectadas | Alta | Alta | Corrigir suite |

## Top 10 Riscos

1. **R06** — Processo FastAPI único
2. **R07** — Qdrant single container
3. **R08** — Ollama único
4. **R17** — Dados de produção no repositório
5. **R01** — SESSION_SECRET default
6. **R24** — Testes quebrados em área crítica
7. **R16** — Registry JSON sem lock
8. **R02** — Proofread público
9. **R21** — Paths de modelos hardcoded
10. **R09** — Jobs em threads daemon

## SPOFs

| SPOF | Impacto |
|---|---|
| Processo FastAPI único | Indisponibilidade total |
| Qdrant single container | Sem busca semântica |
| Ollama único | Sem geração |
| JSON registry único | Corrupção afeta todos os projetos |
| `SESSION_SECRET` default | Sessões previsíveis |

## Riscos de Dados

- Corrupção de `projects_registry.json`
- Perda de checkpoints durante ingestão
- Vazamento de PDFs/conversas se `data/` for versionado/publicado
- Inconsistência de IDs de projeto (com/sem hífen)

## Riscos de Segurança

- Secret default
- Rotas públicas sensíveis
- Rate limit em memória
- XSS via `dangerouslySetInnerHTML`
- Senhas hash com Werkzeug (aceitável, mas sem MFA)

## Riscos Operacionais

- Dependência de modelos locais pesados
- Configuração de GPU complexa
- OCR opcional requer Tesseract instalado
- Deploy single-instance

## Risco Residual

Mesmo após mitigações, permanecem riscos inerentes a LLMs (alucinações) e a operação de infraestrutura local (Ollama/Qdrant).

## Evidências

- `backend/main.py`
- `backend/api/proofread.py`
- `backend/api/auth.py`
- `backend/services/chat_turn_runner.py`
- `backend/services/ingest_runner.py`
- `core/project_store.py`
- `core/runtime_config.py`
- `frontend/src/components/ProofreadPanel.tsx`
- `data/`
