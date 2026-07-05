# Relatório de Auditoria de Segurança — PDF Extreme AI

## Resumo Executivo

A aplicação apresenta vulnerabilidades e riscos significativos, especialmente em autenticação, autorização, exposição de endpoints e proteção de dados. A maior parte dos problemas pode ser mitigada com configuração e pequenas alterações de código.

## Score

**Pontuação estimada:** 45/100

**Classificação:** Ruim

## Vulnerabilidades Críticas

### V01 — `SESSION_SECRET` default previsível
- **Categoria:** Session Management
- **Exploração:** Se `SESSION_SECRET` não for configurado, o valor default `"dev-change-me-in-production"` permite forjar cookies de sessão.
- **Impacto:** Sequestro de sessão, acesso não autorizado.
- **Probabilidade:** Alta em deploys descuidados.
- **Severidade:** Crítica.
- **Evidências:** `backend/main.py:44`
- **Correção:** Exigir `SESSION_SECRET` em produção; falhar ao iniciar se vazio/default.

### V02 — Endpoints de proofread públicos
- **Categoria:** Autorização
- **Exploração:** `POST /proofread` e `POST /proofread/stream` não exigem autenticação. Qualquer pessoa pode consumir LLM e recursos computacionais.
- **Impacto:** Abuso de recursos, potencial extração de informações via prompts.
- **Probabilidade:** Alta se API exposta.
- **Severidade:** Crítica.
- **Evidências:** `backend/api/proofread.py:14`, `backend/api/proofread.py:46`
- **Correção:** Adicionar `Depends(require_auth)`.

### V03 — Dados de produção em `data/` no repositório
- **Categoria:** Dados
- **Exploração:** O repositório contém ~1,1 GB de dados reais (PDFs, conversas, registry, auth). Se publicado, há vazamento massivo.
- **Impacto:** Vazamento de dados sensíveis de clientes.
- **Probabilidade:** Alta se repo for tornado público.
- **Severidade:** Crítica.
- **Evidências:** `data/`
- **Correção:** Remover do VCS, adicionar a `.gitignore`, migrar para storage externo.

## Vulnerabilidades Altas

### V04 — Endpoint `/export/markdown` público
- **Categoria:** Autorização / Vazamento de dados
- **Exploração:** Recebe `user_prompt`, `assistant_md`, `thinking`, `telemetry`, `retrieved_chunks` e retorna markdown formatado. Embora não acesse banco, permite que terceiros processem dados potencialmente sensíveis sem autenticação.
- **Impacto:** Processamento não autorizado de conteúdo; possível vazamento indireto.
- **Probabilidade:** Média.
- **Severidade:** Alta.
- **Evidências:** `backend/api/export.py:21-32`
- **Correção:** Adicionar autenticação.

### V05 — Rate limit de login em memória
- **Categoria:** APIs / Brute-force
- **Exploração:** `_LOGIN_ATTEMPTS` é dicionário global em memória. Não funciona entre workers e reinicia com o processo.
- **Impacto:** Brute-force de senhas viável em deploy multi-worker ou após restart.
- **Probabilidade:** Média.
- **Severidade:** Alta.
- **Evidências:** `backend/api/auth.py:15-45`
- **Correção:** Rate limit persistente (Redis) ou proteção por WAF/reverse proxy.

### V06 — XSS via `dangerouslySetInnerHTML` no corretor
- **Categoria:** Frontend / XSS
- **Exploração:** `ProofreadPanel.tsx` renderiza `highlighted_html` vindo do backend via `dangerouslySetInnerHTML`. Se o LLM ou parser produzirem HTML malicioso, há execução de script.
- **Impacto:** Sequestro de sessão, ações em nome do usuário.
- **Probabilidade:** Média (depende de prompt injection no LLM).
- **Severidade:** Alta.
- **Evidências:** `frontend/src/components/ProofreadPanel.tsx:116-119`
- **Correção:** Sanitizar HTML (DOMPurify) ou renderizar diff de forma segura.

### V07 — JSON de auth sem lock de concorrência
- **Categoria:** Dados / Integridade
- **Exploração:** Múltiplas requisições simultâneas podem corromper `usuarios_app.json` ou `admins.json`.
- **Impacto:** Perda/corruptão de credenciais.
- **Probabilidade:** Média.
- **Severidade:** Alta.
- **Evidências:** `backend/auth/store.py`
- **Correção:** Lock de arquivo ou migração para banco.

### V08 — CORS origins default amplas
- **Categoria:** Infra / Network
- **Exploração:** `CORS_ORIGINS` default inclui `localhost:5173` e `127.0.0.1:5173`. Se não substituído em produção, permite requisições de origens locais.
- **Impacto:** CSRF-like em ambientes compartilhados.
- **Probabilidade:** Média.
- **Severidade:** Média/Alta.
- **Evidências:** `backend/main.py:45-52`
- **Correção:** Forçar configuração explícita em produção; não usar defaults.

## Vulnerabilidades Médias

### V09 — Informação de admin/consultor exposta em `/auth/primeiro-acesso/check`
- **Categoria:** Information Leakage
- **Exploração:** Endpoint público revela se usuário está autorizado, se tem senha e qual perfil previsto.
- **Impacto:** Enumeração de usuários e perfis.
- **Probabilidade:** Alta.
- **Severidade:** Média.
- **Evidências:** `backend/api/auth.py:120-134`
- **Correção:** Retornar mensagem genérica; não revelar perfil.

### V10 — Respostas de erro detalhadas podem expor estrutura interna
- **Categoria:** Information Leakage
- **Exploração:** Exceções podem retornar detalhes internos em respostas HTTP.
- **Impacto:** Enumeração interna.
- **Probabilidade:** Baixa/Média.
- **Severidade:** Média.
- **Evidências:** Padrão observado em vários endpoints.
- **Correção:** Tratamento centralizado de erros sem expor stack traces.

### V11 — Upload de arquivos sem validação de conteúdo
- **Categoria:** Input Validation / File Upload
- **Exploração:** Valida extensão `.pdf` e tamanho, mas não verifica magic bytes ou conteúdo real.
- **Impacto:** Upload de arquivos maliciosos disfarçados.
- **Probabilidade:** Média.
- **Severidade:** Média.
- **Evidências:** `backend/services/documents_service.py:45`
- **Correção:** Verificar magic bytes; isolar processamento em sandbox.

### V12 — `service_credentials.py` deriva chave de informações do host
- **Categoria:** Secrets
- **Exploração:** Chave Fernet derivada de `platform.node() + platform.system() + platform.machine()`. Máquinas idênticas podem gerar mesma chave.
- **Impacto:** Criptografia fraca de credenciais.
- **Probabilidade:** Baixa (ainda não usado para Ollama local).
- **Severidade:** Média.
- **Evidências:** `backend/auth/service_credentials.py`
- **Correção:** Usar chave gerada aleatoriamente e armazenada em secret manager.

## Riscos Arquiteturais de Segurança

- Acoplamento backend/core dificulta auditoria e isolamento.
- Lógica de UI no core aumenta superfície de ataque.
- Jobs em threads daemon dificultam rastreamento de abuso.

## Riscos Operacionais de Segurança

- Deploy single-instance sem WAF.
- Dados sensíveis em filesystem local sem criptografia.
- Logs podem conter dados sensíveis (não auditado).

## Riscos de Supply Chain

| Dependência | Risco | Ação |
|---|---|---|
| `llama-index` | Monkey-patch depende de APIs internas | Manter atualizado e testar |
| `ollama` (biblioteca) | Formato de thinking pode mudar | Testar após upgrades |
| `torch` / `transformers` | Vulnerabilidades conhecidas | Auditar CVEs periodicamente |
| `fastapi` / `uvicorn` | Vulnerabilidades conhecidas | Manter atualizado |

## Roadmap de Remediação

### Curto prazo (0-3 meses)
- Configurar `SESSION_SECRET` obrigatório
- Proteger `/proofread` e `/export/markdown` com autenticação
- Remover `data/` do controle de versão
- Sanitizar HTML no corretor
- Corrigir rate limit de login

### Médio prazo (3-12 meses)
- Migrar auth para banco com locks/transações
- Implementar tratamento centralizado de erros
- Adicionar validação de conteúdo de upload
- Revisar CORS origins em produção

### Longo prazo (12+ meses)
- Adicionar MFA para admins
- Criptografia em repouso para dados sensíveis
- WAF/reverse proxy com rate limiting
- Auditoria de logs e alertas de segurança

## Trade-offs

| Remediação | Benefício | Custo | Risco de implementar | Risco de não implementar |
|---|---|---|---|---|
| Proteger endpoints públicos | Reduz abuso | Baixo | Quebrar integrações não autenticadas | Alto |
| Remover `data/` do VCS | Evita vazamento | Baixo | Perder dados se não backup | Alto |
| Migrar auth para banco | Concorrência segura | Médio | Mudança de infra | Alto |
| Adicionar MFA | Segurança maior | Médio | UX | Alto para admins |

## Conclusão

A segurança do PDF Extreme AI precisa de atenção imediata. Os riscos críticos (secret default, endpoints públicos, dados no repo) são facilmente exploráveis e devem ser corrigidos antes de qualquer deploy em ambiente compartilhado. Recomenda-se aprovar as remediações de curto prazo imediatamente.
