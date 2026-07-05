# PDF Extreme AI — Mental Model

## O sistema é

Um assistente de leitura de autos jurídicos. O usuário faz upload de PDFs, o sistema "lê" e indexa esses PDFs, e o usuário pode fazer perguntas naturais recebendo respostas com citações.

## Analogia

Pense em um estagiário jurídico que:
1. Recebe uma pilha de PDFs
2. Lê e organiza por tema/página
3. Quando perguntado, procura nos documentos e responde citando página e arquivo

## Conceitos fundamentais

- **Projeto** = pasta de trabalho de um caso
- **Documento** = PDF dentro do projeto
- **Chunk** = pedaço de texto de um PDF com referência de página
- **Índice semântico** = busca por significado (Qdrant + embeddings)
- **Índice lexical** = busca por palavras exatas (SQLite FTS5)
- **Turno** = uma pergunta + resposta, pode ser longo e assíncrono
- **Memória do caso** = notas editáveis sobre o projeto

## Como as partes se relacionam

- Frontend pede; Backend orquestra; Core executa
- Core depende de Qdrant (memória vetorial), SQLite (memória textual) e Ollama (raciocínio)
- Cada projeto tem seu próprio "cérebro" (coleção Qdrant + banco lexical)

## O que pode dar errado

- Sem Ollama → sem respostas
- Sem Qdrant → sem busca semântica
- Sem FTS5 → sem recall lexical
- Sem sessão configurada → segurança comprometida
- JSON corrompido → projetos somem

## Como evoluir

- Separar UI do core
- Migrar JSON para banco
- Quebrar serviços grandes
- Adicionar filas persistentes
- Remover legado Streamlit
