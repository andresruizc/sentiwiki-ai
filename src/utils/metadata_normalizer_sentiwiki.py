"""Metadata normalization utilities for consistent mission and document type values."""

import re
from typing import Dict, Optional

from loguru import logger


class MetadataNormalizer:
    """Normalize metadata values to ensure consistency across the system."""
    
    # Standard mission codes (canonical format)
    MISSION_MAPPING = {
        # Sentinel missions
        "sentinel-1": "S1",
        "sentinel 1": "S1",
        "s1": "S1",
        "s1a": "S1",
        "s1b": "S1",
        "sentinel-2": "S2",
        "sentinel 2": "S2",
        "s2": "S2",
        "s2a": "S2",
        "s2b": "S2",
        "sentinel-3": "S3",
        "sentinel 3": "S3",
        "s3": "S3",
        "s3a": "S3",
        "s3b": "S3",
        "sentinel-4": "S4",
        "sentinel 4": "S4",
        "s4": "S4",
        "sentinel-5": "S5",
        "sentinel 5": "S5",
        "s5": "S5",
        "sentinel-5p": "S5P",
        "sentinel 5p": "S5P",
        "sentinel-5-p": "S5P",
        "sentinel 5 p": "S5P",
        "s5p": "S5P",
        "sentinel-6": "S6",
        "sentinel 6": "S6",
        "s6": "S6",
        # Future missions (keep as-is but normalize case)
        "chime": "CHIME",
        "cimr": "CIMR",
        "co2m": "CO2M",
        "cristal": "CRISTAL",
        "lstm": "LSTM",
        "rose-l": "ROSE-L",
        "rose l": "ROSE-L",
        "rose_l": "ROSE-L",
    }
    
    # Document type normalization
    DOCUMENT_TYPE_MAPPING = {
        "mission": "mission_overview",
        "mission overview": "mission_overview",
        "overview": "mission_overview",
        "applications": "applications",
        "application": "applications",
        "products": "products",
        "product": "products",
        "processing": "processing",
        "instrument": "instrument",
        "instruments": "instrument",
        "general": "general",
        "documents": "documents",
        "document": "documents",
    }
    
    @classmethod
    def normalize_mission(cls, mission: Optional[str]) -> Optional[str]:
        """Normalize mission identifier to canonical format.
        
        Args:
            mission: Mission identifier in any format
            
        Returns:
            Normalized mission code (S1, S2, S3, S5P, etc.) or None if not recognized
            
        Examples:
            >>> MetadataNormalizer.normalize_mission("Sentinel-3")
            'S3'
            >>> MetadataNormalizer.normalize_mission("SENTINEL 5P")
            'S5P'
            >>> MetadataNormalizer.normalize_mission("s3")
            'S3'
        """
        if not mission:
            return None
        
        # Normalize input: lowercase, strip whitespace
        normalized = mission.strip().lower()
        
        # Remove common prefixes/suffixes
        normalized = re.sub(r'^(the\s+)?', '', normalized)
        normalized = re.sub(r'\s+(mission|satellite)$', '', normalized)
        
        # Direct mapping lookup
        if normalized in cls.MISSION_MAPPING:
            return cls.MISSION_MAPPING[normalized]
        
        # Try pattern matching for variants
        # Handle "sentinel-5p", "sentinel 5p", "sentinel-5-p", etc.
        if re.match(r'sentinel[- ]?5[- ]?p', normalized):
            return "S5P"
        if re.match(r'sentinel[- ]?1', normalized):
            return "S1"
        if re.match(r'sentinel[- ]?2', normalized):
            return "S2"
        if re.match(r'sentinel[- ]?3', normalized):
            return "S3"
        if re.match(r'sentinel[- ]?4', normalized):
            return "S4"
        if re.match(r'sentinel[- ]?5(?!p)', normalized):
            return "S5"
        if re.match(r'sentinel[- ]?6', normalized):
            return "S6"
        
        # Handle abbreviations with variants (s1, s1a, s1b, etc.)
        if re.match(r'^s[1-6][ab]?$', normalized):
            return normalized.upper()
        if re.match(r'^s5p$', normalized):
            return "S5P"
        
        # For future missions, normalize case but keep format
        if normalized in ["chime", "cimr", "co2m", "cristal", "lstm", "rose-l"]:
            return normalized.upper()
        
        # If we can't normalize, log warning and return None
        logger.warning(f"Could not normalize mission: '{mission}' -> keeping as-is")
        return mission.strip().upper() if mission else None
    
    @classmethod
    def normalize_document_type(cls, doc_type: Optional[str]) -> Optional[str]:
        """Normalize document type to canonical format.
        
        Args:
            doc_type: Document type in any format
            
        Returns:
            Normalized document type or None
            
        Examples:
            >>> MetadataNormalizer.normalize_document_type("mission")
            'mission_overview'
            >>> MetadataNormalizer.normalize_document_type("applications")
            'applications'
        """
        if not doc_type:
            return None
        
        normalized = doc_type.strip().lower()
        
        if normalized in cls.DOCUMENT_TYPE_MAPPING:
            return cls.DOCUMENT_TYPE_MAPPING[normalized]
        
        # If not in mapping, return as-is (might be a valid custom type)
        return doc_type.strip()
    
    @classmethod
    def normalize_metadata(cls, metadata: Dict) -> Dict:
        """Normalize all metadata fields in a dictionary.
        
        Args:
            metadata: Metadata dictionary
            
        Returns:
            Normalized metadata dictionary
        """
        normalized = metadata.copy()
        
        # Normalize mission
        if "mission" in normalized:
            normalized["mission"] = cls.normalize_mission(normalized["mission"])
        
        # Normalize document_type
        if "document_type" in normalized:
            normalized["document_type"] = cls.normalize_document_type(
                normalized["document_type"]
            )
        
        return normalized
    
    @classmethod
    def extract_mission_from_url(cls, url: str) -> Optional[str]:
        """Extract and normalize mission from URL.
        
        Args:
            url: URL string (e.g., "https://sentiwiki.copernicus.eu/web/s3-mission")
            
        Returns:
            Normalized mission code or None
        """
        if not url:
            return None
        
        url_lower = url.lower()
        
        # Try to match mission patterns in URL
        for pattern, mission_code in [
            (r'sentinel[-_]?5[-_]?p', "S5P"),
            (r'sentinel[-_]?1', "S1"),
            (r'sentinel[-_]?2', "S2"),
            (r'sentinel[-_]?3', "S3"),
            (r'sentinel[-_]?4', "S4"),
            (r'sentinel[-_]?5(?!p)', "S5"),
            (r'sentinel[-_]?6', "S6"),
            (r'[/-]s5p[/-]', "S5P"),
            (r'[/-]s[1-6][ab]?[/-]', None),  # Will extract and normalize
        ]:
            match = re.search(pattern, url_lower)
            if match:
                if mission_code:
                    return mission_code
                # Extract the matched part and normalize
                matched = match.group(0).strip('/-')
                return cls.normalize_mission(matched)
        
        # Try direct lookup for future missions
        for mission_name in ["chime", "cimr", "co2m", "cristal", "lstm", "rose-l"]:
            if mission_name in url_lower:
                return mission_name.upper()
        
        return None


__all__ = ["MetadataNormalizer"]

