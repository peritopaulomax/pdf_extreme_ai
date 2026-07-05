# Relatório de Auditoria Arquitetural — PDF Extreme AI

## Score Geral

**Classificação:** Ruim / Aceitável em transição

| Critério | Nota | Justificativa |
|---|---|---|
| Acoplamento | Ruim | Backend depende de `core/` via manipulação de `sys.path`; `chat_service.py` e `HybridRetriever` acoplados a muitos módulos |
| Coesão | Ruim | `chat_service.py` concentra múltiplos modos; `HybridRetriever._retrieve` mistura planejamento, expansão, fusão, diversificação |
| Segurança | Ruim | Secret default, rotas públicas sensíveis, XSS potencial, rate limit em memória |
| Escalabilidade | Ruim | Deploy single-instance, JSON registry carregado inteiro, Qdrant/Ollama únicos |
| Observabilidade | Ruim | Logs não estruturados, sem métricas/alertas/tracing centralizados |
| Testabilidade | Ruim | Testes quebrados, serviços grandes, dependência de mocks excessiva |
| Disponibilidade | Ruim | SPOFs: FastAPI, Qdrant, Ollama; jobs em threads daemon |

## Anti-padrões Detectados

### Big Ball of Mud
- `chat_service.py` ~1280 linhas com RAG, free, sync, async, retry, fallback, audit, analytical.
- `HybridRetriever._retrieve` ~200 linhas com múltiplas responsabilidades.

### God Service
- `chat_service.py` centraliza praticamente toda a orquestração do chat.

### Invisible Dependencies
- `core/bootstrap.py` manipula `sys.path` e `os.chdir` implicitamente.
- Módulos do core fazem imports locais após bootstrap.

## Padrões Adequados

### RAG
- Uso apropriado de retrieval híbrido para complementar LLM.

### Monolito Modular
- Estrutura `core/`/`backend/`/`frontend/` é adequada para equipe pequena, embora a disciplina esteja degradada.

## Análise por Critério

### Acoplamento
- **Problema:** Backend depende de `core/` via bootstrap; `chat_service.py` depende de stack manager, chat turn store, runner, runtime_config, prompts, validator, etc.
- **Impacto:** Mudanças no core quebram API; dificuldade de testes.
- **Recomendação:** Introduzir interfaces/contracts entre backend e core; refatorar `chat_service.py` em handlers por modo.

### Coesão
- **Problema:** Muitas responsabilidades em poucos arquivos.
- **Impacto:** Dificuldade de manutenção e alta taxa de bugs.
- **Recomendação:** Separar planejamento, recuperação, geração e validação em componentes menores.

### Segurança
- **Problema:** Ver detalhes em `security_audit_report.md`.
- **Impacto:** Alto.
- **Recomendação:** Ver remediações no relatório de segurança.

### Escalabilidade
- **Problema:** Single-instance, JSON carregado inteiro, sem cache distribuído, sem fila.
- **Impacto:** Gargalo com crescimento de usuários/projetos.
- **Recomendação:** Migrar registry/conversas para banco; adicionar fila para jobs; cluster Qdrant/Ollama.

### Observabilidade
- **Problema:** Logs dispersos, sem métricas, sem tracing.
- **Impacto:** Dificuldade de diagnosticar falhas.
- **Recomendação:** Logger estruturado, métricas de retrieval, tracing de turnos.

### Testabilidade
- **Problema:** Serviços grandes, mocks frágeis, testes quebrados.
- **Impacto:** Regressões não detectadas.
- **Recomendação:** Refatorar para injeção de dependências; testes de contrato; corrigir suites.

### Disponibilidade
- **Problema:** SPOFs e jobs em threads.
- **Impacto:** Indisponibilidade total em quedas.
- **Recomendação:** Fila persistente, múltiplas instâncias, health checks.

## SPOFs

- Processo FastAPI
- Qdrant single container
- Ollama single instance
- `projects_registry.json`
- `SESSION_SECRET` configurável

## Falhas em Cascata

- Qdrant indisponível → chat RAG sem semântica → ingest falha
- Ollama indisponível → sem geração em chat/corretor
- FastAPI cai durante job async → turno perdido
- JSON registry corrompido → todos os projetos afetados

## Recomendações por Horizonte

### Curto prazo (0-3 meses)
- Corrigir testes quebrados
- Refatorar `chat_service.py` em handlers por modo
- Configurar `SESSION_SECRET` e proteger rotas públicas

### Médio prazo (3-12 meses)
- Mover lógica de UI do core
- Migrar persistência JSON para SQLite/Postgres
- Adicionar logger estruturado e métricas

### Longo prazo (12+ meses)
- Remover `legacy/app.py`
- Adicionar fila persistente para jobs
- Clusterizar Qdrant/Ollama

## Conclusão

A arquitetura atende ao propósito funcional, mas acumulou dívidas significativas durante a transição Streamlit → FastAPI + React. A principal ameaça é a concentração de responsabilidades em poucos arquivos e a falta de resiliência operacional. Recomenda-se priorizar correções de segurança, testes e refatoração dos componentes críticos.
