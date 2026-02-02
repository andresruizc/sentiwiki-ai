"""Unit tests for utility functions."""

import pytest
from typing import Dict, Any


class TestUtils:
    """Test suite for utility functions."""
    
    def test_basic_assertion(self):
        """Basic test to verify test infrastructure works."""
        assert True
    
    def test_dict_operations(self):
        """Test basic dictionary operations."""
        data = {"key": "value", "number": 42}
        assert data["key"] == "value"
        assert data["number"] == 42
        assert len(data) == 2
    
    def test_list_operations(self):
        """Test basic list operations."""
        items = [1, 2, 3, 4, 5]
        assert len(items) == 5
        assert sum(items) == 15
        assert max(items) == 5
    
    def test_string_operations(self):
        """Test basic string operations."""
        text = "Sentinel-1"
        assert "Sentinel" in text
        assert text.startswith("Sentinel")
        assert text.endswith("1")
    
    @pytest.mark.parametrize("input_value,expected", [
        (1, 2),
        (2, 4),
        (3, 6),
        (10, 20),
    ])
    def test_parameterized(self, input_value: int, expected: int):
        """Test parameterized test."""
        assert input_value * 2 == expected

