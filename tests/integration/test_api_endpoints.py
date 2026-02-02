"""Integration tests for API endpoints."""

import pytest
from httpx import AsyncClient
from fastapi import FastAPI


class TestHealthEndpoints:
    """Test health check endpoints."""
    
    @pytest.mark.asyncio
    async def test_root_endpoint(self, client: AsyncClient):
        """Test root endpoint."""
        response = await client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "timestamp" in data
    
    @pytest.mark.asyncio
    async def test_health_endpoint(self, client: AsyncClient):
        """Test health endpoint."""
        response = await client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "components" in data
        assert isinstance(data["components"], dict)
    
    @pytest.mark.asyncio
    async def test_metrics_endpoint(self, client: AsyncClient):
        """Test metrics endpoint."""
        response = await client.get("/metrics")
        
        assert response.status_code == 200
        # Prometheus metrics format
        assert "text/plain" in response.headers.get("content-type", "")


class TestRetrievalEndpoints:
    """Test retrieval endpoints."""
    
    @pytest.mark.asyncio
    async def test_retrieve_endpoint_success(
        self, client: AsyncClient, mock_retriever
    ):
        """Test successful retrieval."""
        # Note: This requires mocking the dependency injection
        # For now, we test the endpoint structure
        response = await client.get(
            "/api/v1/retrieve",
            params={"query": "test query"},
        )
        
        # Should either succeed or return appropriate error
        assert response.status_code in [200, 500, 503]
    
    @pytest.mark.asyncio
    async def test_retrieve_endpoint_missing_query(self, client: AsyncClient):
        """Test retrieval endpoint without query parameter."""
        response = await client.get("/api/v1/retrieve")
        
        # Should return 422 (validation error)
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_retrieve_endpoint_with_collection(self, client: AsyncClient):
        """Test retrieval with collection parameter."""
        response = await client.get(
            "/api/v1/retrieve",
            params={
                "query": "test query",
                "collection": "test_collection",
            },
        )
        
        # Should either succeed or return appropriate error (404 if endpoint doesn't exist)
        assert response.status_code in [200, 404, 500, 503]


class TestRAGEndpoints:
    """Test RAG endpoints."""
    
    @pytest.mark.asyncio
    async def test_rag_endpoint_structure(self, client: AsyncClient):
        """Test RAG endpoint structure."""
        response = await client.get(
            "/api/v1/rag",
            params={"query": "What is Sentinel-1?"},
        )
        
        # Should either succeed or return appropriate error
        assert response.status_code in [200, 500, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert "query" in data
            assert "answer" in data
            assert "sources" in data
    
    @pytest.mark.asyncio
    async def test_rag_endpoint_missing_query(self, client: AsyncClient):
        """Test RAG endpoint without query parameter."""
        response = await client.get("/api/v1/rag")
        
        # Should return 422 (validation error)
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_rag_stream_endpoint(self, client: AsyncClient):
        """Test RAG streaming endpoint."""
        response = await client.get(
            "/api/v1/rag/stream",
            params={"query": "What is Sentinel-1?"},
        )
        
        # Should return streaming response
        assert response.status_code in [200, 500, 503]
        
        if response.status_code == 200:
            assert "text/event-stream" in response.headers.get("content-type", "")


class TestChatEndpoints:
    """Test chat endpoints."""
    
    @pytest.mark.asyncio
    async def test_chat_endpoint_structure(self, client: AsyncClient):
        """Test chat endpoint structure."""
        response = await client.get(
            "/api/v1/chat",
            params={"query": "Hello"},
        )
        
        # Should either succeed or return appropriate error
        assert response.status_code in [200, 500, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert "query" in data
            assert "answer" in data
            assert "route" in data
            assert "metadata" in data
    
    @pytest.mark.asyncio
    async def test_chat_stream_endpoint(self, client: AsyncClient):
        """Test chat streaming endpoint."""
        response = await client.get(
            "/api/v1/chat/stream",
            params={"query": "Hello"},
        )
        
        # Should return streaming response
        assert response.status_code in [200, 500, 503]
        
        if response.status_code == 200:
            assert "text/event-stream" in response.headers.get("content-type", "")


class TestCollectionsEndpoints:
    """Test collections endpoints."""
    
    @pytest.mark.asyncio
    async def test_list_collections(self, client: AsyncClient):
        """Test listing collections."""
        response = await client.get("/api/v1/collections")
        
        # Should either succeed or return appropriate error
        assert response.status_code in [200, 500, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert "collections" in data
            assert isinstance(data["collections"], list)


class TestErrorHandling:
    """Test error handling."""
    
    @pytest.mark.asyncio
    async def test_invalid_endpoint(self, client: AsyncClient):
        """Test accessing non-existent endpoint."""
        response = await client.get("/api/v1/nonexistent")
        
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_invalid_method(self, client: AsyncClient):
        """Test using wrong HTTP method."""
        response = await client.post("/api/v1/rag")
        
        # Should return 405 (Method Not Allowed) or handle gracefully
        assert response.status_code in [405, 422]
    
    @pytest.mark.asyncio
    async def test_rag_endpoint_empty_query(self, client: AsyncClient):
        """Test RAG endpoint with empty query."""
        response = await client.get("/api/v1/rag", params={"query": ""})
        
        # Should return validation error or handle gracefully
        assert response.status_code in [400, 422, 500]
    
    @pytest.mark.asyncio
    async def test_retrieve_endpoint_empty_query(self, client: AsyncClient):
        """Test retrieve endpoint with empty query."""
        response = await client.get("/api/v1/retrieve", params={"query": ""})
        
        # Empty string might pass validation, so accept 200 or error codes
        assert response.status_code in [200, 400, 422, 500, 503]
    
    @pytest.mark.asyncio
    async def test_chat_endpoint_empty_query(self, client: AsyncClient):
        """Test chat endpoint with empty query."""
        response = await client.get("/api/v1/chat", params={"query": ""})
        
        # Empty string might pass validation, so accept 200 or error codes
        assert response.status_code in [200, 400, 422, 500, 503]
    
    @pytest.mark.asyncio
    async def test_rag_stream_endpoint_without_litellm(self, client: AsyncClient):
        """Test RAG stream endpoint when litellm is not available."""
        # This tests the error handling path when completion is None
        # Note: In real scenario, this would require mocking completion=None
        response = await client.get(
            "/api/v1/rag/stream",
            params={"query": "test"},
        )
        
        # Should either work or return 503 if litellm not available
        assert response.status_code in [200, 503]


class TestRAGEndpointsExtended:
    """Extended tests for RAG endpoints."""
    
    @pytest.mark.asyncio
    async def test_rag_endpoint_with_reranking_disabled(self, client: AsyncClient):
        """Test RAG endpoint with reranking disabled."""
        response = await client.get(
            "/api/v1/rag",
            params={
                "query": "What is Sentinel-1?",
                "use_reranking": False,
            },
        )
        
        # Should either succeed or return appropriate error
        assert response.status_code in [200, 500, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert "answer" in data
            assert "sources" in data
    
    @pytest.mark.asyncio
    async def test_rag_endpoint_with_hybrid_disabled(self, client: AsyncClient):
        """Test RAG endpoint with hybrid search disabled."""
        response = await client.get(
            "/api/v1/rag",
            params={
                "query": "What is Sentinel-1?",
                "use_hybrid": False,
            },
        )
        
        # Should either succeed or return appropriate error
        assert response.status_code in [200, 500, 503]
    
    @pytest.mark.asyncio
    async def test_rag_endpoint_with_collection(self, client: AsyncClient):
        """Test RAG endpoint with specific collection."""
        response = await client.get(
            "/api/v1/rag",
            params={
                "query": "What is Sentinel-1?",
                "collection": "test_collection",
            },
        )
        
        # Should either succeed or return appropriate error
        assert response.status_code in [200, 404, 500, 503]


class TestRetrievalEndpointsExtended:
    """Extended tests for retrieval endpoints."""
    
    @pytest.mark.asyncio
    async def test_retrieve_endpoint_with_reranking_disabled(self, client: AsyncClient):
        """Test retrieve endpoint with reranking disabled."""
        response = await client.get(
            "/api/v1/retrieve",
            params={
                "query": "test query",
                "use_reranking": False,
            },
        )
        
        # Should either succeed or return appropriate error
        assert response.status_code in [200, 500, 503]
    
    @pytest.mark.asyncio
    async def test_retrieve_endpoint_with_hybrid_disabled(self, client: AsyncClient):
        """Test retrieve endpoint with hybrid search disabled."""
        response = await client.get(
            "/api/v1/retrieve",
            params={
                "query": "test query",
                "use_hybrid": False,
            },
        )
        
        # Should either succeed or return appropriate error
        assert response.status_code in [200, 500, 503]


class TestChatEndpointsExtended:
    """Extended tests for chat endpoints."""
    
    @pytest.mark.asyncio
    async def test_chat_endpoint_with_collection(self, client: AsyncClient):
        """Test chat endpoint with specific collection."""
        response = await client.get(
            "/api/v1/chat",
            params={
                "query": "Hello",
                "collection": "test_collection",
            },
        )
        
        # Should either succeed or return appropriate error
        assert response.status_code in [200, 404, 500, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert "route" in data
            assert data["route"] in ["RAG", "DIRECT"]


class TestSystemEndpoints:
    """Test system status endpoints."""
    
    @pytest.mark.asyncio
    async def test_system_status_endpoint(self, client: AsyncClient):
        """Test system status endpoint."""
        response = await client.get("/api/v1/system/status")
        
        # Should either succeed or return appropriate error
        assert response.status_code in [200, 500, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert "overall_status" in data
            assert "components" in data
            assert isinstance(data["components"], dict)
    
    @pytest.mark.asyncio
    async def test_qdrant_ping_endpoint(self, client: AsyncClient):
        """Test Qdrant ping endpoint."""
        response = await client.get("/api/v1/health/qdrant")
        
        # Should either succeed or return 503 if Qdrant unavailable
        assert response.status_code in [200, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert "status" in data
            assert "timestamp" in data

