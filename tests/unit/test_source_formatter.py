"""Unit tests for source formatter utilities."""

import pytest
from src.utils.source_formatter import extract_pdf_name_from_doc, format_sources_for_response


class TestExtractPDFNameFromDoc:
    """Test suite for extract_pdf_name_from_doc."""
    
    def test_extract_from_source_file(self):
        """Test extracting PDF name from source_file path."""
        doc = {
            "metadata": {
                "source_file": "/path/to/document.pdf",
            },
            "title": "Document Title",
        }
        
        result = extract_pdf_name_from_doc(doc)
        assert result == "document"
    
    def test_extract_from_source_file_without_extension(self):
        """Test extracting PDF name from source_file without .pdf extension."""
        doc = {
            "metadata": {
                "source_file": "/path/to/document",
            },
            "title": "Document Title",
        }
        
        result = extract_pdf_name_from_doc(doc)
        assert result == "document"
    
    def test_extract_from_file_stem(self):
        """Test extracting PDF name from file_stem."""
        doc = {
            "metadata": {
                "file_stem": "document",
            },
            "title": "Document Title",
        }
        
        result = extract_pdf_name_from_doc(doc)
        assert result == "document"
    
    def test_extract_from_file_name_pdf(self):
        """Test extracting PDF name from file_name with .pdf extension."""
        doc = {
            "metadata": {
                "file_name": "document.pdf",
            },
            "title": "Document Title",
        }
        
        result = extract_pdf_name_from_doc(doc)
        assert result == "document"
    
    def test_extract_from_file_name_enhanced_json(self):
        """Test extracting PDF name from enhanced JSON file name."""
        doc = {
            "metadata": {
                "file_name": "document_enhanced_enriched.json",
            },
            "title": "Document Title",
        }
        
        result = extract_pdf_name_from_doc(doc)
        assert result == "document"
    
    def test_extract_from_file_name_json(self):
        """Test extracting PDF name from JSON file name."""
        doc = {
            "metadata": {
                "file_name": "document.json",
            },
            "title": "Document Title",
        }
        
        result = extract_pdf_name_from_doc(doc)
        assert result == "document"
    
    def test_extract_fallback_to_title(self):
        """Test fallback to title when no metadata available."""
        doc = {
            "title": "Document Title",
        }
        
        result = extract_pdf_name_from_doc(doc)
        assert result == "Document Title"
    
    def test_extract_fallback_to_unknown(self):
        """Test fallback to 'Unknown' when nothing available."""
        doc = {}
        
        result = extract_pdf_name_from_doc(doc)
        assert result == "Unknown"


class TestFormatSourcesForResponse:
    """Test suite for format_sources_for_response."""
    
    def test_format_sources_basic(self):
        """Test basic source formatting."""
        docs = [
            {
                "title": "Test Document",
                "url": "http://test.com/doc1",
                "heading": "Section 1",
                "score": 0.9,
                "text": "This is test content",
            }
        ]
        
        sources = format_sources_for_response(docs)
        
        assert len(sources) == 1
        assert sources[0]["title"] == "Test Document"
        assert sources[0]["url"] == "http://test.com/doc1"
        assert sources[0]["heading"] == "Section 1"
        assert sources[0]["score"] == 90.0  # Converted to percentage
        assert sources[0]["score_percentage"] == 90.0
    
    def test_format_sources_with_limit(self):
        """Test formatting sources with limit."""
        docs = [
            {"title": f"Doc {i}", "score": 0.9 - (i * 0.1), "text": f"Content {i}"}
            for i in range(5)
        ]
        
        sources = format_sources_for_response(docs, limit=2)
        
        assert len(sources) == 2
    
    def test_format_sources_filters_low_relevance(self):
        """Test that sources below minimum relevance are filtered."""
        docs = [
            {"title": "High relevance", "score": 0.5, "text": "Content"},  # 50%
            {"title": "Low relevance", "score": 0.1, "text": "Content"},   # 10% - below 15%
            {"title": "Medium relevance", "score": 0.2, "text": "Content"}, # 20%
        ]
        
        sources = format_sources_for_response(docs, min_relevance_percentage=15.0)
        
        # Should filter out the 10% one
        assert len(sources) == 2
        assert all(s["score"] >= 15.0 for s in sources)
    
    def test_format_sources_with_contextualized_text(self):
        """Test formatting with contextualized_text preferred over text."""
        docs = [
            {
                "title": "Test Doc",
                "text": "Regular text",
                "contextualized_text": "Contextualized text",
                "score": 0.9,
            }
        ]
        
        sources = format_sources_for_response(docs)
        
        assert "contextualized text" in sources[0]["text"].lower()
    
    def test_format_sources_with_metadata(self):
        """Test formatting sources with metadata for PDF name extraction."""
        docs = [
            {
                "title": "Test Document",
                "metadata": {
                    "source_file": "/path/to/document.pdf",
                },
                "score": 0.9,
                "text": "Content",
            }
        ]
        
        sources = format_sources_for_response(docs)
        
        assert sources[0]["pdf_name"] == "document"
        assert sources[0]["title"] == "document"  # Uses PDF name as title
    
    def test_format_sources_text_truncation(self):
        """Test that text is truncated to 200 characters."""
        long_text = "A" * 300
        docs = [
            {
                "title": "Test Doc",
                "text": long_text,
                "score": 0.9,
            }
        ]
        
        sources = format_sources_for_response(docs)
        
        assert len(sources[0]["text"]) <= 203  # 200 + "..."
        assert sources[0]["text"].endswith("...")
    
    def test_format_sources_empty_list(self):
        """Test formatting empty document list."""
        sources = format_sources_for_response([])
        
        assert sources == []
    
    def test_format_sources_zero_score(self):
        """Test formatting sources with zero score."""
        docs = [
            {
                "title": "Test Doc",
                "score": 0.0,
                "text": "Content",
            }
        ]
        
        sources = format_sources_for_response(docs)
        
        # Zero score should be filtered out (below 15% threshold)
        assert len(sources) == 0
    
    def test_format_sources_missing_fields(self):
        """Test formatting sources with missing optional fields."""
        docs = [
            {
                "title": "Test Doc",
                "score": 0.9,
                # Missing url, heading, text
            }
        ]
        
        sources = format_sources_for_response(docs)
        
        assert len(sources) == 1
        assert sources[0]["url"] == ""
        assert sources[0]["heading"] == ""
        assert "text" in sources[0]
    
    def test_format_sources_groups_by_document(self):
        """Test that multiple chunks from the same document are grouped together."""
        docs = [
            {
                "title": "Test Document",
                "metadata": {
                    "source_file": "/path/to/document.pdf",
                },
                "heading": "Section 1",
                "score": 0.7,  # 70%
                "text": "Content from section 1",
            },
            {
                "title": "Test Document",
                "metadata": {
                    "source_file": "/path/to/document.pdf",
                },
                "heading": "Section 2",
                "score": 0.9,  # 90% - best score
                "text": "Content from section 2",
            },
            {
                "title": "Test Document",
                "metadata": {
                    "source_file": "/path/to/document.pdf",
                },
                "heading": "Section 3",
                "score": 0.6,  # 60%
                "text": "Content from section 3",
            },
            {
                "title": "Other Document",
                "metadata": {
                    "source_file": "/path/to/other.pdf",
                },
                "heading": "Section A",
                "score": 0.8,  # 80%
                "text": "Content from other document",
            },
        ]
        
        sources = format_sources_for_response(docs)
        
        # Should have 2 sources (one per document), not 4
        assert len(sources) == 2
        
        # Find the grouped document source
        doc_source = next(s for s in sources if s["pdf_name"] == "document")
        other_source = next(s for s in sources if s["pdf_name"] == "other")
        
        # The grouped document should have the best score (90%)
        assert doc_source["score_percentage"] == 90.0
        
        # Should include multiple headings (may be formatted as comma-separated)
        assert "Section" in doc_source["heading"]
        
        # The text should be from the chunk with best score
        assert "section 2" in doc_source["text"].lower()
        
        # Other document should be separate
        assert other_source["pdf_name"] == "other"
        assert other_source["score_percentage"] == 80.0
    
    def test_format_sources_groups_with_heading_path(self):
        """Test grouping with heading_path from metadata."""
        docs = [
            {
                "title": "Test Document",
                "metadata": {
                    "source_file": "/path/to/document.pdf",
                    "heading_path": "Mission > OLCI Instrument",
                },
                "score": 0.8,
                "text": "Content 1",
            },
            {
                "title": "Test Document",
                "metadata": {
                    "source_file": "/path/to/document.pdf",
                    "heading_path": "Mission > SLSTR Instrument",
                },
                "score": 0.9,
                "text": "Content 2",
            },
        ]
        
        sources = format_sources_for_response(docs)
        
        # Should be grouped into one source
        assert len(sources) == 1
        assert sources[0]["score_percentage"] == 90.0
        # Should show multiple headings
        assert "OLCI" in sources[0]["heading"] or "SLSTR" in sources[0]["heading"]

