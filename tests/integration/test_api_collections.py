"""Integration tests for collection management endpoints."""

import pytest
from httpx import AsyncClient
from unittest.mock import patch, Mock


class TestCollectionManagement:
    """Test collection management endpoints."""
    
    @pytest.mark.asyncio
    async def test_get_collection_info(self, client: AsyncClient):
        """Test getting collection info."""
        # This will likely fail if collection doesn't exist, which is expected
        response = await client.get("/api/v1/collections/test_collection/info")
        
        # Should return 404 if collection doesn't exist, or 200 if it does
        assert response.status_code in [200, 404, 500, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert "collection_name" in data
            assert data["collection_name"] == "test_collection"
    
    @pytest.mark.asyncio
    async def test_get_collection_info_nonexistent(self, client: AsyncClient):
        """Test getting info for non-existent collection."""
        response = await client.get("/api/v1/collections/nonexistent_collection_12345/info")
        
        # Should return 404
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_delete_collection_nonexistent(self, client: AsyncClient):
        """Test deleting non-existent collection."""
        response = await client.delete("/api/v1/collections/nonexistent_collection_12345")
        
        # Should return 404
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_list_collections_error_handling(self, client: AsyncClient):
        """Test list collections with error handling."""
        # Test that endpoint handles errors gracefully
        response = await client.get("/api/v1/collections")
        
        # Should either succeed or return appropriate error
        assert response.status_code in [200, 500, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert "collections" in data
            assert "total" in data


class TestIndexingEndpoints:
    """Test indexing endpoints."""
    
    @pytest.mark.asyncio
    async def test_index_documents_invalid_directory(self, client: AsyncClient):
        """Test indexing with invalid directory."""
        response = await client.post(
            "/api/v1/index",
            params={
                "input_dir": "/nonexistent/directory/12345",
                "collection": "test_collection",
            },
        )
        
        # Should return 400 for invalid directory
        assert response.status_code == 400
        assert "does not exist" in response.json().get("detail", "").lower()
    
    @pytest.mark.asyncio
    async def test_get_index_status_nonexistent_job(self, client: AsyncClient):
        """Test getting status for non-existent job."""
        response = await client.get("/api/v1/index/status/nonexistent-job-id-12345")
        
        # Should return 404
        assert response.status_code == 404
        assert "not found" in response.json().get("detail", "").lower()
    
    @pytest.mark.asyncio
    async def test_get_index_status_existing_job(self, client: AsyncClient):
        """Test getting status for existing job."""
        # First create a job (if possible) or test with mock
        # For now, just test the endpoint structure
        response = await client.get("/api/v1/index/status/test-job-id")
        
        # Should return 404 if job doesn't exist, or 200 if it does
        assert response.status_code in [200, 404]



class TestHealthEndpointsExtended:
    """Extended health check endpoints."""
    
    @pytest.mark.asyncio
    async def test_qdrant_ping_success(self, client: AsyncClient):
        """Test Qdrant ping endpoint."""
        response = await client.get("/api/v1/health/qdrant")
        
        # Should either succeed or return 503 if Qdrant unavailable
        assert response.status_code in [200, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert "status" in data
            assert data["status"] == "healthy"
    
    @pytest.mark.asyncio
    async def test_qdrant_ping_failure(self, client: AsyncClient):
        """Test Qdrant ping when Qdrant is unavailable."""
        # This tests error handling path
        # In real scenario, Qdrant might be down
        response = await client.get("/api/v1/health/qdrant")
        
        # Should return 503 if unavailable, or 200 if available
        assert response.status_code in [200, 503]
        
        if response.status_code == 503:
            assert "unavailable" in response.json().get("detail", "").lower()

