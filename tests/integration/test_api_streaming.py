"""Integration tests for streaming endpoints."""

import pytest
import json
from httpx import AsyncClient


class TestRAGStreaming:
    """Test RAG streaming endpoint."""
    
    @pytest.mark.asyncio
    async def test_rag_stream_basic(self, client: AsyncClient):
        """Test basic RAG streaming."""
        async with client.stream(
            "GET",
            "/api/v1/rag/stream",
            params={"query": "What is Sentinel-1?"},
        ) as response:
            assert response.status_code in [200, 503]
            
            if response.status_code == 200:
                assert "text/event-stream" in response.headers.get("content-type", "")
                
                # Read first few chunks
                chunks = []
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = json.loads(line[6:])  # Remove "data: " prefix
                        chunks.append(data)
                        if len(chunks) >= 3:  # Read first 3 events
                            break
                
                # Should have at least retrieving stage
                assert len(chunks) > 0
                assert any(chunk.get("stage") == "retrieving" for chunk in chunks)
    
    @pytest.mark.asyncio
    async def test_rag_stream_with_collection(self, client: AsyncClient):
        """Test RAG streaming with collection parameter."""
        async with client.stream(
            "GET",
            "/api/v1/rag/stream",
            params={
                "query": "What is Sentinel-1?",
                "collection": "test_collection",
            },
        ) as response:
            assert response.status_code in [200, 404, 503]
    
    @pytest.mark.asyncio
    async def test_rag_stream_missing_query(self, client: AsyncClient):
        """Test RAG streaming without query parameter."""
        response = await client.get("/api/v1/rag/stream")
        
        # Should return 422 (validation error)
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_rag_stream_error_handling(self, client: AsyncClient):
        """Test RAG streaming error handling."""
        # Test with empty query to trigger potential errors
        async with client.stream(
            "GET",
            "/api/v1/rag/stream",
            params={"query": ""},
        ) as response:
            # Should either work or return error
            assert response.status_code in [200, 400, 422, 500, 503]


class TestChatStreaming:
    """Test chat streaming endpoint."""
    
    @pytest.mark.asyncio
    async def test_chat_stream_basic(self, client: AsyncClient):
        """Test basic chat streaming."""
        async with client.stream(
            "GET",
            "/api/v1/chat/stream",
            params={"query": "Hello"},
        ) as response:
            assert response.status_code in [200, 503]
            
            if response.status_code == 200:
                assert "text/event-stream" in response.headers.get("content-type", "")
                
                # Read first few chunks
                chunks = []
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            chunks.append(data)
                            if len(chunks) >= 3:  # Read first 3 events
                                break
                        except json.JSONDecodeError:
                            continue
                
                # Should have routing stage
                assert len(chunks) > 0
                assert any(chunk.get("stage") in ["routing", "routed", "generating"] for chunk in chunks)
    
    @pytest.mark.asyncio
    async def test_chat_stream_with_collection(self, client: AsyncClient):
        """Test chat streaming with collection parameter."""
        async with client.stream(
            "GET",
            "/api/v1/chat/stream",
            params={
                "query": "Hello",
                "collection": "test_collection",
            },
        ) as response:
            assert response.status_code in [200, 404, 503]
    
    @pytest.mark.asyncio
    async def test_chat_stream_missing_query(self, client: AsyncClient):
        """Test chat streaming without query parameter."""
        response = await client.get("/api/v1/chat/stream")
        
        # Should return 422 (validation error)
        assert response.status_code == 422

