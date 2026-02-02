"""Unit tests for API main module - dependencies, services, and utilities."""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from fastapi import HTTPException

from src.api.main import (
    ServiceContainer,
    get_services,
    verify_collection_exists,
    get_retriever_service,
    get_llm_service,
    get_agent_service,
)


class TestServiceContainer:
    """Test suite for ServiceContainer."""
    
    @pytest.fixture
    def mock_settings(self):
        """Mock settings."""
        mock_settings = Mock()
        mock_settings.llm.provider = "anthropic"
        mock_settings.llm.model = "claude-3-haiku"
        mock_settings.llm.temperature = 0.1
        mock_settings.llm.max_tokens = 4096
        mock_settings.llm.streaming = False
        mock_settings.llm.prompt_caching = False
        return mock_settings
    
    @patch('src.api.main.get_settings')
    def test_service_container_initialization(self, mock_get_settings, mock_settings):
        """Test ServiceContainer initialization."""
        mock_get_settings.return_value = mock_settings
        
        container = ServiceContainer()
        
        assert container.agent is None
        assert container.retriever is None
        assert container.llm_wrapper is None
        assert container.index_jobs == {}
    
    @patch('src.api.main.get_settings')
    @patch('src.api.main.AdvancedRetriever')
    def test_get_retriever_default(self, mock_retriever_class, mock_get_settings, mock_settings):
        """Test getting default retriever."""
        mock_get_settings.return_value = mock_settings
        mock_retriever = Mock()
        mock_retriever_class.return_value = mock_retriever
        
        container = ServiceContainer()
        retriever = container.get_retriever()
        
        assert retriever == mock_retriever
        assert container.retriever == mock_retriever
    
    @patch('src.api.main.get_settings')
    @patch('src.api.main.AdvancedRetriever')
    def test_get_retriever_with_collection(self, mock_retriever_class, mock_get_settings, mock_settings):
        """Test getting retriever for specific collection."""
        mock_get_settings.return_value = mock_settings
        mock_retriever = Mock()
        mock_retriever_class.return_value = mock_retriever
        
        container = ServiceContainer()
        retriever = container.get_retriever(collection_name="test_collection")
        
        assert retriever == mock_retriever
        mock_retriever_class.assert_called_with(collection_name="test_collection")
    
    @patch('src.api.main.get_settings')
    @patch('src.api.main.get_llm')
    def test_get_llm_default(self, mock_get_llm, mock_get_settings, mock_settings):
        """Test getting default LLM."""
        mock_get_settings.return_value = mock_settings
        mock_llm = Mock()
        mock_get_llm.return_value = mock_llm
        
        container = ServiceContainer()
        llm = container.get_llm()
        
        assert llm == mock_llm
        assert container.llm_wrapper == mock_llm
    
    @patch('src.api.main.get_settings')
    @patch('src.api.main.AdvancedRetriever')
    @patch('src.api.main.RouterAgent')
    def test_get_agent_default(self, mock_agent_class, mock_retriever_class, mock_get_settings, mock_settings):
        """Test getting default agent."""
        mock_get_settings.return_value = mock_settings
        mock_retriever = Mock()
        mock_retriever_class.return_value = mock_retriever
        mock_agent = Mock()
        mock_agent_class.return_value = mock_agent
        
        container = ServiceContainer()
        agent = container.get_agent()
        
        assert agent == mock_agent
        assert container.agent == mock_agent
    
    @patch('src.api.main.get_settings')
    @patch('src.api.main.AdvancedRetriever')
    @patch('src.api.main.RouterAgent')
    def test_get_agent_with_collection(self, mock_agent_class, mock_retriever_class, mock_get_settings, mock_settings):
        """Test getting agent for specific collection."""
        mock_get_settings.return_value = mock_settings
        mock_retriever = Mock()
        mock_retriever_class.return_value = mock_retriever
        mock_agent = Mock()
        mock_agent_class.return_value = mock_agent
        
        container = ServiceContainer()
        agent = container.get_agent(collection_name="test_collection")
        
        assert agent == mock_agent
        mock_agent_class.assert_called_with(retriever=mock_retriever, collection_name="test_collection")
    
    @patch('src.api.main.get_settings')
    @patch('src.api.main.AdvancedRetriever')
    @patch('src.api.main.get_llm')
    @pytest.mark.asyncio
    async def test_warmup_models_success(self, mock_get_llm, mock_retriever_class, mock_get_settings, mock_settings):
        """Test successful model warmup."""
        mock_get_settings.return_value = mock_settings
        mock_retriever = Mock()
        mock_retriever_class.return_value = mock_retriever
        mock_llm = Mock()
        mock_get_llm.return_value = mock_llm
        
        container = ServiceContainer()
        await container.warmup_models()
        
        # Should have loaded retriever and LLM
        assert container.retriever is not None
        assert container.llm_wrapper is not None
    
    @patch('src.api.main.get_settings')
    @patch('src.api.main.AdvancedRetriever')
    @pytest.mark.asyncio
    async def test_warmup_models_failure(self, mock_retriever_class, mock_get_settings, mock_settings):
        """Test model warmup with failure."""
        mock_get_settings.return_value = mock_settings
        mock_retriever_class.side_effect = Exception("Model load failed")
        
        container = ServiceContainer()
        # Should not raise, just log error
        await container.warmup_models()
        
        # Retriever should still be None due to error
        assert container.retriever is None


class TestDependencyFunctions:
    """Test suite for dependency injection functions."""
    
    def test_get_services(self):
        """Test get_services returns service container."""
        from src.api.main import services
        result = get_services()
        assert result == services
    
    @patch('src.db.qdrant_client.QdrantClient')
    def test_verify_collection_exists_success(self, mock_qdrant_client_class):
        """Test verify_collection_exists when collection exists."""
        # Mock the QdrantClient instance
        mock_client = Mock()
        mock_client.collection_exists.return_value = True
        mock_qdrant_client_class.return_value = mock_client
        
        # Should not raise
        verify_collection_exists("test_collection")
    
    @patch('src.db.qdrant_client.QdrantClient')
    def test_verify_collection_exists_not_found(self, mock_qdrant_client_class):
        """Test verify_collection_exists when collection doesn't exist."""
        # Mock the QdrantClient instance
        mock_client = Mock()
        mock_client.collection_exists.return_value = False
        mock_collection = Mock()
        mock_collection.name = "existing_collection"
        mock_client.get_collections.return_value = Mock(collections=[mock_collection])
        mock_qdrant_client_class.return_value = mock_client
        
        with pytest.raises(HTTPException) as exc_info:
            verify_collection_exists("nonexistent_collection")
        
        assert exc_info.value.status_code == 404
        assert "nonexistent_collection" in str(exc_info.value.detail)
    
    @patch('src.db.qdrant_client.QdrantClient')
    def test_verify_collection_exists_error_getting_collections(self, mock_qdrant_client_class):
        """Test verify_collection_exists when get_collections fails."""
        # Mock the QdrantClient instance
        mock_client = Mock()
        mock_client.collection_exists.return_value = False
        mock_client.get_collections.side_effect = Exception("Connection error")
        mock_qdrant_client_class.return_value = mock_client
        
        with pytest.raises(HTTPException) as exc_info:
            verify_collection_exists("test_collection")
        
        assert exc_info.value.status_code == 404
    
    @patch('src.api.main.verify_collection_exists')
    @patch('src.api.main.get_services')
    def test_get_retriever_service_with_collection(self, mock_get_services, mock_verify):
        """Test get_retriever_service with collection parameter."""
        mock_container = Mock()
        mock_retriever = Mock()
        mock_container.get_retriever.return_value = mock_retriever
        mock_get_services.return_value = mock_container
        
        result = get_retriever_service(collection="test_collection", container=mock_container)
        
        assert result == mock_retriever
        mock_verify.assert_called_once_with("test_collection")
        mock_container.get_retriever.assert_called_once_with("test_collection")
    
    @patch('src.api.main.get_services')
    def test_get_retriever_service_without_collection(self, mock_get_services):
        """Test get_retriever_service without collection parameter."""
        mock_container = Mock()
        mock_retriever = Mock()
        mock_container.get_retriever.return_value = mock_retriever
        mock_get_services.return_value = mock_container
        
        result = get_retriever_service(collection=None, container=mock_container)
        
        assert result == mock_retriever
        mock_container.get_retriever.assert_called_once_with(None)
    
    @patch('src.api.main.verify_collection_exists')
    @patch('src.api.main.get_services')
    def test_get_retriever_service_collection_not_found(self, mock_get_services, mock_verify):
        """Test get_retriever_service when collection doesn't exist."""
        mock_container = Mock()
        mock_get_services.return_value = mock_container
        mock_verify.side_effect = HTTPException(status_code=404, detail="Not found")
        
        with pytest.raises(HTTPException) as exc_info:
            get_retriever_service(collection="nonexistent", container=mock_container)
        
        assert exc_info.value.status_code == 404
    
    @patch('src.api.main.get_services')
    def test_get_retriever_service_error(self, mock_get_services):
        """Test get_retriever_service when get_retriever fails."""
        mock_container = Mock()
        mock_container.get_retriever.side_effect = Exception("Initialization failed")
        mock_get_services.return_value = mock_container
        
        with pytest.raises(HTTPException) as exc_info:
            get_retriever_service(collection=None, container=mock_container)
        
        assert exc_info.value.status_code == 503
    
    @patch('src.api.main.get_services')
    def test_get_llm_service_success(self, mock_get_services):
        """Test get_llm_service success."""
        mock_container = Mock()
        mock_llm = Mock()
        mock_container.get_llm.return_value = mock_llm
        mock_get_services.return_value = mock_container
        
        result = get_llm_service(container=mock_container)
        
        assert result == mock_llm
    
    @patch('src.api.main.get_services')
    def test_get_llm_service_error(self, mock_get_services):
        """Test get_llm_service when get_llm fails."""
        mock_container = Mock()
        mock_container.get_llm.side_effect = Exception("LLM initialization failed")
        mock_get_services.return_value = mock_container
        
        with pytest.raises(HTTPException) as exc_info:
            get_llm_service(container=mock_container)
        
        assert exc_info.value.status_code == 503
    
    @patch('src.api.main.verify_collection_exists')
    @patch('src.api.main.get_services')
    def test_get_agent_service_with_collection(self, mock_get_services, mock_verify):
        """Test get_agent_service with collection parameter."""
        mock_container = Mock()
        mock_agent = Mock()
        mock_container.get_agent.return_value = mock_agent
        mock_get_services.return_value = mock_container
        
        result = get_agent_service(collection="test_collection", container=mock_container)
        
        assert result == mock_agent
        mock_verify.assert_called_once_with("test_collection")
        mock_container.get_agent.assert_called_once_with("test_collection")
    
    @patch('src.api.main.get_services')
    def test_get_agent_service_without_collection(self, mock_get_services):
        """Test get_agent_service without collection parameter."""
        mock_container = Mock()
        mock_agent = Mock()
        mock_container.get_agent.return_value = mock_agent
        mock_get_services.return_value = mock_container
        
        result = get_agent_service(collection=None, container=mock_container)
        
        assert result == mock_agent
        mock_container.get_agent.assert_called_once_with(None)
    
    @patch('src.api.main.get_services')
    def test_get_agent_service_error(self, mock_get_services):
        """Test get_agent_service when get_agent fails."""
        mock_container = Mock()
        mock_container.get_agent.side_effect = Exception("Agent initialization failed")
        mock_get_services.return_value = mock_container
        
        with pytest.raises(HTTPException) as exc_info:
            get_agent_service(collection=None, container=mock_container)
        
        assert exc_info.value.status_code == 503

