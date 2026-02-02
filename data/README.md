# Data Directory

This directory contains datasets used by the SentiWiki RAG system for development, testing, and deployment.

## Directory Structure

```
data/
├── README.md                    # This file
├── seed/                        # Sample data for quick testing ✅ Committed
├── sentiwiki_docs/              # Raw scraped data ⚠️ Committed (can be regenerated)
│   ├── crawl4ai/               # Raw JSON from Crawl4AI scraper
│   ├── markdown/               # Converted to markdown
│   └── markdown_enhanced/      # Cleaned and enhanced markdown
└── processed/                   # Processed and chunked data
    └── sentiwiki_structured/   # Ready for embedding ✅ Committed (Docker image)
```

## ⚠️ Legal Notice: SentiWiki Content Not Included

**IMPORTANT**: This repository does **NOT** include any SentiWiki content (scraped or processed data). SentiWiki content is copyrighted by ESA and cannot be redistributed without written authorization. See the main [README.md](../README.md#️-legal-disclaimer--usage-terms) for full legal disclaimer.

**You must generate all data locally** using the provided scripts. This ensures compliance with [ESA's Terms and Conditions](https://sentiwiki.copernicus.eu/web/terms-and-conditions).

## What's Committed vs Generated

### ✅ Committed to Repository

**`seed/README.md`** (documentation only)
- README file explaining seed data structure
- **Note**: Seed data JSON files are NOT committed (gitignored for ESA compliance)
- Users must generate seed data locally if needed for testing

### ❌ NOT Committed (Must Generate Locally)

**`seed/*.json`** (sample data files)
- Seed data JSON files for testing
- **Must be generated locally** - not included in repository (gitignored for ESA compliance)
- Only `seed/README.md` is committed

**`sentiwiki_docs/`** (~7MB)
- Raw scraped data in multiple formats
- **Must be generated locally** - not included in repository
- Run: `uv run python -m src.crawlers.scrape_sentiwiki_crawl4ai`

**`processed/sentiwiki_structured/`** (~5MB, 66 files)
- Fully processed and chunked documents ready for vector embedding
- **Must be generated locally** - not included in repository
- Run the full pipeline (see "Getting Started" below)

### ❌ Generated Locally (Not Committed)

The following are created when you run the data pipeline but are gitignored:

- `data/raw/` - Other scraped sources
- `data/embeddings/` - Vector embeddings cache

## Getting Started

### Option 1: Generate Data Locally (Required - 15 minutes)

**You must generate the data locally** as SentiWiki content is not included in this repository.

```bash
# 1. Scrape raw data from SentiWiki (~5 min)
uv run python -m src.crawlers.scrape_sentiwiki_crawl4ai

# 2. Enhance markdown (clean, extract metadata) (~3 min)
uv run python scripts/data/enhance_sentiwiki.py

# 3. Chunk documents to JSON (~2 min)
uv run python -m src.parsers.sentiwiki_chunker

# 4. Load into Qdrant (~5 min)
uv run python -m src.db.populate_vectors

# 5. Start services
cd deployment/docker && docker compose up -d
```

**What happens:**
- You generate all data locally (compliant with ESA terms)
- Qdrant container starts
- API loads your locally-generated documents
- Generates embeddings on first query
- Ready to use

### Option 2: Regenerate Data from Scratch (Full Pipeline - 15 minutes)

If you want to modify scraping or processing logic:

```bash
# 1. Scrape raw data from SentiWiki (~5 min)
uv run python -m src.crawlers.scrape_sentiwiki_crawl4ai

# 2. Enhance markdown (clean, extract metadata) (~3 min)
uv run python scripts/data/enhance_sentiwiki.py

# 3. Chunk documents to JSON (~2 min)
uv run python -m src.parsers.sentiwiki_chunker

# 4. Load into Qdrant (~5 min)
uv run python -m src.db.populate_vectors
```

**What gets created:**
```
data/
├── sentiwiki_docs/
│   ├── crawl4ai/              # Raw scraped JSON (Step 1)
│   ├── markdown/              # Initial conversion (Step 1)
│   └── markdown_enhanced/     # Cleaned markdown (Step 2)
└── processed/
    └── sentiwiki_structured/  # Chunked for RAG (Step 3)
```

### Option 3: Test with Seed Data Only (Testing - Requires Local Generation)

**Note**: Seed data files are not committed to the repository. You must generate them locally first.

```bash
# Generate seed data locally (if needed)
# Seed data generation scripts would go here

# Then use seed data
export USE_SEED_DATA=true
docker compose up -d
```

**Use cases:**
- Running tests in GitHub Actions (with locally generated seed data)
- Quick sanity checks
- Demonstrating the system without full dataset

**Important**: Seed data JSON files are gitignored to maintain ESA copyright compliance. Only the `seed/README.md` documentation file is committed.

## Data Formats

### Raw Scraped Data (`sentiwiki_docs/crawl4ai/*.json`)

```json
{
  "url": "https://sentiwiki.copernicus.eu/web/sentinel-2",
  "title": "Sentinel-2",
  "markdown": "# Sentinel-2\n\nSentinel-2 is a wide-swath...",
  "metadata": {
    "crawled_at": "2024-01-15T10:30:00Z"
  }
}
```

### Processed Data (`processed/sentiwiki_structured/*.json`)

```json
{
  "chunks": [
    {
      "text": "Sentinel-2 carries the Multispectral Instrument (MSI)...",
      "metadata": {
        "source_url": "https://sentiwiki.copernicus.eu/web/sentinel-2",
        "mission": "sentinel-2",
        "chunk_id": "sentinel-2_chunk_0",
        "chunk_index": 0,
        "total_chunks": 15
      }
    }
  ]
}
```

## Dataset Statistics

| Dataset | Files | Size | Documents | Chunks | Use Case | Committed? |
|---------|-------|------|-----------|--------|----------|------------|
| **seed/** | 3 | ~20KB | 3 | ~15 | Testing, CI/CD | ❌ No (gitignored) |
| **sentiwiki_structured/** | 66 | ~5MB | 66 | ~2,500 | Production, Docker | ❌ No (gitignored) |
| **Full (all missions)** | 100+ | ~15MB | 100+ | ~5,000 | Extended knowledge base | ❌ No (gitignored) |

**Note**: All data files (JSON) are gitignored for ESA copyright compliance. Only README.md files are committed.

## Updating the Dataset

### Adding New Sentinel Missions

1. Add URLs to `src/crawlers/targets.py`:
```python
SENTIWIKI_URLS = [
    "https://sentiwiki.copernicus.eu/web/sentinel-4",  # New mission
    # ...
]
```

2. Run the scraping pipeline:
```bash
uv run python scripts/data/scrape_sentiwiki.py --missions sentinel-4
```

3. Process and load:
```bash
uv run python scripts/data/enhance_sentiwiki.py
uv run python scripts/pipeline/load_to_qdrant.py --collection sentiwiki_index
```

### Refreshing Existing Data

```bash
# Re-scrape all data (overwrites existing)
uv run python scripts/data/scrape_sentiwiki.py --force

# Re-process with new chunking strategy
uv run python scripts/data/enhance_sentiwiki.py --chunk-size 800
```

## Storage Considerations

### Why is processed data NOT committed?

**Legal Compliance:** SentiWiki content is copyrighted by ESA and cannot be redistributed without written authorization. All data files (including processed data) are gitignored to maintain compliance.

**First-time users must:**
1. Wait 5 minutes for scraping
2. Wait 3 minutes for processing
3. Wait 5 minutes for vector indexing
4. = 13 minutes before they can try a single query

**Alternative for AWS deployment:** Use the upload endpoint to upload locally-generated data to your deployed system (see "Uploading Data to AWS Deployment" section above).

### Why Data is NOT Committed

**Legal Requirement:** ESA copyright compliance requires that SentiWiki content cannot be redistributed. All data files are gitignored.

**Users must generate data locally:**
- Ensures compliance with ESA Terms and Conditions
- Users take responsibility for data generation
- No copyright issues with repository

**For AWS deployment:** Users can upload locally-generated data via the `/api/v1/upload-and-index` endpoint (see "Uploading Data to AWS Deployment" section above).

## Data Versioning

Processed data is versioned with the code because:
- Chunking strategy may change
- Metadata schema evolves
- Ensures Docker image matches code version

If you modify chunking logic in `src/parsers/`, regenerate data:

```bash
# After changing chunking code
uv run python scripts/data/enhance_sentiwiki.py
git add data/processed/sentiwiki_structured/
git commit -m "Update chunked data for new chunking strategy"
```

## Data Governance

### Sources
- **SentiWiki:** https://sentiwiki.copernicus.eu
- **License:** Public domain (ESA/EU Copernicus program)
- **Usage:** Educational and research purposes

### Privacy
- No personal data collected
- No user tracking
- All data is publicly available documentation

### Attribution
When using this dataset, please cite:
```
ESA Sentinel Online. (2024). SentiWiki - Sentinel Missions Guide.
Retrieved from https://sentiwiki.copernicus.eu
```

## Uploading Data to AWS Deployment

**For AWS-deployed systems**, you can upload your locally-generated data using the FastAPI upload endpoint. This maintains legal compliance while allowing you to populate your production Qdrant collection.

### Step 1: Generate Data Locally

```bash
# Generate processed data locally (as required for legal compliance)
uv run python -m src.crawlers.scrape_sentiwiki_crawl4ai
uv run python scripts/data/enhance_sentiwiki.py
uv run python -m src.parsers.sentiwiki_chunker
```

### Step 2: Create Zip Archive

```bash
# Create a zip file of the processed JSON documents
cd data/processed
zip -r sentiwiki_structured.zip sentiwiki_structured/
```

### Step 3: Upload via API

```bash
# Upload to your deployed AWS API
curl -X POST "https://your-api-domain/api/v1/upload-and-index" \
  -F "file=@sentiwiki_structured.zip" \
  -F "collection=sentiwiki_index" \
  -F "recreate=true"
```

**Response:**
```json
{
  "job_id": "abc123-def456-...",
  "status": "pending",
  "message": "Upload received (66 JSON files). Indexing started...",
  "input_dir": "/tmp/upload_abc123/extracted/sentiwiki_structured",
  "collection_name": "sentiwiki_index"
}
```

### Step 4: Track Progress

```bash
# Check indexing status
curl "https://your-api-domain/api/v1/index/status/{job_id}"
```

**Response:**
```json
{
  "job_id": "abc123-def456-...",
  "status": "running",
  "progress": 45.0,
  "message": "Generating embeddings...",
  "result": null
}
```

### Using Python Client

```python
import requests

# Upload file
with open("data/processed/sentiwiki_structured.zip", "rb") as f:
    response = requests.post(
        "https://your-api-domain/api/v1/upload-and-index",
        files={"file": f},
        data={
            "collection": "sentiwiki_index",
            "recreate": "true"
        }
    )
    
job_id = response.json()["job_id"]
print(f"Upload started. Job ID: {job_id}")

# Check status
status_response = requests.get(
    f"https://your-api-domain/api/v1/index/status/{job_id}"
)
print(status_response.json())
```

### Frontend Integration

You can also add a file upload button to your frontend:

```typescript
// Example: Add upload button to your Next.js frontend
const handleUpload = async (file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('collection', 'sentiwiki_index');
  formData.append('recreate', 'true');
  
  const response = await fetch('/api/v1/upload-and-index', {
    method: 'POST',
    body: formData,
  });
  
  const { job_id } = await response.json();
  // Poll for status using job_id
};
```

**Benefits:**
- ✅ Maintains legal compliance (data generated locally, not in repo)
- ✅ No need to rebuild Docker images
- ✅ Works with AWS ECS deployment
- ✅ Automatic cleanup of temporary files
- ✅ Progress tracking via job_id

## Troubleshooting

### "No documents found in Qdrant"

Check if data was loaded:
```bash
# Verify files exist
ls -lh data/processed/sentiwiki_structured/

# Check Qdrant collections
curl http://localhost:6333/collections
```

### "Processing takes too long"

Use parallel processing:
```bash
uv run python scripts/data/enhance_sentiwiki.py --workers 4
```

### "Out of disk space"

Clear generated data (keeps committed data):
```bash
# Remove raw scraped data
rm -rf data/sentiwiki_docs/

# Regenerate from processed data if needed
# (processed data contains all information)
```

## Questions?

See also:
- [SentiWiki Complete Pipeline](../docs/architecture/data_pipeline/SENTIWIKI_COMPLETE_PIPELINE.md)
- [Scripts Overview](../scripts/README.md)
- [Chunking Strategy](../docs/architecture/data_pipeline/SENTIWIKI_CHUNKING_STRATEGY.md)
