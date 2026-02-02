"""FastAPI application with enhanced architecture."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import time
import uuid
import zipfile
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

from src.agents.router_agent import RouterAgent
from src.db.populate_vectors import VectorPopulator
from src.db.qdrant_client import QdrantManager
from src.llm.llm_factory import LiteLLMWrapper, get_llm
from src.models.retrieval import RetrievalConfig
from src.retrieval.retriever import AdvancedRetriever
from src.utils.config import get_settings
from src.utils.prompts import build_rag_system_prompt, extract_standards_from_docs
from src.utils.source_formatter import extract_pdf_name_from_doc, format_sources_for_response
from src.utils.s3_logger import get_s3_logger
from src.utils.security import validate_path, validate_query_input
from src.utils.exceptions import (
    RAGException,
    PathTraversalError,
    ValidationError as RAGValidationError,
)
from src.pipeline.pipeline_router import router as pipeline_router
from src.utils.metrics import (
    http_requests_total,
    http_request_duration_seconds,
    rag_queries_total,
    rag_query_duration_seconds,
    rag_retrieval_duration_seconds,
    rag_llm_duration_seconds,
    rag_retrieval_docs,
    rag_retrieval_avg_score,
    llm_tokens_total,
    llm_cost_total,
    agent_queries_total,
    agent_query_duration_seconds,
    agent_routing_decisions_total,
    get_metrics,
)

try:
    from litellm import completion
except ImportError:
    completion = None


# Request/Response models
class Source(BaseModel):
    """Source document model."""

    title: str
    url: str
    heading: str
    score: Optional[float] = Field(default=None, description="Relevance score")
    text: Optional[str] = Field(default=None, description="Document text excerpt")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    timestamp: str
    components: Dict[str, str] = Field(default_factory=dict)


class StatsResponse(BaseModel):
    """Statistics response model."""

    collection_info: "CollectionInfo"  # Forward reference
    retriever_config: RetrievalConfig
    agent_config: Dict[str, Any]  # Keep as dict for now - agent config is complex


# New request/response models
class RetrieveResponse(BaseModel):
    """Retrieve response model with context and relevance."""

    query: str
    results: List[Source]
    total: int
    context: str = Field(..., description="Formatted context from retrieved documents")
    metadata: dict = Field(default_factory=dict)


class GenerateRequest(BaseModel):
    """Generate request model (generation with provided context)."""

    query: str = Field(..., min_length=1, max_length=1000, description="User question")
    context: str = Field(..., description="Context to use for generation")


class GenerateResponse(BaseModel):
    """Generate response model."""

    query: str
    answer: str
    context_used: str
    llm_metrics: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class RAGResponse(BaseModel):
    """RAG response model."""

    query: str
    answer: str
    sources: List[Source]
    context: str
    retrieval_metrics: dict = Field(default_factory=dict)
    llm_metrics: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class ChatResponse(BaseModel):
    """Chat response model (agent-based)."""

    query: str
    answer: str
    route: str  # "RAG" or "DIRECT"
    sources: List[Source] = Field(default_factory=list)
    context: str = ""
    metadata: dict = Field(default_factory=dict)


class IndexResponse(BaseModel):
    """Index response model."""

    job_id: str
    status: str
    message: str
    input_dir: str
    collection_name: str


class IndexStatusResponse(BaseModel):
    """Index job status response."""

    job_id: str
    status: str  # pending, running, completed, failed
    progress: Optional[float] = Field(default=None, ge=0.0, le=100.0, description="Progress percentage")
    message: str
    result: Optional[dict] = Field(default=None, description="Result when completed")


class CollectionInfo(BaseModel):
    """Collection information model."""

    name: str
    points_count: int
    vectors_count: int
    status: str
    config: Optional[Dict[str, Any]] = None  # Raw Qdrant config (complex structure)

class CollectionsResponse(BaseModel):
    """Collections list response."""

    collections: List[CollectionInfo]
    total: int

class LLMStatsResponse(BaseModel):
    """LLM statistics response."""

    total_cost: float
    total_calls: int
    total_tokens: Optional[int] = None
    model: str
    last_call_time: Optional[str] = None
    average_cost_per_call: float
    metadata: dict = Field(default_factory=dict)


# ===== SERVICE LAYER =====
class ServiceContainer:
    """Dependency injection container for services."""
    
    def __init__(self) -> None:
        self.agent: Optional[RouterAgent] = None
        self.retriever: Optional[AdvancedRetriever] = None
        self.llm_wrapper: Optional[LiteLLMWrapper] = None
        self.index_jobs: Dict[str, Dict[str, Any]] = {}
        self._settings = get_settings()
    
    def get_retriever(self, collection_name: Optional[str] = None) -> AdvancedRetriever:
        """Get retriever instance, optionally for specific collection."""
        if collection_name:
            return AdvancedRetriever(collection_name=collection_name)
        
        if self.retriever is None:
            self.retriever = AdvancedRetriever()
        return self.retriever
    
    def get_llm(self) -> LiteLLMWrapper:
        """Get LLM wrapper instance."""
        if self.llm_wrapper is None:
            self.llm_wrapper = get_llm(
                provider=self._settings.llm.provider,
                model=self._settings.llm.model,
                temperature=self._settings.llm.temperature,
                max_tokens=self._settings.llm.max_tokens,
                streaming=self._settings.llm.streaming,
                prompt_caching=self._settings.llm.prompt_caching,
            )
        return self.llm_wrapper
    
    def get_agent(self, collection_name: Optional[str] = None) -> RouterAgent:
        """Get router agent instance, optionally for specific collection."""
        if collection_name:
            # Create new agent for specific collection
            retriever = self.get_retriever(collection_name)
            # Agent will create its own LLMs from config
            return RouterAgent(retriever=retriever, collection_name=collection_name)
        
        if self.agent is None:
            retriever = self.get_retriever()
            # Agent will create its own LLMs from config
            self.agent = RouterAgent(retriever=retriever)
        return self.agent
    
    async def warmup_models(self) -> None:
        """Pre-load models during startup to avoid first-request delay.
        
        This loads models in the background so they're ready when users
        make their first request. Prevents 30-60 second delay on first use.
        """
        logger.info("🔥 Warming up models (this may take 30-60 seconds)...")
        start_time = time.time()
        
        try:
            # Load retriever (this loads embedding model + reranker)
            logger.info("Loading embedding model and reranker...")
            retriever = self.get_retriever()
            logger.success(f"✅ Retriever models loaded ({time.time() - start_time:.1f}s)")
            
            # Load LLM wrapper (lightweight, just sets up client)
            logger.info("Initializing LLM wrapper...")
            llm = self.get_llm()
            logger.success(f"✅ LLM wrapper initialized ({time.time() - start_time:.1f}s)")
            
            total_time = time.time() - start_time
            logger.success(f"🎉 All models warmed up successfully in {total_time:.1f}s")
            logger.info("API is now ready for fast responses!")
            
        except Exception as e:
            logger.error(f"⚠️ Model warmup failed: {e}")
            logger.warning("Models will load on first request (may cause 30-60s delay)")
            import traceback
            logger.debug(traceback.format_exc())

# Global service container
services = ServiceContainer()

# Rate limiting storage (in-memory, use Redis for production)
_rate_limit_store: Dict[str, List[float]] = defaultdict(list)


# ===== DEPENDENCY INJECTION =====

def get_services() -> ServiceContainer:
    """Dependency to get service container."""
    return services


def verify_collection_exists(collection_name: str) -> None:
    """Verify that a collection exists in Qdrant.
    
    Args:
        collection_name: Name of the collection to verify
        
    Raises:
        HTTPException: If the collection does not exist (404)
    """
    qdrant = QdrantManager()
    if not qdrant.client.collection_exists(collection_name):
        try:
            available_collections = qdrant.client.get_collections().collections
            collection_names = [col.name for col in available_collections]
        except Exception:
            collection_names = []
        
        raise HTTPException(
            status_code=404,
            detail=(
                f"Collection '{collection_name}' not found in Qdrant. "
                f"Available collections: {', '.join(collection_names) if collection_names else 'none'}. "
                f"Use GET /api/v1/collections to list all available collections."
            )
        )


def get_retriever_service(
    collection: Optional[str] = Query(None, description="Collection name"),
    container: ServiceContainer = Depends(get_services)
) -> AdvancedRetriever:
    """Dependency to get retriever service.
    
    This function receives the collection parameter from the query string
    and creates a retriever instance for that specific collection.
    
    IMPORTANT: When this dependency is used in an endpoint that also has a
    'collection' parameter, FastAPI automatically passes the same query string
    value to both. This is the standard FastAPI behavior - both receive the
    same value from the URL query parameters.
    
    Example:
        GET /api/v1/rag?query=test&collection=my_collection
        - Endpoint's 'collection' parameter receives: "my_collection"
        - This dependency's 'collection' parameter receives: "my_collection"
        - Both values come from the same query string parameter
    
    Raises:
        HTTPException: If the specified collection does not exist in Qdrant.
    """
    try:
        # If a specific collection is requested, verify it exists
        if collection:
            verify_collection_exists(collection)
        
        return container.get_retriever(collection)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to initialize retriever: {e}")
        raise HTTPException(
            status_code=503, 
            detail=f"Retriever not available: {str(e)}"
        )




def get_llm_service(
    container: ServiceContainer = Depends(get_services)
) -> LiteLLMWrapper:
    """Dependency to get LLM service."""
    try:
        return container.get_llm()
    except Exception as e:
        logger.error(f"Failed to initialize LLM: {e}")
        raise HTTPException(
            status_code=503, 
            detail=f"LLM not available: {str(e)}"
        )


def get_agent_service(
    collection: Optional[str] = Query(None, description="Collection name"),
    container: ServiceContainer = Depends(get_services)
) -> RouterAgent:
    """Dependency to get router agent service.
    
    This function receives the collection parameter from the query string
    and creates an agent instance for that specific collection.
    
    Raises:
        HTTPException: If the specified collection does not exist in Qdrant.
    """
    try:
        # If a specific collection is requested, verify it exists
        if collection:
            verify_collection_exists(collection)
        
        return container.get_agent(collection)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to initialize agent: {e}")
        raise HTTPException(
            status_code=503, 
            detail=f"Agent not available: {str(e)}"
        )


# Rate limiting middleware
async def rate_limit_middleware(request: Request, call_next):
    """Simple rate limiting middleware."""
    settings = get_settings()
    rate_limit_config = getattr(settings.api, "rate_limit", None)
    
    if rate_limit_config:
        client_ip = request.client.host if request.client else "unknown"
        current_time = time.time()
        requests_per_minute = getattr(rate_limit_config, "requests_per_minute", 60)
        
        # Clean old requests (older than 1 minute)
        _rate_limit_store[client_ip] = [
            req_time
            for req_time in _rate_limit_store[client_ip]
            if current_time - req_time < 60
        ]
        
        # Check rate limit
        if len(_rate_limit_store[client_ip]) >= requests_per_minute:
            return Response(
                content='{"detail": "Rate limit exceeded"}',
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                media_type="application/json",
            )
        
        # Add current request
        _rate_limit_store[client_ip].append(current_time)
    
    response = await call_next(request)
    return response

# Logging middleware
async def logging_middleware(request: Request, call_next):
    """Logging middleware for request/response."""
    start_time = time.time()
    
    # Log request
    logger.info(
        f"{request.method} {request.url.path} - "
        f"Client: {request.client.host if request.client else 'unknown'}"
    )
    
    response = await call_next(request)
    
    # Log response
    process_time = time.time() - start_time
    log_detail: Optional[str] = None

    if response.status_code >= 400:
        response_body: Optional[bytes] = None
        if getattr(response, "body", None):
            response_body = response.body
        elif getattr(response, "body_iterator", None):
            response_body = b"".join([chunk async for chunk in response.body_iterator])
            response = Response(
                content=response_body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        if response_body:
            try:
                parsed = json.loads(response_body.decode("utf-8"))
                if isinstance(parsed, dict) and "detail" in parsed:
                    log_detail = str(parsed.get("detail"))
            except json.JSONDecodeError:
                pass

    logger.info(
        f"{request.method} {request.url.path} - "
        f"Status: {response.status_code} - "
        f"Time: {process_time:.3f}s"
    )
    if log_detail:
        logger.info(f"Response detail: {log_detail}")
    
    response.headers["X-Process-Time"] = str(process_time)
    return response

# Metrics middleware
async def metrics_middleware(request: Request, call_next):
    """Prometheus metrics middleware."""
    start_time = time.time()
    
    # Skip metrics endpoint itself to avoid recursion
    if request.url.path == "/metrics":
        return await call_next(request)
    
    response = await call_next(request)
    
    duration = time.time() - start_time
    
    # Track metrics
    endpoint = request.url.path
    # Simplify endpoint names for better aggregation
    if endpoint.startswith("/api/v1/"):
        # Keep API paths as-is
        pass
    elif endpoint.startswith("/"):
        endpoint = endpoint.split("/")[1] if len(endpoint.split("/")) > 1 else "root"
    
    http_requests_total.labels(
        method=request.method,
        endpoint=endpoint,
        status=response.status_code
    ).inc()
    
    http_request_duration_seconds.labels(
        method=request.method,
        endpoint=endpoint
    ).observe(duration)
    
    return response

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan manager."""
    # Startup
    logger.info("Starting up ESA IAGen API")
    
    # Warmup models in background (non-blocking)
    # This pre-loads models so first request is fast
    # Models load asynchronously, API is ready immediately
    logger.info("🔥 Starting model warmup in background...")
    warmup_task = asyncio.create_task(services.warmup_models())
    
    logger.info("✅ API ready - models warming up in background")
    logger.info("   First request may be slow if warmup not complete")
    
    yield

    # Shutdown
    logger.info("Shutting down ESA IAGen API")
    # Cancel warmup if still running
    if not warmup_task.done():
        warmup_task.cancel()
    services.agent = None
    services.retriever = None
    services.llm_wrapper = None

# Create FastAPI app
app = FastAPI(
    title="ESA Sentinel Missions AI Agent",
    description="AI-powered API for querying Copernicus Sentinel Missions documentation (SentiWiki) with advanced RAG capabilities",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "health", "description": "Health checks and system status"},
        {"name": "monitoring", "description": "Prometheus metrics"},
        {"name": "Pipeline", "description": "Data pipeline: scrape, enhance, chunk, and ingest SentiWiki"},
        {"name": "indexing", "description": "Document indexing, chunking, and embedding"},
        {"name": "collections", "description": "Qdrant collection management"},
        {"name": "retrieval", "description": "Document retrieval and search"},
        {"name": "generation", "description": "Complete RAG pipeline (retrieve + generate)"},
        {"name": "chat", "description": "Agent-based chat with automatic RAG routing"},
    ],
)

# CORS middleware - MUST be first to handle OPTIONS preflight requests
# If CORS is not first, OPTIONS requests may fail before CORS can handle them
settings = get_settings()

# Custom middleware to handle OPTIONS requests before FastAPI route validation
# FastAPI validates query parameters before CORSMiddleware can respond to OPTIONS.
# This middleware intercepts OPTIONS requests and responds directly with CORS headers.
@app.middleware("http")
async def options_handler(request: Request, call_next):
    """Handle OPTIONS requests before FastAPI validates query parameters.
    
    This middleware intercepts OPTIONS requests and responds directly with CORS headers,
    preventing FastAPI from validating query parameters that would cause a 400 error.
    """
    if request.method == "OPTIONS":
        # Get origin from request
        origin = request.headers.get("origin", "")
        
        # Check if origin is allowed
        allowed_origins = settings.api.cors_origins
        if origin in allowed_origins or "*" in allowed_origins:
            # Respond directly with CORS headers
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": origin if origin else "*",
                    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
                    "Access-Control-Allow-Headers": "*",
                    "Access-Control-Allow-Credentials": "true",
                    "Access-Control-Max-Age": "86400",  # 24 hours
                }
            )
        else:
            # Origin not allowed
            return Response(status_code=403)
    
    # For non-OPTIONS requests, proceed normally
    response = await call_next(request)
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add other middleware (order matters!)
app.middleware("http")(metrics_middleware)  # Tracks all requests
app.middleware("http")(logging_middleware)
app.middleware("http")(rate_limit_middleware)

# Include routers
app.include_router(pipeline_router)


@app.get("/", response_model=HealthResponse, tags=["health"])
async def root() -> HealthResponse:
    """Root endpoint with basic health check - lightweight, no model loading."""
    # Simple health check that doesn't load models
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        timestamp=datetime.utcnow().isoformat(),
        components={
            "api": "ready",
            "message": "API is running. Services load on first use."
        },
    )


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    """Lightweight health check endpoint - doesn't load models."""
    components = {}
    healthy_services = 0
    
    # Check Qdrant connectivity (lightweight - no model loading)
    try:
        qdrant = QdrantManager()
        # Just check if we can connect, don't get full info
        collections_response = qdrant.client.get_collections()
        components["qdrant"] = "ready"
        healthy_services += 1
    except Exception as e:
        components["qdrant"] = f"error: {str(e)[:50]}"
    
    # Don't check retriever/LLM - they load models on first use
    components["retriever"] = "lazy_loaded"
    components["llm"] = "lazy_loaded"
    components["api"] = "ready"
    healthy_services += 1
    
    status_str = "healthy" if healthy_services >= 1 else "unhealthy"
    
    return HealthResponse(
        status=status_str,
        version="0.1.0",
        timestamp=datetime.utcnow().isoformat(),
        components=components,
    )


@app.get("/metrics", tags=["monitoring"])
async def metrics():
    """Prometheus metrics endpoint."""
    from fastapi.responses import Response
    return Response(
        content=get_metrics(),
        media_type="text/plain"
    )


# ===== NEW ENDPOINTS =====

@app.get(
    "/api/v1/retrieve",
    response_model=RetrieveResponse,
    tags=["retrieval"],
    summary="Retrieve relevant documents",
    description="Performs semantic search with hybrid search and cross-encoder reranking. Returns relevant documents with relevance scores and metadata.",
    responses={
        200: {"description": "Successfully retrieved documents"},
        400: {"description": "Invalid query parameters"},
        500: {"description": "Internal server error"},
        503: {"description": "Service unavailable"}
    }
)
async def retrieve(
    query: str = Query(..., description="Search query", min_length=1, max_length=10000, example="What is Sentinel-1 resolution?"),
    collection: Optional[str] = Query(None, description="Collection name to query from (default: sentiwiki)", example="sentiwiki"),
    use_reranking: Optional[bool] = Query(True, description="Enable cross-encoder reranking for better relevance (default: true)"),
    use_hybrid: Optional[bool] = Query(True, description="Enable hybrid search combining semantic + keyword matching (default: true)"),
    # FastAPI automatically passes the 'collection' query parameter to get_retriever_service
    # Both the endpoint and dependency receive the same value from the query string
    retriever: AdvancedRetriever = Depends(get_retriever_service),
) -> RetrieveResponse:
    try:
        # Use default top_k from config (settings.yaml)
        # Use async version to avoid blocking event loop during embedding + reranking
        docs = await retriever.retrieve_async(
            query=query,
            top_k=None,  # None uses retriever.top_k_default from settings.yaml
            filters=None,  # Simplified for now
            use_reranking=use_reranking,
            use_hybrid=use_hybrid,
        )

        # Format context from retrieved documents
        context_parts = []
        for i, doc in enumerate(docs, 1):
            text = doc.get("contextualized_text") or doc.get("text", "")
            score = doc.get("score", 0.0)
            context_parts.append(
                f"[Document {i}] {doc.get('title', 'Unknown')} "
                f"(Relevance: {score:.4f})\n"
                f"Source: {doc.get('url', '')}\n"
                f"Section: {doc.get('heading', '')}\n"
                f"Content:\n{text}\n"
            )
        context = "\n---\n\n".join(context_parts)

        results = [
            Source(
                title=doc.get("title", "Unknown"),
                url=doc.get("url", ""),
                heading=doc.get("heading", ""),
                score=doc.get("score"),
                text=(doc.get("contextualized_text") or doc.get("text", ""))[:500] + "...",
            )
            for doc in docs
        ]

        return RetrieveResponse(
            query=query,
            results=results,
            total=len(results),
            context=context,
            metadata={
                "mode": "retrieve",
                "collection": retriever.qdrant.collection_name,
                "top_k": retriever.top_k_default,
                "reranking_enabled": use_reranking if use_reranking is not None else retriever.reranker_enabled,
                "hybrid_search_enabled": use_hybrid if use_hybrid is not None else retriever.hybrid_search_enabled,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in retrieve: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}",
        )


# Removed /api/v1/generate endpoint - not useful (use /api/v1/rag or /api/v1/generate-with-context instead)


@app.get(
    "/api/v1/rag",
    response_model=RAGResponse,
    tags=["generation"],
    summary="Query with RAG (Retrieval-Augmented Generation)",
    description="Complete RAG pipeline: retrieves relevant documents and generates a grounded answer using an LLM. Returns answer with source citations and relevance scores.",
    responses={
        200: {"description": "Successfully generated answer with sources"},
        400: {"description": "Invalid query"},
        429: {"description": "Rate limit exceeded"},
        500: {"description": "Internal server error"},
        503: {"description": "Service unavailable"}
    }
)
async def rag(
    query: str = Query(..., description="User question", min_length=1, max_length=10000, example="What is the spatial resolution of Sentinel-1 IW mode?"),
    collection: Optional[str] = Query(None, description="Collection name to query from (default: sentiwiki)", example="sentiwiki"),
    use_reranking: Optional[bool] = Query(True, description="Enable cross-encoder reranking for better relevance"),
    use_hybrid: Optional[bool] = Query(True, description="Enable hybrid search (semantic + keyword)"),
    # FastAPI automatically passes the 'collection' query parameter to get_retriever_service
    # Both the endpoint and dependency receive the same value from the query string
    retriever: AdvancedRetriever = Depends(get_retriever_service),
    llm_service: LiteLLMWrapper = Depends(get_llm_service),
) -> RAGResponse:
    start_time = time.time()
    collection_name = collection or retriever.qdrant.collection_name
    
    try:
        # Track query start
        rag_queries_total.labels(
            collection=collection_name,
            reranking_enabled=str(use_reranking if use_reranking is not None else retriever.reranker_enabled),
            hybrid_enabled=str(use_hybrid if use_hybrid is not None else retriever.hybrid_search_enabled)
        ).inc()
        
        # Step 1: Retrieve with advanced techniques (uses default top_k from config)
        # Use async version to avoid blocking event loop
        retrieval_start = time.time()
        docs = await retriever.retrieve_async(
            query=query,
            top_k=None,  # None uses retriever.top_k_default from settings.yaml
            filters=None,  # Simplified
            use_reranking=use_reranking,
            use_hybrid=use_hybrid,
        )
        retrieval_duration = time.time() - retrieval_start
        
        # Track retrieval metrics
        rag_retrieval_duration_seconds.labels(collection=collection_name).observe(retrieval_duration)
        rag_retrieval_docs.labels(collection=collection_name).observe(len(docs))
        
        if docs:
            avg_score = sum(d.get("score", 0) for d in docs) / len(docs)
            rag_retrieval_avg_score.labels(collection=collection_name).observe(avg_score)

        # Format context
        context_parts = []
        for i, doc in enumerate(docs, 1):
            text = doc.get("contextualized_text") or doc.get("text", "")
            score = doc.get("score", 0.0)
            context_parts.append(
                f"[Document {i}] {doc.get('title', 'Unknown')} "
                f"(Relevance: {score:.4f})\n"
                f"Content:\n{text}\n"
            )
        context = "\n---\n\n".join(context_parts)

        # Extract ECSS standards from documents
        standards_in_context = extract_standards_from_docs(docs)

        # Step 2: Generate with enhanced prompt
        system_prompt = build_rag_system_prompt(
            context=context,
            standards_in_context=standards_in_context,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ]

        # ====================================================================
        # DETAILED LOGGING: Context and Token Information
        # ====================================================================
        logger.info("=" * 80)
        logger.info("🤖 LLM CALL: RAG Answer Generation (API Endpoint)")
        logger.info("=" * 80)
        logger.info(f"📝 Query: {query}")
        logger.info("")
        logger.info(f"📊 Context Statistics:")
        logger.info(f"   - Documents: {len(docs)}")
        logger.info(f"   - Context Length: {len(context):,} characters")
        logger.info(f"   - System Prompt Length: {len(system_prompt):,} characters")
        logger.info(f"   - User Query Length: {len(query):,} characters")
        # Estimate tokens (rough: ~4 chars per token)
        estimated_tokens = (len(system_prompt) + len(query)) // 4
        logger.info(f"   - Estimated Prompt Tokens: ~{estimated_tokens:,}")
        logger.info("")
        # Document summary logging (only to log files, not terminal)
        logger.debug(f"📄 Documents Used as Context:")
        logger.debug("-" * 80)
        for i, doc in enumerate(docs, 1):
            title = doc.get('title', 'Unknown')
            score = doc.get('score', 0.0)
            text = doc.get("contextualized_text") or doc.get("text", "")
            text_length = len(text)
            url = doc.get('url', '')
            heading = doc.get('heading', '')
            logger.debug(f"  [{i}/{len(docs)}] {title} | Score: {score:.4f} | Length: {text_length:,} chars (~{text_length//4:,} tokens)")
            if url:
                logger.debug(f"      URL: {url}")
            if heading:
                logger.debug(f"      Heading: {heading}")
        logger.debug("-" * 80)
        logger.debug("")
        logger.debug(f"📋 Full System Prompt (for review):")
        logger.debug("-" * 80)
        # Log system prompt with line numbers for easier review
        for i, line in enumerate(system_prompt.split('\n'), 1):
            logger.debug(f"{i:4d} | {line}")
        logger.debug("-" * 80)
        logger.debug("")
        logger.info("🚀 Invoking LLM...")
        logger.info("=" * 80)

        # Track LLM generation
        # Use async version to avoid blocking event loop during LLM API call
        llm_start = time.time()
        answer = await llm_service.invoke_async(messages)
        llm_duration = time.time() - llm_start
        llm_metrics = llm_service.get_last_response_metrics()

        # Log token usage after LLM call
        if llm_metrics:
            logger.info("=" * 80)
            logger.info("💰 LLM CALL COMPLETED: Token Usage")
            logger.info("=" * 80)
            prompt_tokens = llm_metrics.prompt_tokens
            completion_tokens = llm_metrics.completion_tokens
            total_tokens = llm_metrics.total_tokens
            logger.info(f"📥 Prompt Tokens: {prompt_tokens:,}" if isinstance(prompt_tokens, int) else f"📥 Prompt Tokens: {prompt_tokens}")
            logger.info(f"📤 Completion Tokens: {completion_tokens:,}" if isinstance(completion_tokens, int) else f"📤 Completion Tokens: {completion_tokens}")
            logger.info(f"📊 Total Tokens: {total_tokens:,}" if isinstance(total_tokens, int) else f"📊 Total Tokens: {total_tokens}")
            if llm_metrics.cost:
                logger.info(f"💵 Cost: ${llm_metrics.cost:.6f}")
            logger.info("=" * 80)

        # Track LLM metrics
        rag_llm_duration_seconds.labels(model=llm_service.model).observe(llm_duration)
        
        if llm_metrics:
            llm_tokens_total.labels(
                model=llm_service.model,
                type="prompt"
            ).inc(llm_metrics.get("prompt_tokens", 0))
            
            llm_tokens_total.labels(
                model=llm_service.model,
                type="completion"
            ).inc(llm_metrics.get("completion_tokens", 0))
            
            if llm_metrics.get("cost"):
                llm_cost_total.labels(model=llm_service.model).inc(llm_metrics["cost"])

        # Format sources with PDF names and score percentages (consistent format)
        # No limit in backend - frontend will limit to top 5
        formatted_sources = format_sources_for_response(docs, limit=None)
        sources = [
            Source(
                title=src.get("pdf_name", "Unknown"),
                url=src.get("url", ""),
                heading=src.get("heading", ""),
                score=src.get("score_percentage", 0.0),  # Use percentage score
                text=src.get("text", ""),
            )
            for src in formatted_sources
        ]

        response = RAGResponse(
            query=query,
            answer=answer,
            sources=sources,
            context=context[:1000] + "..." if len(context) > 1000 else context,
            retrieval_metrics={
                "num_docs": len(docs),
                "avg_score": sum(d.get("score", 0) for d in docs) / len(docs) if docs else 0,
            },
            llm_metrics=llm_metrics,
            metadata={
                "mode": "rag",
                "collection": retriever.qdrant.collection_name,
                "top_k": retriever.top_k_default,
                "model": llm_service.model,
                "reranking_enabled": use_reranking if use_reranking is not None else retriever.reranker_enabled,
                "hybrid_search_enabled": use_hybrid if use_hybrid is not None else retriever.hybrid_search_enabled,
            },
        )
        
        # Track total query duration
        total_duration = time.time() - start_time
        rag_query_duration_seconds.labels(collection=collection_name).observe(total_duration)
        
        # Log to S3
        s3_logger = get_s3_logger()
        if s3_logger:
            query_id = str(uuid.uuid4())
            s3_logger.log_query(
                query_id=query_id,
                query=query,
                route="RAG",
                response={
                    "answer": answer,
                    "sources_count": len(sources),
                    "sources": [{"title": s.title, "url": s.url, "score": s.score} for s in sources],
                },
                metadata={
                    "duration_seconds": total_duration,
                    "retrieval_duration": retrieval_duration,
                    "llm_duration": llm_duration,
                    "collection": collection_name,
                    "num_docs": len(docs),
                    "model": llm_service.model,
                    "llm_metrics": llm_metrics,
                    "reranking_enabled": use_reranking if use_reranking is not None else retriever.reranker_enabled,
                    "hybrid_search_enabled": use_hybrid if use_hybrid is not None else retriever.hybrid_search_enabled,
                },
            )
        
        return response

    except HTTPException:
        raise
    except Exception as e:
        # Still track metrics even on error
        total_duration = time.time() - start_time
        rag_query_duration_seconds.labels(collection=collection_name).observe(total_duration)
        logger.exception(f"Error in RAG: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}",
        )


@app.options("/api/v1/rag/stream", tags=["generation"], include_in_schema=False)
async def rag_stream_options(
    query: Optional[str] = Query(None, description="User question (ignored for OPTIONS)"),
    collection: Optional[str] = Query(None, description="Collection name (ignored for OPTIONS)"),
    use_reranking: Optional[bool] = Query(None, description="Enable reranking (ignored for OPTIONS)"),
    use_hybrid: Optional[bool] = Query(None, description="Enable hybrid search (ignored for OPTIONS)"),
):
    """Handle OPTIONS preflight requests for /api/v1/rag/stream.
    Accepts query parameters as optional to avoid validation errors.
    """
    return Response(status_code=200)


@app.get(
    "/api/v1/rag/stream",
    tags=["generation"],
    summary="Stream RAG response (Server-Sent Events)",
    description="Streams RAG response in real-time using Server-Sent Events. Returns stages: retrieving, retrieved, generating, streaming (chunks), and complete (with sources).",
    responses={
        200: {"description": "Server-Sent Events stream"},
        400: {"description": "Invalid query parameters"},
        503: {"description": "Streaming not available"}
    }
)
async def rag_stream(
    query: str = Query(..., description="User question", min_length=1, max_length=10000, example="What is Sentinel-1?"),
    collection: Optional[str] = Query(None, description="Collection name to query from (default: sentiwiki)"),
    use_reranking: Optional[bool] = Query(True, description="Enable cross-encoder reranking"),
    use_hybrid: Optional[bool] = Query(True, description="Enable hybrid search"),
    # FastAPI automatically passes the 'collection' query parameter to get_retriever_service
    # Both the endpoint and dependency receive the same value from the query string
    retriever: AdvancedRetriever = Depends(get_retriever_service),
    llm_service: LiteLLMWrapper = Depends(get_llm_service),
):
    if completion is None:
        raise HTTPException(
            status_code=503,
            detail="Streaming not available: litellm is not installed"
        )
    
    async def generate() -> AsyncGenerator[str, None]:
        """Generate streaming response."""
        try:
            # Stage 1: Retrieval (uses default top_k from config)
            yield f"data: {json.dumps({'stage': 'retrieving', 'message': 'Searching documents...'})}\n\n"

            # Use async version to avoid blocking event loop
            docs = await retriever.retrieve_async(
                query=query,
                top_k=None,  # None uses retriever.top_k_default from settings.yaml
                filters=None,  # Simplified
                use_reranking=use_reranking,
                use_hybrid=use_hybrid,
            )
            
            yield f"data: {json.dumps({'stage': 'retrieved', 'count': len(docs), 'message': f'Found {len(docs)} documents'})}\n\n"
            
            # Format context (same logic as non-streaming endpoint)
            context_parts = []
            for i, doc in enumerate(docs, 1):
                text = doc.get("contextualized_text") or doc.get("text", "")
                score = doc.get("score", 0.0)
                context_parts.append(
                    f"[Document {i}] {doc.get('title', 'Unknown')} "
                    f"(Relevance: {score:.4f})\n"
                    f"Content:\n{text}\n"
                )
            context = "\n---\n\n".join(context_parts)
            
            # Extract ECSS standards from documents
            standards_in_context = extract_standards_from_docs(docs)
            
            # Create prompt (same logic as non-streaming endpoint)
            system_prompt = build_rag_system_prompt(
                context=context,
                standards_in_context=standards_in_context,
            )
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ]
            
            # Stage 2: Generate with streaming
            yield f"data: {json.dumps({'stage': 'generating', 'message': 'Generating answer...'})}\n\n"
            
            # Stream LLM response using async method
            try:
                # Use stream_async to avoid blocking event loop during LLM streaming
                async for token in llm_service.stream_async(messages):
                    # json.dumps handles escaping automatically
                    yield f"data: {json.dumps({'stage': 'streaming', 'chunk': token})}\n\n"
                
                # Stage 3: Complete - Include sources with PDF names and score percentages
                # No limit in backend - frontend will limit to top 5
                formatted_sources = format_sources_for_response(docs, limit=None)
                complete_data = {
                    'stage': 'complete',
                    'message': 'Answer complete',
                    'sources': formatted_sources,
                }
                yield f"data: {json.dumps(complete_data)}\n\n"
                
            except Exception as e:
                logger.exception(f"Error streaming LLM response: {str(e)}")
                yield f"data: {json.dumps({'stage': 'error', 'message': f'Generation failed: {str(e)}'})}\n\n"
                
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error in streaming RAG: {str(e)}")
            yield f"data: {json.dumps({'stage': 'error', 'message': f'Internal server error: {str(e)}'})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable buffering in nginx
        }
    )


# ===== AGENT-BASED CHAT ENDPOINTS =====

@app.options("/api/v1/chat", tags=["chat"], include_in_schema=False)
async def chat_options(
    query: Optional[str] = Query(None, description="User question (ignored for OPTIONS)"),
    collection: Optional[str] = Query(None, description="Collection name (ignored for OPTIONS)"),
):
    """Handle OPTIONS preflight requests for /api/v1/chat.
    Accepts query parameters as optional to avoid validation errors.
    """
    return Response(status_code=200)


@app.get(
    "/api/v1/chat",
    response_model=ChatResponse,
    tags=["chat"],
    summary="Agent-based chat with automatic routing",
    description="Automatically routes queries to RAG (for Sentinel/SentiWiki questions) or direct LLM (for general questions). Returns answer with route decision and sources if RAG was used.",
)
async def chat(
    query: str = Query(..., description="User question"),
    collection: Optional[str] = Query(None, description="Collection name to query from"),
    # FastAPI automatically passes the 'collection' query parameter to get_agent_service
    agent: RouterAgent = Depends(get_agent_service),
) -> ChatResponse:
    start_time = time.time()
    
    try:
        # Invoke the agent first (don't access retriever before routing decision)
        result = agent.invoke(query)
        route = result.get("route", "UNKNOWN")
        duration = time.time() - start_time
        
        # Get collection name after agent execution (from result metadata or retriever)
        collection_name = (
            collection 
            or result.get("metadata", {}).get("collection")
            or agent.retriever.qdrant.collection_name
        )
        
        # Track agent metrics
        agent_queries_total.labels(
            collection=collection_name,
            route=route
        ).inc()
        
        agent_query_duration_seconds.labels(route=route).observe(duration)
        agent_routing_decisions_total.labels(route=route).inc()
        
        # Format sources if available - no limit in backend, frontend will limit to top 5
        sources = []
        for src in result.get("sources", []):
            # PDF name should already be extracted in router_agent, but fallback to title
            pdf_name = src.get("pdf_name") or src.get("title", "Unknown")
            score_percentage = src.get("score_percentage", 0.0)
            
            sources.append(Source(
                title=pdf_name,  # Use PDF name as title
                url=src.get("url", ""),
                heading=src.get("heading", ""),
                score=score_percentage,  # Use percentage score
                text=src.get("text", ""),
            ))
        
        response = ChatResponse(
            query=result["query"],
            answer=result["answer"],
            route=route,
            sources=sources,
            context=result.get("context", ""),
            metadata={
                **result.get("metadata", {}),
                "duration_seconds": duration,
            },
        )
        
        # Log to S3
        s3_logger = get_s3_logger()
        if s3_logger:
            query_id = str(uuid.uuid4())
            s3_logger.log_query(
                query_id=query_id,
                query=query,
                route=route,
                response={
                    "answer": result["answer"],
                    "sources_count": len(sources),
                    "sources": [{"title": s.title, "url": s.url, "score": s.score} for s in sources],
                },
                metadata={
                    **result.get("metadata", {}),
                    "duration_seconds": duration,
                    "collection": collection_name,
                },
                agent_state=result.get("agent_state"),
            )
        
        logger.info(f"✅ Chat completed: route={response.route}, duration={response.metadata['duration_seconds']:.2f}s")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in chat: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}",
        )


@app.options("/api/v1/chat/stream", tags=["chat"], include_in_schema=False)
async def chat_stream_options(
    query: Optional[str] = Query(None, description="User question (ignored for OPTIONS)"),
    collection: Optional[str] = Query(None, description="Collection name (ignored for OPTIONS)"),
):
    """Handle OPTIONS preflight requests for /api/v1/chat/stream.
    
    This endpoint is needed because the GET endpoint requires query parameters,
    and FastAPI validates these before CORSMiddleware can respond to OPTIONS.
    This explicit OPTIONS endpoint ensures CORS preflight works correctly.
    Accepts query parameters as optional to avoid validation errors.
    """
    # CORSMiddleware will add the CORS headers automatically
    return Response(status_code=200)


@app.get(
    "/api/v1/chat/stream",
    tags=["chat"],
    summary="Stream agent-based chat (Server-Sent Events)",
    description="Streams agent response with automatic routing. Stages: routing, routed, retrieving (RAG only), retrieved, generating, streaming (chunks), complete.",
)
async def chat_stream(
    query: str = Query(..., description="User question"),
    collection: Optional[str] = Query(None, description="Collection name to query from"),
    # FastAPI automatically passes the 'collection' query parameter to get_agent_service
    agent: RouterAgent = Depends(get_agent_service),
):
    if completion is None:
        raise HTTPException(
            status_code=503,
            detail="Streaming not available: litellm is not installed"
        )
    
    async def generate() -> AsyncGenerator[str, None]:
        """Generate streaming response using invoke() for reliable state capture."""
        try:
            import asyncio
            
            # Stage 1: Routing
            yield f"data: {json.dumps({'stage': 'routing', 'message': 'Analyzing query intent...'})}\n\n"
            await asyncio.sleep(0.3)  # Small delay to ensure UI updates
            
            # Use invoke() instead of astream() - it always returns the complete final state
            # This avoids issues with state capture and ensures we get answer, sources, and metadata
            result = agent.invoke(query)
            
            # Extract all data from the final state
            route = result.get("route", "UNKNOWN")
            answer = result.get("answer", "")
            sources = result.get("sources", [])
            context = result.get("context", "")
            metadata = result.get("metadata", {})
            
            # Send route update
            yield f"data: {json.dumps({'stage': 'routed', 'route': route, 'message': f'Route determined: {route}'})}\n\n"
            await asyncio.sleep(0.3)  # Small delay to ensure UI updates
            
            # If RAG route, send retrieval updates
            if route == "RAG" and sources:
                yield f"data: {json.dumps({'stage': 'retrieving', 'message': 'Searching documents...'})}\n\n"
                await asyncio.sleep(0.5)  # Slightly longer for retrieval
                yield f"data: {json.dumps({'stage': 'retrieved', 'count': len(sources), 'message': f'Found {len(sources)} documents'})}\n\n"
                await asyncio.sleep(0.3)  # Small delay to ensure UI updates
            
            # Stream the answer
            if answer:
                yield f"data: {json.dumps({'stage': 'generating', 'message': 'Generating answer...'})}\n\n"
                await asyncio.sleep(0.3)  # Small delay to ensure UI updates
                # Stream answer in chunks for better UX
                chunk_size = 20
                for i in range(0, len(answer), chunk_size):
                    chunk = answer[i:i + chunk_size]
                    yield f"data: {json.dumps({'stage': 'streaming', 'chunk': chunk})}\n\n"
            else:
                # If no answer, provide error message
                logger.warning("⚠️  No answer received from agent.invoke() - this should not happen.")
                error_msg = "I apologize, but I encountered an error while generating the answer. Please try again."
                yield f"data: {json.dumps({'stage': 'generating', 'message': 'Generating answer...'})}\n\n"
                chunk_size = 20
                for i in range(0, len(error_msg), chunk_size):
                    chunk = error_msg[i:i + chunk_size]
                    yield f"data: {json.dumps({'stage': 'streaming', 'chunk': chunk})}\n\n"
            
            # Stage 3: Complete - Include sources and metadata if available
            complete_data = {
                'stage': 'complete',
                'message': 'Answer complete',
                'route': route or 'UNKNOWN',
            }
            
            # Include metadata (rewritten_query, grade_score, etc.) if available
            if metadata:
                complete_data['metadata'] = metadata
            # Format sources for frontend - no limit in backend, frontend will limit to top 5
            logger.info(f"📚 Preparing complete message. Sources count: {len(sources) if sources else 0}")
            if sources:
                # No limit in backend - frontend will limit to top 5
                logger.info(f"📚 Sending all {len(sources)} sources to frontend (frontend will limit to top 5)")
                logger.info(f"📚 Sources before formatting: {sources[:2]}...")  # Log first 2
                complete_data['sources'] = [
                    {
                        'title': src.get('title', 'Unknown'),
                        'url': src.get('url', ''),
                        'heading': src.get('heading', ''),
                        'score': src.get('score'),
                        'score_percentage': src.get('score_percentage', 0.0),
                        'pdf_name': src.get('pdf_name', src.get('title', 'Unknown')),  # Use pdf_name, fallback to title
                        'headings_with_urls': src.get('headings_with_urls', []),  # Include section URLs
                    }
                    for src in sources
                ]
                logger.info(f"📚 Sources after formatting: {complete_data['sources'][:2]}...")  # Log first 2
            else:
                logger.warning("⚠️ No sources available for complete message")
            logger.info(f"📤 Sending complete message: {json.dumps(complete_data)[:200]}...")
            yield f"data: {json.dumps(complete_data)}\n\n"
            
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error in streaming chat: {str(e)}")
            yield f"data: {json.dumps({'stage': 'error', 'message': f'Internal server error: {str(e)}'})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable buffering in nginx
        }
        )


@app.get(
    "/api/v1/collections",
    response_model=CollectionsResponse,
    tags=["collections"],
    summary="List all vector collections",
    description="Lists all available collections in Qdrant with their status, point counts, and configuration.",
    responses={
        200: {
            "description": "Successfully retrieved collections list",
            "content": {
                "application/json": {
                    "example": {
                        "collections": [
                            {
                                "name": "sentiwiki",
                                "points_count": 15234,
                                "vectors_count": 15234,
                                "status": "green",
                                "config": {
                                    "params": {
                                        "vectors": {"size": 384, "distance": "Cosine"}
                                    }
                                }
                            }
                        ],
                        "count": 1
                    }
                }
            }
        },
        500: {"description": "Failed to connect to Qdrant"},
        503: {"description": "Qdrant service unavailable"}
    }
)
async def list_collections(
    container: ServiceContainer = Depends(get_services)
) -> CollectionsResponse:
    try:
        qdrant = QdrantManager()
        
        # Get all collections
        collections_info = []
        try:
            collections_response = qdrant.client.get_collections()
            
            for col in collections_response.collections:
                try:
                    # Get detailed info for each collection
                    collection_info = qdrant.client.get_collection(col.name)
                    
                    collections_info.append(
                        CollectionInfo(
                            name=col.name,
                            points_count=collection_info.points_count if hasattr(collection_info, 'points_count') else 0,
                            vectors_count=collection_info.vectors_count if hasattr(collection_info, 'vectors_count') else 0,
                            status=str(collection_info.status) if hasattr(collection_info, 'status') else "unknown",
                            config=collection_info.config.dict() if hasattr(collection_info, 'config') and collection_info.config else None,
                        )
                    )
                except Exception as e:
                    logger.warning(f"Error getting info for collection {col.name}: {e}")
                    # Add collection with minimal info if detailed info fails
                    collections_info.append(
                        CollectionInfo(
                            name=col.name,
                            points_count=0,
                            vectors_count=0,
                            status="error",
                            config=None,
                        )
                    )
                    
        except Exception as e:
            logger.warning(f"Error listing collections: {e}")
            # Fallback: return current collection if available
            try:
                retriever = container.get_retriever()
                info = retriever.qdrant.get_collection_info()
                collections_info.append(
                    CollectionInfo(
                        name=retriever.qdrant.collection_name,
                        points_count=info.get("points_count", 0),
                        vectors_count=info.get("vectors_count", 0),
                        status=str(info.get("status", "unknown")),
                        config=info.get("config"),
                    )
                )
            except Exception:
                pass  # If we can't get default collection, just return empty list

        return CollectionsResponse(
            collections=collections_info,
            total=len(collections_info),
        )

    except Exception as e:
        logger.exception(f"Error listing collections: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}",
        )


@app.get("/api/v1/collections/{collection_name}/info", tags=["collections"])
async def get_collection_info(collection_name: str) -> dict:
    """Get detailed information about a specific collection."""
    try:
        # Verify collection exists before attempting to get info
        verify_collection_exists(collection_name)
        
        qdrant = QdrantManager(collection_name=collection_name)
        info = qdrant.get_collection_info()
        return {
            "collection_name": collection_name,
            **info,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting collection info: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}",
        )


@app.delete("/api/v1/collections/{collection_name}", tags=["collections"])
async def delete_collection(collection_name: str) -> dict:
    """Delete a collection from Qdrant."""
    try:
        # Verify collection exists before attempting to delete
        verify_collection_exists(collection_name)
        
        qdrant = QdrantManager(collection_name=collection_name)
        qdrant.client.delete_collection(collection_name)
        
        logger.info(f"Deleted collection: {collection_name}")
        return {
            "status": "success",
            "message": f"Collection '{collection_name}' deleted successfully",
            "collection_name": collection_name,
        }
    except HTTPException:
        raise

    except Exception as e:
        logger.exception(f"Error deleting collection: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}",
        )


@app.post(
    "/api/v1/index",
    response_model=IndexResponse,
    tags=["indexing"],
    summary="Index documents into Qdrant",
    description="Starts async indexing job. Use /api/v1/index/status/{job_id} to check progress.",
)
async def index_documents(
    input_dir: str,
    collection: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    batch_size: Optional[int] = None,
    distance: Optional[str] = None,
    normalize: Optional[bool] = None,
    recreate: bool = False,
) -> IndexResponse:
    try:
        job_id = str(uuid.uuid4())
        input_path = Path(input_dir)
        
        if not input_path.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Input directory does not exist: {input_dir}",
            )

        # Get settings for defaults
        settings = get_settings()

        # Handle empty/None values: use settings defaults if not provided or invalid
        # Validate provider against allowed values
        valid_providers = ["huggingface", "openai"]
        final_provider = None
        if provider and provider.strip() and provider.lower() in valid_providers:
            final_provider = provider.lower()
        else:
            final_provider = settings.embeddings.provider
        
        # Handle model: use settings default if None or empty
        final_model = (model.strip() if model and model.strip() else None) or settings.embeddings.model
        
        # Handle batch_size: None or 0 means use default
        final_batch_size = batch_size if batch_size and batch_size > 0 else settings.embeddings.batch_size
        
        # Handle distance: validate against allowed values
        valid_distances = ["Cosine", "Euclid", "Dot"]
        final_distance = distance if distance and distance in valid_distances else settings.qdrant.distance
        
        # Handle normalize: None means use default based on provider
        final_normalize = normalize if normalize is not None else (final_provider == "huggingface")
        
        # Create request object for background job
        request_data = {
            "input_dir": input_dir,
            "collection_name": collection,
            "provider": final_provider,
            "model": final_model,
            "batch_size": final_batch_size,
            "distance": final_distance,
            "normalize": final_normalize,
            "recreate": recreate,
        }
        
        logger.info(f"Indexing configuration: provider={final_provider}, model={final_model}, batch_size={final_batch_size}, distance={final_distance}, normalize={final_normalize}")

        # Store job info
        services.index_jobs[job_id] = {
            "status": "pending",
            "progress": 0.0,
            "message": "Job queued",
            "request": request_data,
            "started_at": datetime.utcnow().isoformat(),
        }

        # Start indexing in background
        asyncio.create_task(_run_index_job(job_id, request_data))

        return IndexResponse(
            job_id=job_id,
            status="pending",
            message="Indexing job started. Use /api/v1/index/status/{job_id} to check progress.",
            input_dir=input_dir,
            collection_name=collection,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error starting index job: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}",
        )


async def _run_index_job(job_id: str, request_data: dict) -> None:
    """Run indexing job in background."""
    try:
        services.index_jobs[job_id]["status"] = "running"
        services.index_jobs[job_id]["message"] = "Loading documents..."
        services.index_jobs[job_id]["progress"] = 10.0

        populator = VectorPopulator(
            input_dir=Path(request_data["input_dir"]),
            collection_name=request_data["collection_name"],
            embedding_provider=request_data["provider"],
            embedding_model=request_data["model"],
            batch_size=request_data["batch_size"],
            distance=request_data["distance"],
            normalize_embeddings=request_data["normalize"],
        )

        services.index_jobs[job_id]["message"] = "Generating embeddings..."
        services.index_jobs[job_id]["progress"] = 30.0

        # Run blocking populate() in thread pool to avoid blocking event loop
        # This allows the endpoint to return immediately while work continues in background
        await asyncio.to_thread(populator.populate, recreate=request_data["recreate"])

        services.index_jobs[job_id]["status"] = "completed"
        services.index_jobs[job_id]["progress"] = 100.0
        services.index_jobs[job_id]["message"] = "Indexing completed successfully"
        services.index_jobs[job_id]["completed_at"] = datetime.utcnow().isoformat()
        
        # Get collection info
        qdrant = QdrantManager(collection_name=request_data["collection_name"])
        info = qdrant.get_collection_info()
        services.index_jobs[job_id]["result"] = {
            "collection_info": info,
            "collection_name": request_data["collection_name"],
        }

    except Exception as e:
        logger.exception(f"Error in index job {job_id}: {str(e)}")
        services.index_jobs[job_id]["status"] = "failed"
        services.index_jobs[job_id]["message"] = f"Indexing failed: {str(e)}"
        services.index_jobs[job_id]["error"] = str(e)


@app.get("/api/v1/index/status/{job_id}", response_model=IndexStatusResponse, tags=["indexing"])
async def get_index_status(
    job_id: str,
    container: ServiceContainer = Depends(get_services)
) -> IndexStatusResponse:
    """Get status of an indexing job."""
    if job_id not in container.index_jobs:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} not found",
        )

    job = container.index_jobs[job_id]
    return IndexStatusResponse(
        job_id=job_id,
        status=job["status"],
        progress=job.get("progress"),
        message=job["message"],
        result=job.get("result"),
    )


@app.post(
    "/api/v1/upload-and-index",
    response_model=IndexResponse,
    tags=["indexing"],
    summary="Upload and index documents from local folder",
    description=(
        "Uploads a zip file containing processed JSON documents and indexes them into Qdrant. "
        "This allows you to upload locally-generated scraped data to the deployed AWS system. "
        "The zip file should contain the processed JSON files (e.g., from data/processed/sentiwiki_structured/). "
        "Returns a job_id to track indexing progress via /api/v1/index/status/{job_id}."
    ),
)
async def upload_and_index(
    file: UploadFile = File(..., description="Zip file containing processed JSON documents"),
    collection: str = Form(..., description="Qdrant collection name"),
    provider: Optional[str] = Form(default=None, description="Embedding provider (default: from settings)"),
    model: Optional[str] = Form(default=None, description="Embedding model (default: from settings)"),
    batch_size: Optional[int] = Form(default=None, description="Batch size for embeddings (default: from settings)"),
    distance: Optional[str] = Form(default=None, description="Vector distance metric (default: from settings)"),
    normalize: Optional[bool] = Form(default=None, description="Normalize embeddings (default: from settings)"),
    recreate: bool = Form(default=False, description="Recreate collection before indexing"),
) -> IndexResponse:
    """
    Upload a zip file containing processed JSON documents and index them into Qdrant.
    
    This endpoint is designed for uploading locally-generated scraped data to the deployed system.
    It maintains legal compliance by requiring users to generate data locally and upload it themselves.
    
    **Usage:**
    1. Generate data locally: `uv run python -m src.parsers.sentiwiki_chunker`
    2. Zip the processed folder: `zip -r data.zip data/processed/sentiwiki_structured/`
    3. Upload via this endpoint
    4. Track progress: `GET /api/v1/index/status/{job_id}`
    
    **Example with curl:**
    ```bash
    curl -X POST "http://your-api/api/v1/upload-and-index" \
      -F "file=@data.zip" \
      -F "collection=sentiwiki_index" \
      -F "recreate=true"
    ```
    """
    job_id = str(uuid.uuid4())
    temp_dir = None
    
    try:
        # Validate file type
        if not file.filename or not file.filename.endswith('.zip'):
            raise HTTPException(
                status_code=400,
                detail="File must be a .zip file containing processed JSON documents"
            )
        
        # Create temporary directory for extraction
        settings = get_settings()
        temp_base = Path(settings.data_dir) / "temp_uploads"
        temp_base.mkdir(parents=True, exist_ok=True)
        
        temp_dir = Path(tempfile.mkdtemp(dir=temp_base, prefix=f"upload_{job_id}_"))
        logger.info(f"Created temporary directory: {temp_dir}")
        
        # Save uploaded file
        zip_path = temp_dir / file.filename
        with open(zip_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        logger.info(f"Saved uploaded file: {zip_path} ({len(content)} bytes)")
        
        # Extract zip file
        extract_dir = temp_dir / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            logger.info(f"Extracted zip file to: {extract_dir}")
        except zipfile.BadZipFile:
            raise HTTPException(
                status_code=400,
                detail="Invalid zip file. Please ensure the file is a valid zip archive."
            )
        
        # Find JSON files in extracted directory (recursive search)
        # Filter out macOS resource fork files (._*) - these are metadata files, not valid JSON
        json_files = [f for f in extract_dir.rglob("*.json") if not f.name.startswith("._")]
        
        if not json_files:
            # Provide helpful error message showing what was actually extracted
            all_items = list(extract_dir.rglob("*"))
            dir_structure = []
            for item in sorted(all_items)[:30]:  # Show first 30 items
                rel_path = item.relative_to(extract_dir)
                if item.is_dir():
                    dir_structure.append(f"  📁 {rel_path}/")
                else:
                    dir_structure.append(f"  📄 {rel_path}")
            
            structure_msg = "\n".join(dir_structure) if dir_structure else "  (empty)"
            if len(all_items) > 30:
                structure_msg += f"\n  ... and {len(all_items) - 30} more items"
            
            raise HTTPException(
                status_code=400,
                detail=(
                    f"No JSON files found in the uploaded zip.\n\n"
                    f"Zip contents:\n{structure_msg}\n\n"
                    f"Please ensure your zip file contains processed JSON documents. "
                    f"Expected structure: JSON files directly in the zip root or in a single subdirectory."
                )
            )
        
        logger.info(f"Found {len(json_files)} JSON files in uploaded archive")
        
        # Determine the input directory for VectorPopulator
        # IMPORTANT: VectorPopulator.load_documents() uses glob("*.json") which is NOT recursive
        # So we need to find the directory that directly contains the JSON files
        json_dirs = {f.parent for f in json_files}
        
        if len(json_dirs) == 1:
            # All JSON files are in the same directory - perfect!
            input_dir = str(list(json_dirs)[0])
            logger.info(f"All JSON files in single directory: {input_dir}")
        else:
            # JSON files are in multiple directories
            # VectorPopulator only looks in one directory, so we need to pick one
            # Strategy: Use the directory with the most JSON files
            dir_counts = {}
            for json_file in json_files:
                parent = json_file.parent
                dir_counts[parent] = dir_counts.get(parent, 0) + 1
            
            # Use the directory with the most JSON files
            input_dir = str(max(dir_counts.items(), key=lambda x: x[1])[0])
            logger.warning(
                f"JSON files found in {len(json_dirs)} different directories. "
                f"Using directory with most files: {input_dir} ({dir_counts[Path(input_dir)]} files). "
                f"Other directories will be ignored."
            )
        
        # Verify the input_dir actually contains JSON files (non-recursive check)
        # This matches what VectorPopulator.load_documents() does
        input_path = Path(input_dir)
        json_files_in_input = list(input_path.glob("*.json"))
        
        if not json_files_in_input:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Selected input directory '{input_dir}' does not contain JSON files at the root level.\n\n"
                    f"VectorPopulator requires JSON files to be directly in the input directory (not in subdirectories).\n\n"
                    f"Found JSON files in these locations:\n" +
                    "\n".join([f"  - {f.relative_to(extract_dir)}" for f in list(json_files)[:10]]) +
                    (f"\n  ... and {len(json_files) - 10} more" if len(json_files) > 10 else "") +
                    f"\n\nTip: When creating the zip, ensure JSON files are in a flat structure or a single subdirectory."
                )
            )
        
        logger.info(f"Using input directory: {input_dir} (contains {len(json_files_in_input)} JSON files directly)")
        
        # Get settings for defaults
        # Handle form data: if provider/model are None or empty strings, use settings defaults
        # Also filter out invalid values like "string" (which can come from form parsing issues)
        valid_providers = ["huggingface", "openai"]
        final_provider = None
        if provider and provider.strip() and provider.lower() in valid_providers:
            final_provider = provider.lower()
        else:
            final_provider = settings.embeddings.provider
        
        final_model = (model.strip() if model and model.strip() else None) or settings.embeddings.model
        
        # Handle batch_size: None or 0 means use default
        final_batch_size = batch_size if batch_size and batch_size > 0 else settings.embeddings.batch_size
        
        # Handle distance: validate against allowed values
        valid_distances = ["Cosine", "Euclid", "Dot"]
        final_distance = distance if distance and distance in valid_distances else settings.qdrant.distance
        
        # Handle normalize: None means use default based on provider
        final_normalize = normalize if normalize is not None else (final_provider == "huggingface")
        
        request_data = {
            "input_dir": input_dir,
            "collection_name": collection,
            "provider": final_provider,
            "model": final_model,
            "batch_size": final_batch_size,
            "distance": final_distance,
            "normalize": final_normalize,
            "recreate": recreate,
            "temp_dir": str(temp_dir),  # Store for cleanup
        }
        
        logger.info(f"Indexing configuration: provider={final_provider}, model={final_model}, batch_size={final_batch_size}, distance={final_distance}, normalize={final_normalize}")
        
        # Store job info
        services.index_jobs[job_id] = {
            "status": "pending",
            "progress": 0.0,
            "message": "Upload received, starting extraction...",
            "request": request_data,
            "started_at": datetime.utcnow().isoformat(),
            "upload_info": {
                "filename": file.filename,
                "size_bytes": len(content),
                "json_files_count": len(json_files),
            }
        }
        
        # Start indexing in background
        asyncio.create_task(_run_index_job_with_cleanup(job_id, request_data))
        
        return IndexResponse(
            job_id=job_id,
            status="pending",
            message=f"Upload received ({len(json_files)} JSON files). Indexing started. Use /api/v1/index/status/{job_id} to check progress.",
            input_dir=input_dir,
            collection_name=collection,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in upload_and_index: {str(e)}")
        # Cleanup on error
        if temp_dir and temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
                logger.info(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup temp directory: {cleanup_error}")
        
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}",
        )


async def _run_index_job_with_cleanup(job_id: str, request_data: dict) -> None:
    """Run indexing job with automatic cleanup of temporary files."""
    temp_dir = request_data.get("temp_dir")
    
    try:
        # Update status
        services.index_jobs[job_id]["status"] = "running"
        services.index_jobs[job_id]["message"] = "Loading documents..."
        services.index_jobs[job_id]["progress"] = 10.0
        
        # Run the indexing job (same as _run_index_job)
        populator = VectorPopulator(
            input_dir=Path(request_data["input_dir"]),
            collection_name=request_data["collection_name"],
            embedding_provider=request_data["provider"],
            embedding_model=request_data["model"],
            batch_size=request_data["batch_size"],
            distance=request_data["distance"],
            normalize_embeddings=request_data["normalize"],
        )
        
        services.index_jobs[job_id]["message"] = "Generating embeddings..."
        services.index_jobs[job_id]["progress"] = 30.0
        
        # Run blocking populate() in thread pool
        await asyncio.to_thread(populator.populate, recreate=request_data["recreate"])
        
        services.index_jobs[job_id]["status"] = "completed"
        services.index_jobs[job_id]["progress"] = 100.0
        services.index_jobs[job_id]["message"] = "Indexing completed successfully"
        services.index_jobs[job_id]["completed_at"] = datetime.utcnow().isoformat()
        
        # Get collection info
        qdrant = QdrantManager(collection_name=request_data["collection_name"])
        info = qdrant.get_collection_info()
        services.index_jobs[job_id]["result"] = {
            "collection_info": info,
            "collection_name": request_data["collection_name"],
        }
        
    except Exception as e:
        logger.exception(f"Error in index job {job_id}: {str(e)}")
        services.index_jobs[job_id]["status"] = "failed"
        services.index_jobs[job_id]["message"] = f"Indexing failed: {str(e)}"
        services.index_jobs[job_id]["error"] = str(e)
    
    finally:
        # Cleanup temporary directory
        if temp_dir:
            temp_path = Path(temp_dir)
            if temp_path.exists():
                try:
                    shutil.rmtree(temp_path)
                    logger.info(f"Cleaned up temporary directory: {temp_path}")
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup temp directory {temp_path}: {cleanup_error}")



# ===== ADDITIONAL HEALTH AND STATUS ENDPOINTS =====

@app.get("/api/v1/health/qdrant", tags=["health"])
async def qdrant_ping() -> dict:
    """Simple ping to check if Qdrant container is up and responding."""
    try:
        qdrant = QdrantManager()
        
        # Simple ping - just try to get collections (minimal operation)
        collections_response = qdrant.client.get_collections()
        
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "message": "Qdrant is responding",
            "collections_count": len(collections_response.collections) if collections_response else 0,
        }
    
    except Exception as e:
        logger.warning(f"Qdrant ping failed: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail=f"Qdrant unavailable: {str(e)}",
        )


@app.get("/api/v1/system/status", tags=["health"])
async def system_status(container: ServiceContainer = Depends(get_services)) -> dict:
    """Get comprehensive system status including all components."""
    try:
        status = {
            "timestamp": datetime.utcnow().isoformat(),
            "version": "0.1.0",
            "components": {},
            "overall_status": "unknown",
        }
        
        healthy_components = 0
        total_components = 0
        
        # Check Qdrant
        total_components += 1
        try:
            qdrant = QdrantManager()
            collections = qdrant.client.get_collections()
            collection_info = qdrant.get_collection_info()
            status["components"]["qdrant"] = {
                "status": "healthy",
                "collections_count": len(collections.collections),
                "current_collection": qdrant.collection_name,
                "points_count": collection_info.get("points_count", 0),
            }
            healthy_components += 1
        except Exception as e:
            status["components"]["qdrant"] = {
                "status": "unhealthy",
                "error": str(e)[:100],
            }
        
        # Check Retriever
        total_components += 1
        try:
            retriever = container.get_retriever()
            status["components"]["retriever"] = {
                "status": "healthy",
                "provider": retriever.embed_provider,
                "model": retriever.embed_model_name,
                "collection": retriever.qdrant.collection_name,
                "reranking_enabled": retriever.reranker_enabled,
                "hybrid_search_enabled": retriever.hybrid_search_enabled,
            }
            healthy_components += 1
        except Exception as e:
            status["components"]["retriever"] = {
                "status": "unhealthy",
                "error": str(e)[:100],
            }
        
        # Check LLM
        total_components += 1
        try:
            llm = container.get_llm()
            status["components"]["llm"] = {
                "status": "healthy",
                "model": getattr(llm, 'model', 'unknown'),
                "provider": getattr(llm, 'provider', 'unknown'),
            }
            healthy_components += 1
        except Exception as e:
            status["components"]["llm"] = {
                "status": "unhealthy",
                "error": str(e)[:100],
            }
        
        # Check Agent (currently always available via RouterAgent)
        total_components += 1
        try:
            agent = container.get_agent()
            status["components"]["agent"] = {
                "status": "healthy",
                "collection": agent.retriever.qdrant.collection_name,
            }
            healthy_components += 1
        except Exception as e:
            status["components"]["agent"] = {
                "status": "unhealthy",
                "error": str(e)[:100],
            }
        
        # Determine overall status
        health_ratio = healthy_components / total_components
        if health_ratio >= 0.8:
            status["overall_status"] = "healthy"
        elif health_ratio >= 0.5:
            status["overall_status"] = "degraded"
        else:
            status["overall_status"] = "unhealthy"
        
        status["health_summary"] = {
            "healthy_components": healthy_components,
            "total_components": total_components,
            "health_ratio": health_ratio,
        }
        
        return status
    
    except Exception as e:
        logger.exception(f"System status check failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"System status check failed: {str(e)}",
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host=settings.api.host,
        port=settings.api.port,
        reload=True,
    )

