# PDF Extreme AI — Frontend v2

React + Vite + TypeScript com TanStack Query e chat via SSE.

## Pré-requisitos

- **Node.js 18+** (recomendado: 20 LTS). O Node 12 do Ubuntu (`apt install nodejs`) **não funciona** com Vite 5.
- API FastAPI rodando (ver `../README.md`)

### Node 12 no sistema (`EBADENGINE`)

O pacote `nodejs` do Ubuntu costuma ser v12. Use **nvm** (já há `.nvmrc` com `20`):

```bash
# Instalar nvm (uma vez)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.bashrc   # ou: source ~/.nvm/nvm.sh

cd pdf_extreme_ai_v2/frontend
nvm install      # lê .nvmrc → Node 20
nvm use
node -v        # deve mostrar v20.x
rm -rf node_modules package-lock.json
npm install
npm run dev
```

Em cada novo terminal, antes de `npm run dev`:

```bash
source ~/.nvm/nvm.sh && nvm use
```

## Configuração

```bash
cd pdf_extreme_ai_v2/frontend
cp .env.example .env
# Edite VITE_API_URL se a API não estiver em http://127.0.0.1:8765
npm install
```

### `VITE_API_URL`

| Valor | Uso |
|-------|-----|
| `http://127.0.0.1:8765` | API direta (CORS já habilitado no backend) |
| `/api` | Dev com proxy Vite (`vite.config.ts` → porta 8765) |

## Rodar

```bash
# Terminal 1 — API
cd ../backend
export PDF_EXTREME_AI_ROOT=/home/labfaces/pdf_extreme_ai
uvicorn main:app --host 127.0.0.1 --port 8765

# Terminal 2 — Frontend
cd ../frontend
npm run dev
```

Abra http://127.0.0.1:5173 ou, na rede local, `http://<IP-da-máquina>:5173` (ex. `http://10.61.242.161:5173`).

O Vite está configurado com `host: true` e `VITE_API_URL=/api` para o browser chamar a API via **proxy** no mesmo host/porta (evita `127.0.0.1:8765` no PC do cliente).

## Layout (v2)

- **Sidebar única:** projetos + conversas + botão “Memória & regras”
- **Modo Autos (RAG):** coluna **Fontes** (upload/lista PDF) + chat central largo (estilo NotebookLM)
- **Chat livre / Corretor:** chat ou corretor em largura total
- **Config RAG:** ícone ⚙ no header do chat
- **Modelo:** seletor no rodapé do campo de pergunta (estilo Gemini)
- Rodapé `dev` só em `npm run dev`

## Funcionalidades (esta entrega)

- Sidebar: listar / criar / excluir projetos
- Coluna: listar / nova / renomear / excluir conversas
- Chat: modos **Autos (RAG)** e **Chat livre**, stream SSE (tokens + thinking + telemetria + trechos)
- Modelo, estratégia RAG, modo auditoria, memória do caso (chat livre)

**Corretor:** próxima entrega.

## Comparar com Streamlit

1. Mesmo projeto indexado (ex. `teste`) em ambas as UIs
2. Mesma pergunta no modo Autos (RAG)
3. Verifique telemetria e trechos recuperados no rodapé da mensagem

## Build produção

```bash
npm run build
npm run preview
```
