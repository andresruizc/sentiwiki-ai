## 🎯 Adversarial Evaluation Test Set

This document describes the **adversarial RAG test set** used to evaluate SentiWiki AI.

The goal of this test set is to **stress‑test retrieval and answer generation** with queries that are:

- **Tricky**: ambiguous wording, edge cases, or easily-confused concepts  
- **Multi‑hop**: require combining information from multiple documents/sections  
- **Comparative**: e.g. compare Sentinel‑1 vs Sentinel‑2 capabilities  
- **Failure‑seeking**: designed to expose hallucinations or shallow retrieval

---

## 📂 Where the adversarial test lives

- **Test data & prompts**:  
  - Stored alongside the evaluation scripts and helpers in:  
    - `scripts/evaluation/` (evaluation code)  
    - `scripts/experiments/` (retrieval experiments, filtering, etc.)
- **Key scripts that use it**:
  - `scripts/evaluation/eval_ragas.py`
  - `scripts/evaluation/eval_ragas_with_latency.py`
  - `scripts/experiments/test_retriever.py`
  - `scripts/experiments/compare_filtering.py`

These scripts orchestrate:

- Query generation / loading (including adversarial queries)
- Running retrieval + answer generation
- Computing **RAGAS metrics** (faithfulness, recall, relevancy, precision)
- Optionally measuring **latency** end‑to‑end

> **Note**: The actual question/answer pairs and logs are **not** committed to the repo if they contain SentiWiki content, to stay compliant with ESA’s terms. You should run the evaluation locally to regenerate metrics.

---

## 🧪 How to run the adversarial evaluation

### Prerequisites

**Minimal setup required!** The evaluation script automatically:
- **Uses local embeddings**: Same embedding model as your Qdrant collection (e.g., `BAAI/bge-small-en-v1.5`) for accurate semantic similarity calculations. These work for **Context Precision** and **Context Recall** metrics without any API keys.
- **LLM API key required**: An LLM API key (e.g., `ANTHROPIC_API_KEY`) is **required** for **Faithfulness** and **Answer Relevancy** metrics, which use LLM-based evaluation. The script automatically detects and reuses your API key from environment variables or settings.
- **Configures via settings.yaml**: LLM model for evaluation is configured in `config/settings.yaml` under `llm.eval_llm`

### Running the Evaluation

From the project root:

**Option 1: Using Makefile (Recommended)**
```bash
# Quick RAGAS evaluation (uses default collection: sentiwiki_index, limit: 10)
make eval-ragas

# RAGAS evaluation with latency measurement
make eval-ragas-latency
```

**Option 2: Direct Python commands**
```bash
# Small adversarial RAGAS run (example collection name: sentiwiki_index)
uv run python scripts/evaluation/eval_ragas.py \
  --collection sentiwiki_index \
  --limit 20 \
  --delay 10.0

# Adversarial RAGAS + latency measurement
uv run python scripts/evaluation/eval_ragas_with_latency.py \
  --collection sentiwiki_index \
  --limit 20 \
  --delay 10.0
```

> **Note**: The Makefile commands use default parameters. For custom options (different collection, limit, delay), use the direct Python commands above.
> 
> Adjust `--collection`, `--limit`, and `--delay` according to your local setup.

### Configuration

**Embeddings**: The script automatically uses the same embedding model as your retriever (detected from your Qdrant collection). No configuration needed.

**LLM for Evaluation**: Configure in `config/settings.yaml`:

```yaml
llm:
  eval_llm:
    provider: "anthropic"
    model: "claude-3-haiku-20240307"
    temperature: 0.0
    max_tokens: 1024
```

The script will automatically use your `ANTHROPIC_API_KEY` (or other provider key) from environment variables. **Note**: The LLM API key is required for **Faithfulness** and **Answer Relevancy** metrics. If no API key is provided, only **Context Precision** and **Context Recall** will be computed (which use local embeddings only).

### Golden Dataset

The evaluation uses a **golden dataset** of adversarial questions stored directly in `scripts/evaluation/eval_ragas.py` as the `GOLDEN_DATASET` variable. This dataset includes:

- **Hallucination checks**: Questions designed to catch false information (e.g., "What is the swath width of Sentinel-2 SAR?" — trick question, Sentinel-2 doesn't have SAR)
- **Temporal reasoning**: Questions about mission status and launch dates
- **Mission-specific queries**: Technical questions about Sentinel-1, Sentinel-2, Sentinel-3, etc.
- **Cross-mission comparisons**: Questions requiring knowledge from multiple missions
- **Negative constraints**: Questions testing the system's ability to correctly deny non-existent capabilities

You can **view and modify** the questions by editing the `GOLDEN_DATASET` list in `scripts/evaluation/eval_ragas.py`. Each question includes:
- `question`: The query to test
- `ground_truth`: The expected answer
- `difficulty`: Hard/Medium difficulty level
- `capability`: Type of test (e.g., "Hallucination Check", "Multi-hop Reasoning")
- `filtering_test`: Category for analysis (e.g., "negative_constraint", "cross_mission_comparison")

### Results

Results (scores and logs) are written to:

- `scripts/evaluation_results/` (gitignored)  
- Additional experiment‑specific output paths referenced inside each script.

---

## 📊 Reported metrics

The evaluation focuses on:

- **Context Precision** — how much of the retrieved context is truly relevant? *(Uses local embeddings, no API key needed)*
- **Context Recall** — does retrieval bring in the right information? *(Uses local embeddings, no API key needed)*
- **Faithfulness** — are answers grounded in retrieved context? *(Requires LLM API key)*
- **Answer Relevancy** — does the answer actually address the question? *(Requires LLM API key)*

**Note**: If no LLM API key is provided, only **Context Precision** and **Context Recall** will be computed. These metrics use local embeddings and don't require any API calls.

These are aggregated over the adversarial question set and summarized in the
**"Evaluation Results: RAGAS Metrics on Adversarial Queries"** section of the main `README.md`.


