# Scripts Directory

This directory contains utility scripts for development, testing, evaluation, and data processing.

## Production Utilities

These scripts are used in production workflows:

### `setup/preload_models.py`
Preloads ML models during Docker build for faster startup.

**Usage:**
```bash
# Called automatically during Docker build (see Dockerfile)
python scripts/preload_models.py
```

**Note:** This script reads `config/settings.yaml` to determine which models to pre-download.

### `data/enhance_sentiwiki.py`
Enhances SentiWiki markdown files by cleaning, formatting, and adding metadata for better RAG performance.

**Usage:**
```bash
# Use default paths (data/sentiwiki_docs/)
uv run python scripts/data/enhance_sentiwiki.py

# Custom sub-folder
uv run python scripts/data/enhance_sentiwiki.py --sub-folder my_sentiwiki_data

# Override specific paths
uv run python scripts/data/enhance_sentiwiki.py \
    --json-dir data/custom/crawl4ai \
    --md-dir data/custom/markdown \
    --output-dir data/custom/markdown_enhanced
```

**What it does:**
- Removes navigation menus and boilerplate
- Cleans up headings and links
- Adds enhanced metadata (document type, mission, word count)
- Normalizes metadata (mission: S3, S5P, etc.)
- Includes table of contents
- Normalizes structure for better RAG

## Testing Scripts

Scripts for testing and validation:

### `experiments/test_retriever.py`
Tests the retrieval system directly from the command line.

**Usage:**
```bash
# Single query
uv run python scripts/experiments/test_retriever.py -q "What are Sentinel-1 applications?" -k 5

# Interactive mode
uv run python scripts/experiments/test_retriever.py -i

# With options
uv run python scripts/experiments/test_retriever.py \
    -q "SAR imaging" \
    -k 10 \
    --no-hybrid \
    --no-reranking \
    --no-filtering
```

### `experiments/test_rag_litellm.py`
Tests the full RAG pipeline (retrieval + generation) with LiteLLM.

**Usage:**
```bash
# Single query
uv run python scripts/experiments/test_rag_litellm.py -q "What is Sentinel-1?" -k 5

# Interactive mode
uv run python scripts/experiments/test_rag_litellm.py -i

# With custom model and collection
uv run python scripts/experiments/test_rag_litellm.py \
    -q "What is the resolution of Sentinel-2?" \
    --model claude-3-5-sonnet-20241022 \
    --collection sentiwiki_index \
    --top-k 10
```

### `experiments/test_metadata_filtering.py`
Tests metadata filtering functionality and query analysis.

**Usage:**
```bash
uv run python scripts/experiments/test_metadata_filtering.py
```

**What it tests:**
- Query analysis (extracting filters from queries)
- Metadata extraction
- Retrieval with smart filtering
- Boost factors and reasons

## Evaluation Scripts

Scripts for evaluating system performance:

### `evaluation/eval_ragas.py`
Primary RAGAS evaluation framework. Evaluates RAG system using standard metrics:
- Context Precision
- Context Recall
- Faithfulness
- Answer Relevancy

**Usage:**
```bash
# Basic evaluation
uv run python scripts/evaluation/eval_ragas.py \
    --collection sentiwiki_index \
    --output results_evaluacion_ragas.csv \
    --limit 10 \
    --delay 10.0

# With options
uv run python scripts/evaluation/eval_ragas.py \
    --collection sentiwiki_index \
    --top-k 15 \
    --no-hybrid \
    --no-reranking \
    --no-filtering \
    --output results_no_hybrid.csv \
    --limit 20
```

**Options:**
- `--top-k`: Number of documents to retrieve (default: 10)
- `--collection`: Collection name (default: from config)
- `--model`: LLM model name (default: from config)
- `--no-hybrid`: Disable hybrid search
- `--no-reranking`: Disable reranking
- `--no-filtering`: Disable metadata filtering
- `--output`: Output CSV file path
- `--limit`: Limit number of questions to evaluate
- `--delay`: Delay between requests in seconds (default: 10.0)
- `--max-retries`: Max retries for rate limit errors (default: 3)

### `evaluation/eval_ragas_with_latency.py`
Extends `eval_ragas.py` to measure latency breakdown for each component:
- Embedding time
- Retrieval time
- Generation time
- Total time

**Usage:**
```bash
uv run python scripts/evaluation/eval_ragas_with_latency.py \
    --collection sentiwiki_index \
    --output results_with_latency.csv \
    --limit 10 \
    --delay 10.0
```

**Output:** CSV file with RAGAS metrics plus latency columns (`embedding_ms`, `retrieval_ms`, `generation_ms`, `total_ms`).

## Experimental/Development Scripts

Scripts used for experimentation and development:

### `experiments/compare_filtering.py`
Compares retrieval with and without smart metadata filtering.

**Usage:**
```bash
uv run python scripts/experiments/compare_filtering.py
```

**What it does:**
- Runs the same query with filtering enabled and disabled
- Compares metadata characteristics (shall/should requirements, requirement types)
- Shows boost factors and reasons
- Displays improvement metrics

**Note:** The test query is hardcoded in the script. Modify `main()` function to test different queries.

## Data Processing Scripts

Scripts for processing data (optional depending on use case):

### `data/scrape_dataspace.py`
Scrapes Copernicus Data Space documentation using Crawl4AI.

**Usage:**
```bash
# Use default settings
uv run python scripts/data/scrape_dataspace.py

# Start from specific page
uv run python scripts/data/scrape_dataspace.py \
    --start-url https://documentation.dataspace.copernicus.eu/Registration.html

# Custom limits
uv run python scripts/scrape_dataspace.py \
    --sub-folder my_dataspace_data \
    --max-depth 3 \
    --max-pages 500

# Skip PDF downloads
uv run python scripts/data/scrape_dataspace.py --no-download-pdfs
```

**Output directories** (under `data/{sub_folder}/`):
- `crawl4ai/`: JSON files with complete page data
- `markdown/`: RAG-optimized markdown files
- `pdfs/`: Downloaded PDF files (if enabled)

### `data/enhance_dataspace.py`
Enhances DataSpace markdown files for better RAG performance (similar to `enhance_sentiwiki.py` but DataSpace-specific).

**Usage:**
```bash
# Use default paths (data/dataspace_docs/)
uv run python scripts/data/enhance_dataspace.py

# Custom sub-folder
uv run python scripts/data/enhance_dataspace.py --sub-folder my_dataspace_data

# Override specific paths
uv run python scripts/data/enhance_dataspace.py \
    --json-dir data/custom/crawl4ai \
    --md-dir data/custom/markdown \
    --output-dir data/custom/markdown_enhanced
```

**What it does:**
- Removes DataSpace breadcrumbs and navigation menus
- Cleans up headings and links
- Adds enhanced metadata with DataSpace-specific document types
- Normalizes metadata (mission: S3, S5P, etc.)
- Includes table of contents
- Normalizes structure for better RAG

## General Usage Notes

### Running Scripts

Most scripts use Click for CLI and support `--help`:
```bash
uv run python scripts/evaluation/eval_ragas.py --help
uv run python scripts/experiments/test_retriever.py --help
```

### Requirements

- **Scripts that import from `src/`** should be run from the project root
- **Some scripts require environment variables** (API keys, etc.):
  - `ANTHROPIC_API_KEY` for evaluation scripts
  - `QDRANT_URL` and `QDRANT_API_KEY` for retrieval scripts
- **Evaluation scripts** may take significant time to run (especially with rate limiting delays)

### Common Patterns

**Testing retrieval:**
```bash
uv run python scripts/experiments/test_retriever.py -q "your query" -k 5
```

**Evaluating system:**
```bash
uv run python scripts/evaluation/eval_ragas.py --limit 10 --delay 10.0
```

**Processing data:**
```bash
uv run python scripts/data/enhance_sentiwiki.py
```

## Script Dependencies

Some scripts depend on others:
- `eval_ragas_with_latency.py` imports from `eval_ragas.py` (GOLDEN_DATASET, helper functions)
- `compare_filtering.py` is standalone but uses the same retriever as other scripts

## Archive

The following scripts have been archived or are no longer actively used:
- `simple_evaluator.py` - Superseded by `eval_ragas.py`
- `compare_embedding_models.py` - No longer needed (BGE-small decision made)
- `create_test_collection_bge_small.py` - No longer needed (BGE-small decision made)

See `scripts/EMBEDDING_EXPERIMENT_GUIDE.md` for historical reference on embedding experiments.
