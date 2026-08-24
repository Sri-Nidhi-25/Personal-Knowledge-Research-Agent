# Grounding LLMs with Retrieval-Augmented Generation (RAG)

## 1. Concept and Mechanism
Retrieval-Augmented Generation (RAG) anchors model responses to external, verified knowledge repositories. Instead of relying solely on parametric memory, the system fetches relevant document chunks and provides them as dynamic in-context evidence.

## 2. Advanced Retrieval Strategies
- **Hybrid Search**: Combines dense vector similarity (semantic embeddings) with sparse keyword retrieval (BM25) for high recall and exact keyword precision.
- **Reranking Models**: Cross-encoders score candidate passages to prioritize high-relevance evidence in the LLM's primary attention window.
- **Hierarchical Chunking**: Small chunks are used for vector retrieval, while parent sections are passed to the generator to preserve semantic context.

## 3. Self-Reflective Retrieval Frameworks
- **Self-RAG**: The model generates reflection tokens to assess whether retrieval is needed, whether retrieved passages are relevant, and whether generated assertions are faithful.
- **Corrective RAG (CRAG)**: Evaluates retrieval quality with an external evaluator and falls back to web search when local context confidence is low.
