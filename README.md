# 🧠 Personal Knowledge Research Agent

An autonomous, local-first AI research assistant and knowledge gap filler. The agent continuously analyzes your personal knowledge corpus, detects structural, semantic, and temporal knowledge gaps using a **Deep Knowledge Gap Engine**, autonomously browses and fetches external research to bridge those gaps, verifies claims against source evidence, and synthesizes structured knowledge proposals for your review and approval.

---

## 🌟 Key Features

* 📂 **Multi-Format Document Ingestion**: Ingest Markdown (`.md`), Text (`.txt`), and PDF (`.pdf`) documents from dedicated topic folders with automatic chunking and deduplication.
* 🕸️ **Knowledge Graph & Topology**: Automatically extracts concepts, keywords, and relationship triples (`relates_to`, `is_part_of`) to construct a traversable knowledge graph.
* 🔬 **Deep Knowledge Gap Engine (Multi-Stage Reasoning)**:
  * **Structured Knowledge Modeling**: Derives structured profiles across functional knowledge roles (`FOUNDATIONAL`, `MECHANISM`, `IMPLEMENTATION`, `EVALUATION`, `LIMITATION`, `FAILURE_MODE`, `SECURITY`, `TRADEOFF`, `OPERATIONAL`, `TEMPORAL`).
  * **Knowledge Depth & Coverage Matrix**: Computes a 0–5 depth scale per role to diagnose structural imbalances (e.g. *Deep Implementation = 5 + Zero Evaluation = 0*).
  * **Multi-Signal Candidate Generation**: Flags structural omissions, missing prerequisites, evaluation voids, security omissions, and temporal/frontier drift.
  * **Significance & Counterfactual Analysis**: Filters out trivial 1-off words and evaluates practical consequences (*"What will fail or be misunderstood if this knowledge remains missing?"*).
  * **Dual-Relevance Scoring**: Separates **Personal Relevance** from **Current SOTA Relevance (2026)**.
* 🤖 **Autonomous Real-World Web Research Loop**:
  * Real-time web search via **Brave Search API** & **DuckDuckGo** (`ddgs`) with zero mock or fake data.
  * Deep web page scraping with realistic browser headers, BeautifulSoup content sanitization, and fallback extraction.
  * Scaled research budgets (up to 25 sources and 15 results per query) to satisfy multi-source corroboration.
* ⚖️ **Multi-Source Confidence & Verification Engine**:
  * **Strict Multi-Source Rubric**:
    * **$\ge 90\%$ Confidence**: Corroborated by $\ge 10$ distinct web sources.
    * **$\ge 80\%$ Confidence**: Corroborated by $\ge 7$ distinct web sources.
    * **$\ge 75\%$ Confidence**: Corroborated by $> 5$ distinct web sources (6 sources).
    * **$60\%$ Confidence**: Corroborated by exactly 5 distinct web sources.
    * **$< 60\%$ Confidence (Quarantine & Warning)**: $< 5$ sources (flagged with warnings and quarantined for re-verification).
  * Synthesizer quality filter: Only claims with $\ge 75\%$ confidence are included in the Core Findings section.
* 📂 **Dual-Destination Research Persistence**:
  * Approved research markdown files are automatically saved to two destinations:
    1. Dedicated research archive (`data/documents/research/`).
    2. Origin source folder from which the analyzed document originated (e.g. `data/documents/llm_hallucinations/`).
* 📊 **Live Dashboard & Real-Time Gap Lifecycle Tracking**:
  * Real-time dashboard metric cards: **Active Gaps**, **Resolved Gaps**, **Proposals in Review**, and **Total Documents**.
  * Instant lifecycle synchronization: approving a research proposal immediately marks the gap as `resolved`, removes it from the active knowledge gap view, and updates dashboard counters without requiring page refreshes.
* 🛡️ **Fault-Tolerant Chunking & Ingestion Engine**:
  * Heading-aware text chunker with a 3-tier retry loop. If any section fails, the entire document is automatically re-chunked.
  * Automatic fallback to paragraph-only chunking if heading parsing fails.
  * Database transaction rollback with fresh UUID generation on insertion errors to prevent partial document states.
  * Pipeline-level cleanup in `index_service.py` that purges partial Chroma vectors and SQLite records before retrying.
* 📈 **Evaluation & Benchmark Suite (Spec 11)**:
  * Automated synthetic benchmark runner measuring **Citation Grounding**, **Multi-Source Consensus**, and **Proposal Structural Completeness**.

---

## 📊 Evaluation Metrics & How They Are Calculated

The system includes a built-in **Evaluation & Benchmarks Engine** (`backend/app/evaluation/metrics.py`) implementing formal quantitative criteria:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EVALUATION METRICS FORMULA                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. Citation Grounding Score (40% Weight):                                  │
│     Grounding = (Count of claims with valid supporting evidence) / (Total)   │
│     Measures what proportion of synthesized claims are backed by external   │
│     factual web evidence.                                                   │
│                                                                             │
│  2. Multi-Source Consensus Ratio (20% Weight):                              │
│     Consensus = (Count of claims backed by >= 2 distinct sources) / (Total) │
│     Measures whether claims represent consensus across multiple independent │
│     domains rather than a single website.                                   │
│                                                                             │
│  3. Proposal Structural Completeness (40% Weight):                          │
│     Completeness = (Passed Section Checks) / 5                              │
│     Verifies presence of:                                                   │
│       • Executive Summary                                                   │
│       • Key Concepts                                                        │
│       • Verified Findings                                                   │
│       • Markdown Citations                                                  │
│       • Bibliography / Source References                                    │
│                                                                             │
│  ═════════════════════════════════════════════════════════════════════════  │
│  Overall Quality Score = (0.4 × Grounding) + (0.2 × Consensus) +            │
│                          (0.4 × Completeness)                               │
│                                                                             │
│  Status: PASS (Score >= 0.75 / 75%) | NEEDS_IMPROVEMENT (< 0.75)            │
└─────────────────────────────────────────────────────────────────────────────┘
```

You can run the benchmark suite at any time from the **Evaluation & Metrics** tab in the web UI.

---

## 🏗️ Architecture Overview

```
                          ┌───────────────────────────┐
                          │   React + Vite Frontend   │
                          │   (Port 3000 / Modern UI) │
                          └─────────────┬─────────────┘
                                        │ REST / SSE
                                        ▼
                          ┌───────────────────────────┐
                          │      FastAPI Backend      │
                          │        (Port 8000)        │
                          └──────┬─────────────┬──────┘
                                 │             │
                 ┌───────────────┴──┐       ┌──┴───────────────┐
                 ▼                  ▼       ▼                  ▼
       ┌──────────────────┐  ┌───────────┐ ┌─────────────┐ ┌───────────────┐
       │   SQLite DB      │  │ ChromaDB  │ │ Local Ollama│ │ Search Engine │
       │ (Runs, Proposals,│  │  Vector   │ │ (LLM +      │ │ (Brave Search/│
       │  Concepts, Gaps) │  │  Chunks)  │ │  Embeddings)│ │  DuckDuckGo)  │
       └──────────────────┘  └───────────┘ └─────────────┘ └───────────────┘
```

---

## 📋 Prerequisites

1. **Python**: Python 3.10 to 3.14 (with virtual environment support).
2. **Node.js**: Node.js 18+ and npm (or the portable binary in `tools/node`).
3. **Ollama (Optional, for 100% local neural execution)**:
   * Download and install from [ollama.com](https://ollama.com).
   * Pull recommended models:
     ```bash
     ollama pull llama3.2
     ollama pull nomic-embed-text
     ```
4. **Brave Search API Key (Recommended for live web search)**:
   * Obtain a free API key at [brave.com/search/api/](https://brave.com/search/api/).

---

## ⚙️ Configuration (`.env`)

Create or edit the `.env` file in the project root:

```ini
# App Settings
APP_NAME=Personal Knowledge Research Agent
DEBUG=true
HOST=0.0.0.0
PORT=8000

# Storage Paths
DATA_DIR=data
DOCUMENTS_DIR=data/documents
CHROMA_DIR=data/chroma
DATABASE_URL=sqlite:///data/database/app.db
KNOWLEDGE_DIR=data/knowledge

# --- LLM with Ollama ---
LLM_PROVIDER=ollama
LLM_MODEL=llama3.2
LLM_BASE_URL=http://localhost:11434/v1
LLM_TEMPERATURE=0.2

# --- Vector Embeddings with Ollama ---
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIM=768
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_LLM_MODEL=llama3.2

# --- Web Search Provider (brave / duckduckgo) ---
SEARCH_PROVIDER=brave
BRAVE_SEARCH_API_KEY=your_brave_api_key_here

# Research Budgets & Multi-Source Limits
MAX_RESEARCH_ITERATIONS=8
MAX_SEARCH_QUERIES=15
MAX_SOURCES_PER_RUN=25
MAX_FETCHES_PER_RUN=25
MAX_RUNTIME_MINUTES=10
FETCH_TIMEOUT_SECONDS=15
MAX_CONTENT_LENGTH_BYTES=1000000
```

---

## 🚀 Quick Start Guide

### Step 1: Start the Backend Server

#### On PowerShell (Windows):
```powershell
.\backend\venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### On Git Bash (Windows) / macOS / Linux:
```bash
./backend/venv/Scripts/python.exe -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

*Backend API Documentation is available at:* `http://localhost:8000/docs`

---

### Step 2: Start the Frontend UI

In a new terminal window:

#### On PowerShell:
```powershell
$env:PATH = "D:\Personal Knowledge gap filler\tools\node;" + $env:PATH
cd frontend
npm run dev
```

#### On Git Bash:
```bash
export PATH="/d/Personal Knowledge gap filler/tools/node:$PATH"
cd frontend
npm run dev
```

*Open your browser and navigate to:* `http://localhost:3000/`

---

## 📖 How to Use the System

### 1. Ingest Knowledge Documents
* Place your `.md`, `.txt`, or `.pdf` research notes inside a subfolder under `data/documents/` (e.g. `data/documents/llm_hallucinations/`).
* In the UI under **Dashboard**, enter `data/documents/llm_hallucinations` into the **Ingest Local Folder** field and click **Scan & Ingest Folder**.
* The agent chunks each file with retry protection, indexes vectors into ChromaDB, and builds the initial concept graph.

### 2. Scan for Deep Knowledge Gaps
* Switch to the **Knowledge Gaps** tab.
* Click **Scan for Deep Gaps**.
* The **Deep Knowledge Gap Engine** analyzes knowledge depth across roles (`FOUNDATIONAL`, `MECHANISM`, `IMPLEMENTATION`, `EVALUATION`, `SECURITY`, `TEMPORAL`), assesses counterfactual impact, and surfaces high-value research opportunities.

### 3. Run Autonomous Research
* Click **Research Gap** on any discovered gap (or enter a custom query in the **Research Workspace** tab).
* The research loop runs asynchronously in a background thread with live SSE streaming.
* It searches live web sources (Brave/DuckDuckGo), scrapes content, extracts evidence, clusters cross-source claims, and calculates multi-source confidence scores.

### 4. Review and Approve Proposals
* Switch to the **Proposals & Approval** tab.
* Inspect the synthesized findings (strictly $\ge 75\%$ confidence), sources, and relationship triples.
* Click **Approve**.
* The proposal is saved to both `data/documents/research/` and the original topic folder, the gap is marked as **resolved** and removed from the active gaps view, and the dashboard metrics update live.

### 5. Run Evaluation Benchmarks
* Switch to the **Evaluation & Metrics** tab.
* Click **Run Benchmark Suite** to measure Citation Grounding, Consensus Ratio, and Proposal Completeness scores across synthetic benchmarks.

---

## 🧪 Running Automated Tests

The test suite covers unit tests, deep gap engine, chunking retries, claim verification, API endpoints, and SSE streaming.

```powershell
# On PowerShell
.\backend\venv\Scripts\pytest.exe backend/tests/ -v
```

---

## 📁 Repository Structure

```
├── backend/
│   ├── app/
│   │   ├── agent/            # Research orchestrator, planner, unified LLM client
│   │   ├── api/              # FastAPI routers (documents, gaps, research, eval, health)
│   │   ├── config/           # Settings and environment configuration management
│   │   ├── evaluation/       # Benchmark suite and metrics engine (Grounding, Consensus)
│   │   ├── knowledge/        # Chunking with retry, embeddings, ingestion, graph, deep_gap_engine
│   │   │   ├── deep_gap_engine.py  # Deep Knowledge Gap Engine (Coverage Matrix, Counterfactual)
│   │   │   ├── gap_discovery.py    # Gap discovery service and CRUD persistence
│   │   │   ├── knowledge_repr.py   # Concept registry and graph extraction
│   │   │   ├── ingestion.py        # Multi-format document parser and pipeline
│   │   │   ├── chunking.py         # Resilient heading-aware text chunking with retries
│   │   │   ├── index_service.py    # Pipeline-level indexing orchestrator with retry/cleanup
│   │   │   └── embeddings.py       # Pluggable vector embeddings (Ollama, FastEmbed, Hash)
│   │   ├── models/           # Pydantic schemas (KnowledgeGap, ResearchPlan, Proposal)
│   │   ├── storage/          # SQLite database (app.db) and ChromaDB vector store
│   │   ├── synthesis/        # Proposal markdown synthesizer with >= 75% confidence gate
│   │   ├── tools/            # Real web search (Brave / DDG), web scraper with headers
│   │   └── verification/     # 10+ source confidence verifier & contradiction detector
│   └── tests/                # 58+ unit, regression, and API integration test cases
├── frontend/
│   ├── src/
│   │   ├── api/              # REST client and SSE event subscriber
│   │   └── App.jsx           # Dashboard, Gaps, Workspace, Proposals, and Evaluation tabs
│   ├── package.json
│   └── vite.config.js
├── data/
│   ├── documents/            # Source topic folders and approved research notes
│   ├── database/             # SQLite application database (app.db)
│   └── chroma/               # ChromaDB persistent vector index
├── tools/node/               # Portable Node.js binaries
└── .env                      # Application environment configuration
```

---

## 🛡️ License

MIT License. Designed for autonomous, private personal knowledge expansion.

