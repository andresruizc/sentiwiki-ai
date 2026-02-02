"""Shared fixtures for tests."""

import os
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

# Set test environment variables before imports
os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["OPENAI_API_KEY"] = "test-key"
os.environ["LANGCHAIN_API_KEY"] = "test-key"

from src.api.main import app
from src.retrieval.retriever import AdvancedRetriever
from src.agents.router_agent import RouterAgent
from src.db.qdrant_client import QdrantManager


@pytest.fixture
def test_app() -> FastAPI:
    """Return the FastAPI app for testing."""
    return app


@pytest.fixture
async def client(test_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client for the API."""
    # Use ASGITransport to connect AsyncClient to FastAPI app
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def mock_qdrant_client() -> Mock:
    """Create a mock Qdrant client."""
    mock_client = Mock()
    mock_client.get_collections.return_value = Mock(collections=[])
    mock_client.scroll.return_value = ([], None)
    mock_client.search.return_value = []
    return mock_client


@pytest.fixture
def mock_qdrant_manager(mock_qdrant_client: Mock) -> Mock:
    """Create a mock QdrantManager."""
    mock_manager = Mock(spec=QdrantManager)
    mock_manager.client = mock_qdrant_client
    mock_manager.collection_name = "test_collection"
    mock_manager.get_collection_info.return_value = {
        "points_count": 100,
        "vectors_count": 100,
    }
    return mock_manager


@pytest.fixture
def mock_embedder() -> Mock:
    """Create a mock embedder."""
    mock_embedder = Mock()
    mock_embedder.encode.return_value = [[0.1] * 1024]  # Mock embedding vector
    return mock_embedder


@pytest.fixture
def mock_reranker() -> Mock:
    """Create a mock reranker."""
    mock_reranker = Mock()
    mock_reranker.predict.return_value = [0.9, 0.8, 0.7]  # Mock scores
    return mock_reranker


@pytest.fixture
def mock_retriever(
    mock_qdrant_manager: Mock, mock_embedder: Mock, mock_reranker: Mock
) -> Mock:
    """Create a mock AdvancedRetriever."""
    mock_retriever = Mock(spec=AdvancedRetriever)
    mock_retriever.qdrant = mock_qdrant_manager
    mock_retriever.embedder = mock_embedder
    mock_retriever.reranker = mock_reranker
    mock_retriever.top_k_default = 10
    mock_retriever.reranker_enabled = True
    mock_retriever.hybrid_search_enabled = True
    mock_retriever.metadata_filtering_enabled = True
    
    # Mock retrieve method
    mock_retriever.retrieve.return_value = [
        {
            "text": "Test document 1",
            "score": 0.9,
            "metadata": {"mission": "S1", "title": "Test Doc 1"},
        },
        {
            "text": "Test document 2",
            "score": 0.8,
            "metadata": {"mission": "S2", "title": "Test Doc 2"},
        },
    ]
    
    return mock_retriever


@pytest.fixture
def mock_llm_service() -> Mock:
    """Create a mock LLM service."""
    mock_llm = Mock()
    mock_llm.model = "test-model"
    mock_llm.generate.return_value = "Test response from LLM"
    
    async def async_generate(*args, **kwargs):
        return "Test response from LLM"
    
    mock_llm.generate_async = AsyncMock(return_value="Test response from LLM")
    
    async def async_stream(*args, **kwargs):
        chunks = ["Test", " response", " from", " LLM"]
        for chunk in chunks:
            yield chunk
    
    mock_llm.stream = AsyncMock(side_effect=async_stream)
    
    return mock_llm


@pytest.fixture
def mock_router_agent(
    mock_retriever: Mock, mock_llm_service: Mock
) -> Mock:
    """Create a mock RouterAgent."""
    mock_agent = Mock(spec=RouterAgent)
    mock_agent.retriever = mock_retriever
    mock_agent.router_llm = mock_llm_service
    mock_agent.rag_llm = mock_llm_service
    mock_agent.direct_llm = mock_llm_service
    
    # Mock process method - returns RAG by default
    # Can be overridden in individual tests
    async def async_process(query: str, **kwargs):
        return {
            "query": query,
            "route": "RAG",
            "answer": "Test answer",
            "sources": [
                {
                    "title": "Test Doc 1",
                    "url": "http://test.com/doc1",
                    "heading": "Test Heading",
                    "score": 0.9,
                }
            ],
            "context": "Test context",
            "metadata": {"duration_seconds": 0.5},
        }
    
    # Use AsyncMock so it can be overridden in tests
    mock_agent.process = AsyncMock(side_effect=async_process)
    
    # Mock process_stream method - must be async generator, not coroutine
    async def async_process_stream(query: str, **kwargs):
        chunks = [
            {"type": "route", "data": "RAG"},
            {"type": "chunk", "data": "Test"},
            {"type": "chunk", "data": " answer"},
        ]
        for chunk in chunks:
            yield chunk
    
    # Create async generator function
    mock_agent.process_stream = async_process_stream
    
    return mock_agent


@pytest.fixture
def sample_documents() -> list[dict]:
    """Sample documents for testing."""
    return [
        {
            "text": "Sentinel-1 is a radar imaging mission.",
            "score": 0.95,
            "metadata": {
                "mission": "S1",
                "title": "Sentinel-1 Overview",
                "url": "https://sentiwiki.copernicus.eu/s1",
            },
        },
        {
            "text": "Sentinel-2 provides multi-spectral optical imaging.",
            "score": 0.90,
            "metadata": {
                "mission": "S2",
                "title": "Sentinel-2 Overview",
                "url": "https://sentiwiki.copernicus.eu/s2",
            },
        },
        {
            "text": "Sentinel-3 monitors ocean and land.",
            "score": 0.85,
            "metadata": {
                "mission": "S3",
                "title": "Sentinel-3 Overview",
                "url": "https://sentiwiki.copernicus.eu/s3",
            },
        },
    ]


@pytest.fixture(autouse=True)
def mock_qdrant_client_globally():
    """Automatically mock QdrantClient for all tests to prevent connection attempts."""
    with patch('src.db.qdrant_client.QdrantClient') as mock_client_class:
        # Create a mock client instance
        mock_client = Mock()
        # Default: collection doesn't exist (for tests expecting 404)
        mock_client.collection_exists.return_value = False
        mock_client.get_collections.return_value = Mock(collections=[])
        mock_client.get_collection.return_value = Mock(
            status="green",
            points_count=0,
            vectors_count=0,
        )
        mock_client.delete_collection.return_value = None
        mock_client.create_collection.return_value = None
        mock_client.scroll.return_value = ([], None)
        mock_client.search.return_value = []
        mock_client.query_points.return_value = Mock(points=[])
        
        # Make the class return our mock instance
        mock_client_class.return_value = mock_client
        
        yield mock_client


@pytest.fixture(autouse=True)
def reset_environment():
    """Reset environment variables before each test."""
    # Store original values
    original_env = {}
    for key in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "LANGCHAIN_API_KEY"]:
        original_env[key] = os.environ.get(key)
    
    yield
    
    # Restore original values
    for key, value in original_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

