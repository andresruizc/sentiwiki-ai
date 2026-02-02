## 🔧 Scripts & Commands Overview

This page gives you a **single place** to see how to run the main pieces of the system: data pipeline, crawler, FastAPI API, frontend, and evaluation.

For full details on arguments and edge-cases, see `scripts/README.md` and `data/README.md`.

---

### 🚀 From scratch to running app (local)

```bash
# 0. (If needed) Clone and enter repo
git clone https://github.com/YOUR_USERNAME/sentiwiki_ai.git
cd sentiwiki_ai

# 1. Install backend deps
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# 2. Generate data (SentiWiki pipeline)
uv run python -m src.crawlers.scrape_sentiwiki_crawl4ai
uv run python scripts/data/enhance_sentiwiki.py
uv run python -m src.parsers.sentiwiki_chunker
uv run python -m src.db.populate_vectors

# 3. Start infra + API + frontend
docker compose -f deployment/docker/docker-compose.yml up -d qdrant prometheus grafana
cd src/api && uvicorn main:app --host 0.0.0.0 --port 8002 --reload
cd frontend && npm install && npm run dev
```

---

### 1️⃣ End-to-End Data Pipeline (SentiWiki)

Run these from the project root (`sentiwiki_ai/`):

```bash
# 1. Scrape SentiWiki with Crawl4AI (~5 min)
uv run python -m src.crawlers.scrape_sentiwiki_crawl4ai

# 2. Enhance markdown (clean + metadata, ~3 min)
uv run python scripts/data/enhance_sentiwiki.py

# 3. Chunk enhanced markdown for RAG (~2 min)
uv run python -m src.parsers.sentiwiki_chunker

# 4. Load chunks into Qdrant (~5 min)
uv run python -m src.db.populate_vectors
```

**What this gives you:**
- Scraped + cleaned SentiWiki markdown
- Chunked JSON files under `data/processed/sentiwiki_structured/`
- A populated Qdrant collection ready for retrieval

More context: see `data/README.md` ("Getting Started" section).

---

### 2️⃣ Core App Services

Once data is generated, you typically run:

```bash
# 1. Start Qdrant + monitoring (local stack)
docker compose -f deployment/docker/docker-compose.yml up -d qdrant prometheus grafana

# 2. Run the FastAPI backend (port 8002)
cd src/api
uvicorn main:app --host 0.0.0.0 --port 8002 --reload

# 3. Run the Next.js frontend (port 3000)
cd frontend
npm install
npm run dev
```

**Where to connect:**
- **Frontend (recommended):** `http://localhost:3000` – main chat UI to talk to the system
- **API:** `http://localhost:8002` – FastAPI backend (for programmatic/HTTP tests)
- **API docs:** `http://localhost:8002/docs` – Swagger UI where you can send test chat requests
- Qdrant UI: `http://localhost:6333/dashboard`

These commands mirror the **Quick Start → Local Development** section in `README.md`.

---

### 3️⃣ Crawlers & Data Enhancers

**SentiWiki crawler (Crawl4AI):**

```bash
# Default SentiWiki crawl
uv run python -m src.crawlers.scrape_sentiwiki_crawl4ai
```

Outputs under `data/sentiwiki_docs/`:
- `crawl4ai/` – raw JSON from Crawl4AI
- `markdown/` – initial markdown
- `pdfs/` – downloaded PDFs

**Enhance SentiWiki markdown:**

```bash
uv run python scripts/data/enhance_sentiwiki.py
```

For more options (custom folders, paths) see `scripts/README.md` → `data/enhance_sentiwiki.py`.

---

### 4️⃣ Testing Retrieval & RAG from CLI

**Test the retriever only:**

```bash
uv run python scripts/experiments/test_retriever.py -q "What are Sentinel-1 applications?" -k 5
```

**Test full RAG pipeline (retrieval + generation via LiteLLM):**

```bash
uv run python scripts/experiments/test_rag_litellm.py -q "What is Sentinel-1?" -k 5
```

These are useful to confirm your data + Qdrant + config are working before you touch the UI.

---

### 5️⃣ Evaluation Scripts (RAGAS)

**Main evaluation:**

```bash
uv run python scripts/evaluation/eval_ragas.py \
  --collection sentiwiki_index \
  --output results_ragas.csv \
  --limit 10 \
  --delay 10.0
```

**With latency breakdown:**

```bash
uv run python scripts/evaluation/eval_ragas_with_latency.py \
  --collection sentiwiki_index \
  --output results_with_latency.csv \
  --limit 10 \
  --delay 10.0
```

These scripts compute RAGAS metrics (faithfulness, context recall, etc.) and optionally detailed latency timings.

---

### 6️⃣ Helpful References

- `data/README.md` – **authoritative guide** to the data pipeline and SentiWiki-specific details
- `scripts/README.md` – full catalog of scripts, options, and example commands
- Root `README.md` → **Quick Start** – high-level flow for local dev and AWS deployment

