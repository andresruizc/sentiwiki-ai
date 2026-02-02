"""FastAPI router for data pipeline endpoints."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.pipeline.data_pipeline import get_pipeline, PipelineStatus


router = APIRouter(prefix="/admin/pipeline", tags=["Pipeline"])


# Request/Response models
class PipelineStartRequest(BaseModel):
    """Request to start the data pipeline."""

    max_depth: int = Field(default=2, ge=1, le=5, description="Maximum crawl depth")
    max_pages: int = Field(default=200, ge=1, le=1000, description="Maximum pages to scrape")
    download_pdfs: bool = Field(default=False, description="Download PDF files")
    recreate_collection: bool = Field(default=True, description="Recreate Qdrant collection")
    collection_name: str = Field(default="sentiwiki_index", description="Qdrant collection name")
    embedding_model: str = Field(
        default="BAAI/bge-large-en-v1.5",
        description="HuggingFace embedding model"
    )


class PipelineStartResponse(BaseModel):
    """Response after starting the pipeline."""

    job_id: str
    status: str
    message: str


class PipelineStatusResponse(BaseModel):
    """Pipeline job status response."""

    job_id: str
    status: str
    current_step: Optional[str]
    progress: str
    started_at: Optional[str]
    completed_at: Optional[str]
    duration_seconds: Optional[float]
    error: Optional[str]
    steps_completed: List[str]
    stats: Dict[str, Any]


class PipelineLogsResponse(BaseModel):
    """Pipeline job logs response."""

    job_id: str
    logs: List[str]
    total_lines: int


# Endpoints
@router.post("/run", response_model=PipelineStartResponse)
async def start_pipeline(request: PipelineStartRequest) -> PipelineStartResponse:
    """Start the data pipeline (scrape -> enhance -> chunk -> ingest).

    This endpoint triggers the full data pipeline in background:
    1. **Scraping**: Crawls SentiWiki and saves markdown + JSON
    2. **Enhancement**: Cleans and optimizes markdown for RAG
    3. **Chunking**: Splits documents into smaller chunks with metadata
    4. **Embedding**: Generates embeddings using the specified model
    5. **Ingestion**: Inserts vectors into Qdrant

    The pipeline runs asynchronously. Use `/status/{job_id}` to track progress.

    **Warning**: This operation can take 30+ minutes depending on max_pages.
    """
    pipeline = get_pipeline()

    try:
        job_id = pipeline.start_pipeline(
            max_depth=request.max_depth,
            max_pages=request.max_pages,
            download_pdfs=request.download_pdfs,
            recreate_collection=request.recreate_collection,
            collection_name=request.collection_name,
            embedding_model=request.embedding_model,
        )

        return PipelineStartResponse(
            job_id=job_id,
            status="started",
            message=f"Pipeline started. Track progress at /admin/pipeline/status/{job_id}",
        )

    except RuntimeError as e:
        raise HTTPException(
            status_code=409,
            detail=str(e),
        )


@router.get("/status/{job_id}", response_model=PipelineStatusResponse)
async def get_pipeline_status(job_id: str) -> PipelineStatusResponse:
    """Get the status of a pipeline job.

    Returns current step, progress percentage, and statistics.
    """
    pipeline = get_pipeline()
    job = pipeline.get_job_status(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} not found",
        )

    status_dict = job.to_dict()
    return PipelineStatusResponse(**status_dict)


@router.get("/status", response_model=List[PipelineStatusResponse])
async def get_all_pipeline_status() -> List[PipelineStatusResponse]:
    """Get status of all pipeline jobs."""
    pipeline = get_pipeline()
    jobs = pipeline.get_all_jobs()
    return [PipelineStatusResponse(**job) for job in jobs]


@router.get("/logs/{job_id}", response_model=PipelineLogsResponse)
async def get_pipeline_logs(
    job_id: str,
    tail: int = Query(default=50, ge=1, le=500, description="Number of log lines to return"),
) -> PipelineLogsResponse:
    """Get logs for a specific pipeline job.

    Returns the last N log entries for the job.
    """
    pipeline = get_pipeline()
    job = pipeline.get_job_status(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} not found",
        )

    logs = pipeline.get_job_logs(job_id, tail=tail)

    return PipelineLogsResponse(
        job_id=job_id,
        logs=logs,
        total_lines=len(job.logs),
    )


@router.get("/running")
async def is_pipeline_running() -> Dict[str, Any]:
    """Check if a pipeline is currently running."""
    pipeline = get_pipeline()

    return {
        "is_running": pipeline.is_running,
        "current_job_id": pipeline._current_job_id,
    }
