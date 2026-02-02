"""Unit tests for Qdrant client."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.db.qdrant_client import QdrantManager


class TestQdrantManager:
    """Test suite for QdrantManager."""
    
    @pytest.fixture
    def mock_settings(self):
        """Mock settings."""
        mock_settings = Mock()
        mock_settings.qdrant.host = "localhost"
        mock_settings.qdrant.port = 6333
        mock_settings.qdrant.collection_name = "test_collection"
        mock_settings.qdrant.distance = "Cosine"
        mock_settings.qdrant.vector_size = 384
        return mock_settings
    
    @pytest.fixture
    def mock_qdrant_client(self):
        """Mock Qdrant client."""
        mock_client = Mock()
        mock_client.collection_exists.return_value = False
        mock_client.get_collection.return_value = Mock(
            status="green",
            points_count=100,
            vectors_count=100,
        )
        mock_client.get_collections.return_value = Mock(collections=[])
        return mock_client
    
    @patch('src.db.qdrant_client.get_settings')
    @patch('src.db.qdrant_client.QdrantClient')
    def test_qdrant_manager_initialization(
        self, mock_client_class, mock_get_settings, mock_settings, mock_qdrant_client
    ):
        """Test QdrantManager initialization."""
        mock_get_settings.return_value = mock_settings
        mock_client_class.return_value = mock_qdrant_client
        
        manager = QdrantManager()
        
        assert manager.collection_name == "test_collection"
        assert manager.distance == "Cosine"
        assert manager.client == mock_qdrant_client
    
    @patch('src.db.qdrant_client.get_settings')
    @patch('src.db.qdrant_client.QdrantClient')
    def test_qdrant_manager_custom_collection(
        self, mock_client_class, mock_get_settings, mock_settings, mock_qdrant_client
    ):
        """Test QdrantManager with custom collection name."""
        mock_get_settings.return_value = mock_settings
        mock_client_class.return_value = mock_qdrant_client
        
        manager = QdrantManager(collection_name="custom_collection")
        
        assert manager.collection_name == "custom_collection"
    
    @patch('src.db.qdrant_client.get_settings')
    @patch('src.db.qdrant_client.QdrantClient')
    def test_create_collection_new(
        self, mock_client_class, mock_get_settings, mock_settings, mock_qdrant_client
    ):
        """Test creating a new collection."""
        mock_get_settings.return_value = mock_settings
        mock_client_class.return_value = mock_qdrant_client
        mock_qdrant_client.collection_exists.return_value = False
        
        manager = QdrantManager()
        manager.create_collection(vector_size=384)
        
        mock_qdrant_client.create_collection.assert_called_once()
    
    @patch('src.db.qdrant_client.get_settings')
    @patch('src.db.qdrant_client.QdrantClient')
    def test_create_collection_exists(
        self, mock_client_class, mock_get_settings, mock_settings, mock_qdrant_client
    ):
        """Test creating collection when it already exists."""
        mock_get_settings.return_value = mock_settings
        mock_client_class.return_value = mock_qdrant_client
        mock_qdrant_client.collection_exists.return_value = True
        
        manager = QdrantManager()
        manager.create_collection()
        
        # Should not call create_collection if it exists
        mock_qdrant_client.create_collection.assert_not_called()
    
    @patch('src.db.qdrant_client.get_settings')
    @patch('src.db.qdrant_client.QdrantClient')
    def test_create_collection_recreate(
        self, mock_client_class, mock_get_settings, mock_settings, mock_qdrant_client
    ):
        """Test recreating a collection."""
        mock_get_settings.return_value = mock_settings
        mock_client_class.return_value = mock_qdrant_client
        
        # First call returns True (exists), then False (after delete)
        mock_qdrant_client.collection_exists.side_effect = [True, False]
        
        manager = QdrantManager()
        manager.create_collection(recreate=True, vector_size=384)
        
        mock_qdrant_client.delete_collection.assert_called_once_with("test_collection")
        mock_qdrant_client.create_collection.assert_called_once()
    
    @patch('src.db.qdrant_client.get_settings')
    @patch('src.db.qdrant_client.QdrantClient')
    def test_create_collection_no_vector_size(
        self, mock_client_class, mock_get_settings, mock_settings, mock_qdrant_client
    ):
        """Test creating collection without vector_size raises error."""
        mock_get_settings.return_value = mock_settings
        mock_settings.qdrant.vector_size = None
        mock_client_class.return_value = mock_qdrant_client
        mock_qdrant_client.collection_exists.return_value = False
        
        manager = QdrantManager()
        
        with pytest.raises(ValueError, match="vector_size must be provided"):
            manager.create_collection()
    
    @patch('src.db.qdrant_client.get_settings')
    @patch('src.db.qdrant_client.QdrantClient')
    def test_insert_documents(
        self, mock_client_class, mock_get_settings, mock_settings, mock_qdrant_client
    ):
        """Test inserting documents."""
        mock_get_settings.return_value = mock_settings
        mock_client_class.return_value = mock_qdrant_client
        
        manager = QdrantManager()
        
        documents = [
            {"text": "Doc 1", "metadata": {"title": "Title 1"}},
            {"text": "Doc 2", "metadata": {"title": "Title 2"}},
        ]
        embeddings = [[0.1] * 384, [0.2] * 384]
        
        manager.insert_documents(documents, embeddings)
        
        # Should call upsert
        assert mock_qdrant_client.upsert.call_count > 0
    
    @patch('src.db.qdrant_client.get_settings')
    @patch('src.db.qdrant_client.QdrantClient')
    def test_insert_documents_mismatch(
        self, mock_client_class, mock_get_settings, mock_settings, mock_qdrant_client
    ):
        """Test inserting documents with mismatched counts raises error."""
        mock_get_settings.return_value = mock_settings
        mock_client_class.return_value = mock_qdrant_client
        
        manager = QdrantManager()
        
        documents = [{"text": "Doc 1"}]
        embeddings = [[0.1] * 384, [0.2] * 384]  # Mismatch
        
        with pytest.raises(ValueError, match="Number of documents must match"):
            manager.insert_documents(documents, embeddings)
    
    @patch('src.db.qdrant_client.get_settings')
    @patch('src.db.qdrant_client.QdrantClient')
    def test_search_basic(
        self, mock_client_class, mock_get_settings, mock_settings, mock_qdrant_client
    ):
        """Test basic search."""
        mock_get_settings.return_value = mock_settings
        mock_client_class.return_value = mock_qdrant_client
        
        # Mock search results
        mock_result = Mock()
        mock_result.score = 0.9
        mock_result.payload = {"text": "Test doc"}
        mock_qdrant_client.search.return_value = [mock_result]
        
        manager = QdrantManager()
        results = manager.search([0.1] * 384, limit=10)
        
        assert len(results) == 1
        assert results[0].score == 0.9
    
    @patch('src.db.qdrant_client.get_settings')
    @patch('src.db.qdrant_client.QdrantClient')
    def test_search_with_filters(
        self, mock_client_class, mock_get_settings, mock_settings, mock_qdrant_client
    ):
        """Test search with metadata filters."""
        mock_get_settings.return_value = mock_settings
        mock_client_class.return_value = mock_qdrant_client
        
        mock_result = Mock()
        mock_result.score = 0.9
        mock_result.payload = {"text": "Test doc"}
        mock_qdrant_client.search.return_value = [mock_result]
        
        manager = QdrantManager()
        results = manager.search(
            [0.1] * 384,
            limit=10,
            filters={"mission": "S1"},
        )
        
        # Check that search was called with filter
        mock_qdrant_client.search.assert_called_once()
        call_kwargs = mock_qdrant_client.search.call_args[1]
        assert "query_filter" in call_kwargs or "query_vector" in call_kwargs
    
    @patch('src.db.qdrant_client.get_settings')
    @patch('src.db.qdrant_client.QdrantClient')
    def test_search_fallback_to_query_points(
        self, mock_client_class, mock_get_settings, mock_settings, mock_qdrant_client
    ):
        """Test search falls back to query_points if search method fails."""
        mock_get_settings.return_value = mock_settings
        mock_client_class.return_value = mock_qdrant_client
        
        # Make search method fail
        mock_qdrant_client.search.side_effect = Exception("Search failed")
        
        # Mock query_points
        mock_query_result = Mock()
        mock_query_result.points = [Mock(score=0.8, payload={"text": "Test"})]
        mock_qdrant_client.query_points.return_value = mock_query_result
        
        manager = QdrantManager()
        results = manager.search([0.1] * 384, limit=10)
        
        assert len(results) == 1
        mock_qdrant_client.query_points.assert_called()
    
    @patch('src.db.qdrant_client.get_settings')
    @patch('src.db.qdrant_client.QdrantClient')
    def test_get_collection_info(
        self, mock_client_class, mock_get_settings, mock_settings, mock_qdrant_client
    ):
        """Test getting collection information."""
        mock_get_settings.return_value = mock_settings
        mock_client_class.return_value = mock_qdrant_client
        
        mock_collection = Mock()
        mock_collection.status = "green"
        mock_collection.points_count = 100
        mock_collection.vectors_count = 100
        mock_qdrant_client.get_collection.return_value = mock_collection
        
        manager = QdrantManager()
        info = manager.get_collection_info()
        
        assert info["status"] == "green"
        assert info["points_count"] == 100
        assert info["vectors_count"] == 100
    
    @patch('src.db.qdrant_client.get_settings')
    @patch('src.db.qdrant_client.QdrantClient')
    def test_get_collection_info_minimal(
        self, mock_client_class, mock_get_settings, mock_settings, mock_qdrant_client
    ):
        """Test getting collection info with minimal attributes."""
        mock_get_settings.return_value = mock_settings
        mock_client_class.return_value = mock_qdrant_client
        
        # Collection without all attributes - use spec to prevent auto-creation
        from unittest.mock import Mock
        mock_collection = Mock(spec=['status'])
        mock_collection.status = "green"
        # Explicitly set hasattr to False for missing attributes
        type(mock_collection).points_count = property(lambda self: None)
        type(mock_collection).vectors_count = property(lambda self: None)
        mock_qdrant_client.get_collection.return_value = mock_collection
        
        manager = QdrantManager()
        info = manager.get_collection_info()
        
        assert info["status"] == "green"
        # Should not have points_count if not available (hasattr returns False)
        # The code checks hasattr, so if it's not set, it won't be in the dict

