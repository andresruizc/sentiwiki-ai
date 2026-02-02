"""Unit tests for metadata filter."""

import pytest
from unittest.mock import Mock, patch

from src.utils.metadata_filter import MetadataFilter


class TestMetadataFilter:
    """Test suite for MetadataFilter."""
    
    @pytest.fixture
    def metadata_filter(self):
        """Create MetadataFilter instance."""
        return MetadataFilter(enable_logging=False)
    
    def test_analyze_query_basic(self, metadata_filter):
        """Test basic query analysis."""
        result = metadata_filter.analyze_query("What is Sentinel-1?")
        
        assert "query_type" in result
        assert "mission" in result
        assert "missions" in result
        assert "document_type" in result
        assert "instruments" in result
        assert "products" in result
        assert "filters" in result
    
    def test_analyze_query_procedure_type(self, metadata_filter):
        """Test query type detection for procedures."""
        result = metadata_filter.analyze_query("How to process Sentinel-1 data?")
        
        assert result["query_type"] == "procedure"
    
    def test_analyze_query_definition_type(self, metadata_filter):
        """Test query type detection for definitions."""
        result = metadata_filter.analyze_query("What is Sentinel-1?")
        
        assert result["query_type"] == "definition"
    
    def test_analyze_query_specification_type(self, metadata_filter):
        """Test query type detection for specifications."""
        # Use a query that definitely matches specification patterns
        result = metadata_filter.analyze_query("What are the accuracy specifications?")
        
        assert result["query_type"] == "specification"
    
    def test_analyze_query_general_type(self, metadata_filter):
        """Test query type detection for general queries."""
        result = metadata_filter.analyze_query("Tell me about Sentinel missions")
        
        assert result["query_type"] == "general"
    
    def test_analyze_query_extracts_mission(self, metadata_filter):
        """Test mission extraction from query."""
        result = metadata_filter.analyze_query("What is Sentinel-1?")
        
        # Should extract S1 mission
        assert result["mission"] is not None or result["missions"] is not None
    
    def test_analyze_query_extracts_instruments(self, metadata_filter):
        """Test instrument extraction from query."""
        result = metadata_filter.analyze_query("What is SAR instrument?")
        
        assert "SAR" in result["instruments"]
    
    def test_analyze_query_extracts_products(self, metadata_filter):
        """Test product extraction from query."""
        result = metadata_filter.analyze_query("What is L1C product?")
        
        assert "L1C" in result["products"]
    
    def test_analyze_query_extracts_level_products(self, metadata_filter):
        """Test level product extraction (L1, L2, L3)."""
        # Use format that matches the regex pattern
        result = metadata_filter.analyze_query("Tell me about L2 products")
        
        assert "L2" in result["products"]
    
    def test_extract_instruments_sar(self, metadata_filter):
        """Test SAR instrument extraction."""
        instruments = metadata_filter._extract_instruments("What is SAR?")
        
        assert "SAR" in instruments
    
    def test_extract_instruments_olci(self, metadata_filter):
        """Test OLCI instrument extraction."""
        instruments = metadata_filter._extract_instruments("Tell me about OLCI")
        
        assert "OLCI" in instruments
    
    def test_extract_instruments_multiple(self, metadata_filter):
        """Test multiple instrument extraction."""
        instruments = metadata_filter._extract_instruments("Compare SAR and MSI instruments")
        
        assert len(instruments) >= 1
        assert "SAR" in instruments or "MSI" in instruments
    
    def test_extract_products_l1c(self, metadata_filter):
        """Test L1C product extraction."""
        products = metadata_filter._extract_products("What is L1C?")
        
        assert "L1C" in products
    
    def test_extract_products_l2a(self, metadata_filter):
        """Test L2A product extraction."""
        products = metadata_filter._extract_products("Tell me about L2A")
        
        assert "L2A" in products
    
    def test_extract_products_level_format(self, metadata_filter):
        """Test level format product extraction."""
        # The regex looks for "level L" or "L" followed by digits
        products = metadata_filter._extract_products("L1 products")
        
        assert "L1" in products
    
    def test_generate_filters_with_mission(self, metadata_filter):
        """Test filter generation with mission.
        
        Note: When mission is present, document_type is NOT included in filters
        to prevent excluding relevant documents (e.g., CHIME has document_type="general").
        """
        analysis = {
            "mission": "S1",
            "document_type": "handbook",
        }
        
        filters = metadata_filter._generate_filters(analysis)
        
        assert filters["mission"] == "S1"
        # document_type should NOT be in filters when mission is present
        assert "document_type" not in filters
    
    def test_generate_filters_with_document_type_only(self, metadata_filter):
        """Test filter generation with document_type but no mission."""
        analysis = {
            "document_type": "handbook",
        }
        
        filters = metadata_filter._generate_filters(analysis)
        
        assert filters["document_type"] == "handbook"
        assert "mission" not in filters
    
    def test_generate_filters_without_metadata(self, metadata_filter):
        """Test filter generation without metadata."""
        analysis = {}
        
        filters = metadata_filter._generate_filters(analysis)
        
        assert filters == {}
    
    def test_create_qdrant_filter_simple(self, metadata_filter):
        """Test creating Qdrant filter from simple filters."""
        filters = {"mission": "S1", "document_type": "handbook"}
        
        result = metadata_filter.create_qdrant_filter(filters)
        
        assert result == filters
    
    def test_create_qdrant_filter_with_list(self, metadata_filter):
        """Test creating Qdrant filter with list value."""
        filters = {"mission": ["S1", "S2"]}
        
        result = metadata_filter.create_qdrant_filter(filters)
        
        # Should take first value from list
        assert result["mission"] == "S1"
    
    def test_create_qdrant_filter_empty(self, metadata_filter):
        """Test creating Qdrant filter from empty filters."""
        result = metadata_filter.create_qdrant_filter({})
        
        assert result is None
    
    def test_boost_scores_by_metadata_mission_match(self, metadata_filter):
        """Test score boosting for mission match."""
        results = [
            {
                "score": 0.5,
                "metadata": {"mission": "S1"},
                "text": "Test document",
            }
        ]
        analysis = {"mission": "S1"}
        
        boosted = metadata_filter.boost_scores_by_metadata(results, analysis)
        
        assert boosted[0]["score"] > 0.5  # Should be boosted
        assert "boost_reasons" in boosted[0]
    
    def test_boost_scores_by_metadata_instrument_match(self, metadata_filter):
        """Test score boosting for instrument match."""
        results = [
            {
                "score": 0.5,
                "metadata": {},
                "text": "SAR instrument is used for radar imaging",
                "title": "SAR Overview",
            }
        ]
        analysis = {"instruments": ["SAR"]}
        
        boosted = metadata_filter.boost_scores_by_metadata(results, analysis)
        
        assert boosted[0]["score"] > 0.5  # Should be boosted
    
    def test_boost_scores_by_metadata_product_match(self, metadata_filter):
        """Test score boosting for product match."""
        results = [
            {
                "score": 0.5,
                "metadata": {},
                "text": "L1C product format",
                "title": "Product Guide",
            }
        ]
        analysis = {"products": ["L1C"]}
        
        boosted = metadata_filter.boost_scores_by_metadata(results, analysis)
        
        assert boosted[0]["score"] > 0.5  # Should be boosted
    
    def test_boost_scores_by_metadata_document_type_match(self, metadata_filter):
        """Test score boosting for document type match."""
        results = [
            {
                "score": 0.5,
                "metadata": {"document_type": "handbook"},
                "text": "Test document",
            }
        ]
        analysis = {"document_type": "handbook"}
        
        boosted = metadata_filter.boost_scores_by_metadata(results, analysis)
        
        assert boosted[0]["score"] > 0.5  # Should be boosted
    
    def test_boost_scores_by_metadata_procedure_structure(self, metadata_filter):
        """Test score boosting for procedure query with step structure."""
        results = [
            {
                "score": 0.5,
                "metadata": {},
                "text": "Step 1: Do this. Step 2: Do that.",
            }
        ]
        analysis = {"query_type": "procedure"}
        
        boosted = metadata_filter.boost_scores_by_metadata(results, analysis)
        
        assert boosted[0]["score"] > 0.5  # Should be boosted
    
    def test_boost_scores_by_metadata_empty_results(self, metadata_filter):
        """Test boosting with empty results."""
        results = []
        analysis = {"mission": "S1"}
        
        boosted = metadata_filter.boost_scores_by_metadata(results, analysis)
        
        assert boosted == []
    
    def test_boost_scores_by_metadata_no_match(self, metadata_filter):
        """Test boosting when no metadata matches."""
        results = [
            {
                "score": 0.5,
                "metadata": {"mission": "S2"},
                "text": "Test document",
            }
        ]
        analysis = {"mission": "S1"}  # Different mission
        
        boosted = metadata_filter.boost_scores_by_metadata(results, analysis)
        
        # Score should remain the same or slightly different
        assert boosted[0]["score"] == 0.5 or abs(boosted[0]["score"] - 0.5) < 0.1

