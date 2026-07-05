# PDF Extreme AI — Frontend Summary

## Stack

- React 18 + TypeScript + Vite
- React Router v6
- TanStack Query v5
- react-markdown + remark-gfm
- Vitest + jsdom + Testing Library

## Estrutura

```text
main.tsx
  ↓
App.tsx (rotas, AuthProvider, QueryClient)
  ↓
AppShell
  ├── UnifiedSidebar (projetos + conversas)
  ├── MainWorkspace
  │     ├── ModeTabs
  │     ├── DocumentsPanel (modo RAG)
  │     └── ChatPanel
  ├── ConfigDrawer
  └── ResizeHandle
```

## Rotas

- `/login`
- `/primeiro-acesso`
- `/configuracoes/usuarios` (admin)
- `/` (app principal)

## Fluxos principais

- Login via cookie de sessão
- Criação/renomeação/exclusão de projetos
- Upload de PDFs com SSE de progresso
- Chat RAG/free com async turns
- Corretor ortográfico via SSE
- Configuração de regras e memória do projeto

## Integração

- Consome backend em `/api` (proxy Vite) ou `VITE_API_URL`
- Todas as requisições usam `credentials: include`
- SSE customizado para chat, ingest e proofread

## Riscos

- Componentes legados não utilizados (`ProjectSidebar`, `ConversationList`)
- Duplicação de hooks de streaming (`useChatStream` vs `useChatTurn`)
- CSS monolítico (~1790 linhas)
- `dangerouslySetInnerHTML` no corretor
- Hardcodes de modelo/perfil
- Teste `chat.test.ts` quebrado

## Dívidas

- Remover código morto
- Unificar lógica de streaming
- Escopar CSS
- Parametrizar modelos no backend
