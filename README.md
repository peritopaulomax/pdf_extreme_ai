# PDF Extreme AI

Assistente RAG para PDFs juridicos, com:

- chat em Streamlit;
- busca hibrida (semantica no Qdrant + lexical FTS5 em SQLite);
- suporte a multiplos modelos locais via Ollama;
- isolamento por projeto (cada projeto com colecao e base lexical proprias).

## 1) Requisitos de sistema (maquina zerada)

- Ubuntu 22.04+ (recomendado para este setup).
- GPU NVIDIA (instalacao alvo: RTX 3090).
- Docker + Docker Compose plugin.
- Python 3.11.
- Ollama.

## 2) Atualizar driver NVIDIA (importante)

Se o driver estiver antigo, CUDA/PyTorch podem falhar no ingest/chat.

1. Rode o script do projeto:

```bash
sudo bash scripts/upgrade_nvidia_driver.sh
```

1. Reinicie:

```bash
sudo reboot
```

1. Valide apos reiniciar:

```bash
nvidia-smi
```

Se aparecer tabela da GPU sem erro, a base esta pronta para CUDA.

## 3) Instalar dependencias de sistema

```bash
sudo apt-get update
sudo apt-get install -y python3.11 python3-pip docker.io docker-compose-plugin curl
sudo usermod -aG docker $USER
```

Feche e abra a sessao (ou reboot) para o grupo `docker` entrar em vigor.

## 4) Miniconda + ambiente Python (recomendado)

Se a maquina ainda nao tem Miniconda:

```bash
mkdir -p ~/miniconda3
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda3/miniconda.sh
bash ~/miniconda3/miniconda.sh -b -u -p ~/miniconda3
~/miniconda3/bin/conda init bash
```

Feche e abra o terminal antes de continuar.

## 5) Clonar projeto e criar ambiente conda

```bash
git clone <URL_DO_REPOSITORIO>
cd pdf_extreme_ai
conda create -n pdfextreme python=3.11 -y
conda activate pdfextreme
python -m pip install --upgrade pip setuptools wheel
```

Instale os pacotes Python usados pelo codigo:

```bash
pip install \
  streamlit \
  torch \
  llama-index \
  llama-index-core \
  llama-index-llms-ollama \
  llama-index-embeddings-huggingface \
  llama-index-vector-stores-qdrant \
  qdrant-client \
  sentence-transformers \
  pymupdf \
  pypdf
```

## 6) Instalar Ollama e baixar modelos

Instalar Ollama:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Baixar modelos recomendados para este projeto:

```bash
ollama pull gemma4:e4b
ollama pull qwen2.5:7b-instruct
ollama pull gemma4-pericia:latest
ollama pull deepseek-r1:14b
```

Validar:

```bash
ollama list
curl --noproxy 127.0.0.1,localhost -s http://127.0.0.1:11434/api/tags
```

## 7) Subir Qdrant (vetor)

```bash
docker compose up -d qdrant
```

Validar:

```bash
python scripts/test_qdrant_connection.py
```

## 8) Configurar ambiente `.env`

Copie o exemplo:

```bash
cp .env.example .env
```

Pontos principais no `.env`:

- `QDRANT_HOST=127.0.0.1`
- `QDRANT_PORT=6333`
- `OLLAMA_HOST=http://127.0.0.1:11434`
- `OLLAMA_MODELS=gemma4:e4b,qwen2.5:7b-instruct,gemma4-pericia:latest,deepseek-r1:14b`
- `OLLAMA_MODEL_DEFAULT=gemma4:e4b`

Modelos Hugging Face usados no pipeline:

- Embeddings: `BAAI/bge-m3`
- Reranker: `BAAI/bge-reranker-base`

Observacao: os pesos sao baixados automaticamente no primeiro uso (cache local em `~/.cache/huggingface`), ou voce pode fixar paths locais em:

- `EMBEDDING_MODEL_PATH`
- `RERANKER_MODEL_PATH`

## 9) Ingestao dos PDFs

Coloque os PDFs na pasta `data/` e rode:

```bash
python scripts/ingest.py --data-dir ./data
```

Rebuild completo (destrutivo):

```bash
python scripts/ingest.py --data-dir ./data --rebuild --reprocess-all
```

## 10) Rodar a aplicacao

```bash
streamlit run app.py
```

Na UI:

- crie/selecione um projeto na sidebar;
- envie PDFs (auto-ingest opcional);
- escolha o modelo no topo do chat;
- faca perguntas com citacoes de pagina/arquivo.

## 11) Checklist rapido de validacao

- `nvidia-smi` sem erro.
- Qdrant ativo em `127.0.0.1:6333`.
- Ollama ativo em `127.0.0.1:11434`.
- `streamlit run app.py` abre a interface sem erro.
- Ingest finaliza sem erro.
- Chat responde com contexto do projeto ativo.

## 12) Operacao e tuning

Para fluxo operacional, calibracao RTX 3090 e perfis de recuperacao (`rapido`, `preciso`, `pericial`), veja:

- `OPERATIONS.md`

