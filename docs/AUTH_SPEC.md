# Autenticação PDF Extreme AI v2

Auth isolada no **servidor onde o v2 roda** (`pdf_extreme_ai_v2/data/auth/`). Não depende do GEP nem de arquivos em outra máquina.

## Fluxos

```mermaid
flowchart TD
  A[Login] --> B{Autorizado?}
  B -->|não| E403[403 não autorizado]
  B -->|sim| C{Tem senha?}
  C -->|não| E403b[403 use Primeiro Acesso]
  C -->|sim| D{Senha OK?}
  D -->|não| E401[401 incorretos]
  D -->|sim| OK[Sessão cookie]

  P[Primeiro Acesso] --> P1{Autorizado?}
  P1 -->|não| E403p[403]
  P1 -->|sim| P2{Já tem senha?}
  P2 -->|sim| E409[409]
  P2 -->|não| P3[validar_senha + hash]
  P3 --> OKp[Cadastro OK]

  R[Admin reset consultor] --> R1[senha_hash=null primeiro_acesso=true]
  R1 --> P
```

## GEP vs RAG (nomes)

| GEP | PDF Extreme AI v2 |
|-----|-------------------|
| `admins.json` | `data/auth/admins.json` |
| `usuarios_gep.json` | `data/auth/usuarios_app.json` |
| Streamlit session | Cookie `pdf_extreme_session` (Starlette SessionMiddleware) |

## Deploy SSH

```bash
cd pdf_extreme_ai_v2
cp .env.example .env   # editar SESSION_SECRET, BOOTSTRAP_ADMIN_USER
python scripts/bootstrap_admin.py seu.usuario
cd backend && pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8765 --reload
```

1. Abrir frontend → **Primeiro Acesso** com `seu.usuario`
2. **Login** como admin
3. **Usuários** (sidebar) → adicionar consultores
4. Consultor faz Primeiro Acesso na máquina dele

Sincronizar usuários com o GEP é **manual** (copiar listas para `admins.json` / `consultores` se desejado).

## Projetos por utilizador

Cada projeto tem `owner_id` (login). **Admin e consultor** veem apenas projetos em que `owner_id` é o seu utilizador.

Projetos antigos sem `owner_id` não aparecem para ninguém até migração:

```bash
export PDF_EXTREME_AI_ROOT=/home/labfaces/pdf_extreme_ai
python pdf_extreme_ai_v2/scripts/assign_project_owners.py paulo.pmgir
```

Use `--dry-run` para pré-visualizar.

## Credenciais de serviço

`auth/service_credentials.py` — stub Fernet por máquina. **N/A** para Ollama local. Não copiar `.enc` de outro host.

## Segurança

- Senhas: werkzeug `pbkdf2:sha256`
- APIs não retornam `senha_hash`
- Admin não define senha de terceiros; só **reset** (consultores)
- `SESSION_SECRET` obrigatório em produção
- `SESSION_HTTPS_ONLY=true` com HTTPS
