"""Data pipeline orchestrator for SentiWiki scraping, chunking, and ingestion."""

from __future__ import annotations

import asyncio
import os
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from src.models.pipeline import PipelineStatus, PipelineStep
from src.utils.config import get_settings

# Increase HuggingFace timeout for large model downloads (default is 10s)
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "300")


class DataPipeline:
    """Orchestrates the full data pipeline: scrape -> chunk -> embed -> ingest."""

    _instance: Optional["DataPipeline"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "DataPipeline":
        """Singleton pattern to ensure only one pipeline instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self.settings = get_settings()
        self._jobs: Dict[str, PipelineStatus] = {}
        self._current_job_id: Optional[str] = None
        self._running = False
        self._initialized = True

        logger.info("DataPipeline initialized")

    @property
    def is_running(self) -> bool:
        """Check if a pipeline is currently running."""
        return self._running

    def get_job_status(self, job_id: str) -> Optional[PipelineStatus]:
        """Get status of a specific job."""
        return self._jobs.get(job_id)

    def get_all_jobs(self) -> List[Dict[str, Any]]:
        """Get all job statuses."""
        return [job.to_dict() for job in self._jobs.values()]

    def get_job_logs(self, job_id: str, tail: int = 50) -> List[str]:
        """Get logs for a specific job."""
        job = self._jobs.get(job_id)
        if job:
            return job.logs[-tail:]
        return []

    def _log(self, job_id: str, message: str, level: str = "info") -> None:
        """Add log entry to job and loguru."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"

        if job_id in self._jobs:
            self._jobs[job_id].logs.append(log_entry)

        log_func = getattr(logger, level, logger.info)
        log_func(f"[Pipeline {job_id[:8]}] {message}")

    async def run_pipeline(
        self,
        job_id: str,
        max_depth: int = 2,
        max_pages: int = 200,
        download_pdfs: bool = False,
        recreate_collection: bool = True,
        collection_name: str = "sentiwiki_index",
        embedding_model: str = "BAAI/bge-large-en-v1.5",
    ) -> None:
        """Run the full pipeline asynchronously.

        Args:
            job_id: Unique job identifier
            max_depth: Maximum crawl depth for scraping
            max_pages: Maximum number of pages to scrape
            download_pdfs: Whether to download PDFs during scraping
            recreate_collection: Whether to recreate Qdrant collection
            collection_name: Name of the Qdrant collection
            embedding_model: HuggingFace model for embeddings
        """
        job = self._jobs[job_id]
        job.status = "running"
        job.started_at = datetime.now()

        try:
            # Step 1: Scraping (30% of total progress)
            await self._run_scraping(
                job_id, max_depth, max_pages, download_pdfs
            )

            # Step 2: Enhancement (15% of total progress)
            await self._run_enhancement(job_id)

            # Step 3: Chunking (15% of total progress)
            await self._run_chunking(job_id)

            # Step 4: Embedding & Ingestion (40% of total progress)
            await self._run_ingestion(
                job_id, recreate_collection, collection_name, embedding_model
            )

            # Complete
            job.current_step = PipelineStep.COMPLETED
            job.status = "completed"
            job.progress = 100.0
            job.completed_at = datetime.now()
            self._log(job_id, "Pipeline completed successfully!", "success")

        except Exception as e:
            job.current_step = PipelineStep.FAILED
            job.status = "failed"
            job.error = str(e)
            job.completed_at = datetime.now()
            self._log(job_id, f"Pipeline failed: {e}", "error")
            raise
        finally:
            self._running = False
            self._current_job_id = None

    async def _run_scraping(
        self,
        job_id: str,
        max_depth: int,
        max_pages: int,
        download_pdfs: bool,
    ) -> None:
        """Run the scraping step."""
        job = self._jobs[job_id]
        job.current_step = PipelineStep.SCRAPING
        self._log(job_id, f"Starting scraping (depth={max_depth}, max_pages={max_pages})")

        from src.crawlers.scrape_sentiwiki_crawl4ai import SentiWikiCrawl4AIScraper

        scraper = SentiWikiCrawl4AIScraper()

        # Run scraping
        await scraper.scrape_all(
            max_depth=max_depth,
            max_pages=max_pages,
            download_pdfs=download_pdfs,
        )

        # Update stats
        job.stats["pages_scraped"] = max_pages  # Approximate
        job.stats["markdown_dir"] = str(scraper.markdown_dir)
        job.stats["json_dir"] = str(scraper.output_dir)
        job.steps_completed.append("scraping")
        job.progress = 30.0
        self._log(job_id, f"Scraping completed. Output: {scraper.markdown_dir}")

    async def _run_enhancement(self, job_id: str) -> None:
        """Run the markdown enhancement step."""
        job = self._jobs[job_id]
        job.current_step = PipelineStep.ENHANCING
        self._log(job_id, "Starting markdown enhancement...")

        from src.utils.markdown_cleaner_sentiwiki import MarkdownCleaner

        settings = get_settings()
        json_dir = settings.data_dir / "sentiwiki_docs" / "crawl4ai"
        md_dir = settings.data_dir / "sentiwiki_docs" / "markdown"
        output_dir = settings.data_dir / "sentiwiki_docs" / "markdown_enhanced"
        output_dir.mkdir(parents=True, exist_ok=True)

        cleaner = MarkdownCleaner()

        # Get markdown files
        md_files = [f for f in md_dir.glob("*.md") if f.name != "README.md"]
        self._log(job_id, f"Found {len(md_files)} markdown files to enhance")

        success_count = 0
        for i, md_file in enumerate(md_files):
            json_file = json_dir / f"{md_file.stem}.json"

            if not json_file.exists():
                continue

            try:
                # Load JSON metadata
                import json
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                if not data.get('success'):
                    continue

                # Load existing markdown
                with open(md_file, 'r', encoding='utf-8') as f:
                    markdown_content = f.read()

                # Remove existing frontmatter if present
                if markdown_content.startswith('---'):
                    parts = markdown_content.split('---', 2)
                    if len(parts) >= 3:
                        markdown_content = parts[2].strip()

                # Create enhanced markdown
                enhanced_md = cleaner.create_rag_optimized_markdown(
                    markdown=data.get('markdown', markdown_content),
                    metadata={
                        'title': data.get('title', ''),
                        'url': data.get('url', ''),
                        'description': data.get('description', ''),
                        'keywords': data.get('keywords', ''),
                    },
                    include_toc=True
                )

                # Save enhanced version
                output_path = output_dir / md_file.name
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(enhanced_md)

                success_count += 1

            except Exception as e:
                self._log(job_id, f"Error enhancing {md_file.name}: {e}", "warning")

            # Update progress (30% to 45%)
            job.progress = 30.0 + (15.0 * (i + 1) / len(md_files))

        job.stats["files_enhanced"] = success_count
        job.stats["enhanced_dir"] = str(output_dir)
        job.steps_completed.append("enhancing")
        job.progress = 45.0
        self._log(job_id, f"Enhancement completed. Enhanced {success_count} files")

    async def _run_chunking(self, job_id: str) -> None:
        """Run the chunking step."""
        job = self._jobs[job_id]
        job.current_step = PipelineStep.CHUNKING
        self._log(job_id, "Starting chunking...")

        from src.parsers.sentiwiki_chunker import StructuredMarkdownChunker

        # Use enhanced markdown directory (output from enhancement step)
        settings = get_settings()
        markdown_dir = settings.data_dir / "sentiwiki_docs" / "markdown_enhanced"
        output_dir = settings.data_dir / "processed" / "sentiwiki_structured"

        # Fallback to raw markdown if enhanced doesn't exist
        if not markdown_dir.exists() or not list(markdown_dir.glob("*.md")):
            markdown_dir = settings.data_dir / "sentiwiki_docs" / "markdown"
            self._log(job_id, "Using raw markdown (enhanced not available)", "warning")

        chunker = StructuredMarkdownChunker(
            chunk_size=2000,
            chunk_overlap=200,
            output_dir=output_dir,
        )

        # Process all markdown files
        markdown_files = [f for f in markdown_dir.glob("*.md") if f.name != "README.md"]
        self._log(job_id, f"Found {len(markdown_files)} markdown files to chunk")

        total_chunks = 0
        for i, md_file in enumerate(markdown_files):
            result = chunker.process_markdown(md_file)
            total_chunks += len(result.get("chunks", []))

            # Update progress (45% to 60%)
            job.progress = 45.0 + (15.0 * (i + 1) / len(markdown_files))

        job.stats["total_chunks"] = total_chunks
        job.stats["chunks_dir"] = str(output_dir)
        job.steps_completed.append("chunking")
        job.progress = 60.0
        self._log(job_id, f"Chunking completed. Total chunks: {total_chunks}")

    async def _run_ingestion(
        self,
        job_id: str,
        recreate_collection: bool,
        collection_name: str,
        embedding_model: str,
    ) -> None:
        """Run the embedding and ingestion step."""
        job = self._jobs[job_id]
        job.current_step = PipelineStep.EMBEDDING
        self._log(job_id, f"Starting embedding with model: {embedding_model}")

        from src.db.populate_vectors import VectorPopulator

        settings = get_settings()
        input_dir = settings.data_dir / "processed" / "sentiwiki_structured"

        # Run in thread to avoid blocking (embeddings are CPU intensive)
        def populate_sync():
            populator = VectorPopulator(
                input_dir=input_dir,
                collection_name=collection_name,
                embedding_provider="huggingface",
                embedding_model=embedding_model,
                batch_size=32,
                distance="Cosine",
                normalize_embeddings=True,
            )
            populator.populate(recreate=recreate_collection)
            return populator.qdrant.get_collection_info()

        # Run in executor to not block event loop
        loop = asyncio.get_event_loop()
        collection_info = await loop.run_in_executor(None, populate_sync)

        job.current_step = PipelineStep.INGESTION
        job.stats["collection_name"] = collection_name
        job.stats["collection_info"] = collection_info
        job.steps_completed.append("embedding")
        job.steps_completed.append("ingestion")
        job.progress = 100.0
        self._log(job_id, f"Ingestion completed. Collection: {collection_name}")

    def start_pipeline(
        self,
        max_depth: int = 2,
        max_pages: int = 200,
        download_pdfs: bool = False,
        recreate_collection: bool = True,
        collection_name: str = "sentiwiki_index",
        embedding_model: str = "BAAI/bge-large-en-v1.5",
    ) -> str:
        """Start the pipeline in background.

        Returns:
            job_id: Unique identifier for tracking the job
        """
        if self._running:
            raise RuntimeError(
                f"Pipeline already running (job_id: {self._current_job_id}). "
                "Wait for it to complete or check status."
            )

        job_id = str(uuid.uuid4())
        self._jobs[job_id] = PipelineStatus(job_id=job_id)
        self._current_job_id = job_id
        self._running = True

        self._log(job_id, "Pipeline job created")

        # Start async task in background
        async def run_in_background():
            try:
                await self.run_pipeline(
                    job_id=job_id,
                    max_depth=max_depth,
                    max_pages=max_pages,
                    download_pdfs=download_pdfs,
                    recreate_collection=recreate_collection,
                    collection_name=collection_name,
                    embedding_model=embedding_model,
                )
            except Exception as e:
                logger.error(f"Pipeline failed: {e}")

        # Schedule the coroutine
        asyncio.create_task(run_in_background())

        return job_id


# Global pipeline instance
_pipeline: Optional[DataPipeline] = None


def get_pipeline() -> DataPipeline:
    """Get the global pipeline instance."""
    global _pipeline
    if _pipeline is None:
        _pipeline = DataPipeline()
    return _pipeline
