"""Metadata extraction from queries for intelligent filtering."""

import re
from typing import Dict, List, Optional, Set

from loguru import logger


class MetadataExtractor:
    """Extract metadata (missions, document types) from queries for filtering."""
    
    # Mission patterns: full names, abbreviations, and variants
    MISSION_PATTERNS = {
        "S1": [
            r"\bsentinel-1\b",
            r"\bs1\b",
            r"\bs1a\b",
            r"\bs1b\b",
            r"\bsentinel\s*1\b",
        ],
        "S2": [
            r"\bsentinel-2\b",
            r"\bs2\b",
            r"\bs2a\b",
            r"\bs2b\b",
            r"\bsentinel\s*2\b",
        ],
        "S3": [
            r"\bsentinel-3\b",
            r"\bs3\b",
            r"\bs3a\b",
            r"\bs3b\b",
            r"\bsentinel\s*3\b",
        ],
        "S5P": [
            r"\bsentinel-5p\b",
            r"\bs5p\b",
            r"\bsentinel\s*5\s*p\b",
            r"\bsentinel-5\s*precursor\b",
        ],
        "S4": [
            r"\bsentinel-4\b",
            r"\bs4\b",
            r"\bsentinel\s*4\b",
        ],
        "S5": [
            r"\bsentinel-5\b",
            r"\bs5\b",
            r"\bsentinel\s*5\b",
        ],
        "S6": [
            r"\bsentinel-6\b",
            r"\bs6\b",
            r"\bsentinel\s*6\b",
        ],
        "CHIME": [
            r"\bchime\b",
            r"\bcopernicus\s*hyperspectral\s*imaging\s*mission\b",
            r"\bhyperspectral\s*imaging\s*mission\s*for\s*the\s*environment\b",
        ],
        "CIMR": [
            r"\bcimr\b",
            r"\bcopernicus\s*imagine\s*microwave\s*radiometer\b",
        ],
        "CO2M": [
            r"\bco2m\b",
            r"\bcopernicus\s*anthropogenic\s*carbon\s*dioxide\s*monitoring\b",
        ],
        "CRISTAL": [
            r"\bcristal\b",
            r"\bcopernicus\s*polar\s*ice\s*and\s*snow\s*topography\s*altimeter\b",
        ],
        "LSTM": [
            r"\blstm\b",
            r"\bland\s*surface\s*temperature\s*monitoring\b",
        ],
        "ROSE-L": [
            r"\brose-l\b",
            r"\bl-band\s*radar\s*observing\s*system\b",
        ],
    }
    
    # Document type patterns
    # Note: "mission" alone is too broad - it appears in many queries about specific missions
    # Only extract "mission_overview" when explicitly asking for overview/general info
    DOCUMENT_TYPE_PATTERNS = {
        "mission_overview": [
            r"\bmission\s+overview\b",
            r"\boverview\s+of\s+.*mission\b",
            r"\bgeneral\s+.*mission\b",
            r"\bmission\s+general\b",
        ],
        "instrument": [
            r"\binstrument\b",
            r"\bsensor\b",
            r"\bolci\b",
            r"\bslstr\b",
            r"\bsral\b",
            r"\bsar\b",
            r"\bmsi\b",
        ],
        "product": [
            r"\bproduct\b",
            r"\bdata\s*product\b",
            r"\blevel\s*\d+\b",
        ],
        "application": [
            r"\bapplication\b",
            r"\buse\b",
            r"\buse\s*case\b",
        ],
    }
    
    def __init__(self, enable_logging: bool = True):
        """Initialize metadata extractor.
        
        Args:
            enable_logging: Whether to log extraction results
        """
        self.enable_logging = enable_logging
    
    def extract_mission(self, query: str) -> Optional[str]:
        """Extract mission identifier from query.
        
        Args:
            query: User query string
            
        Returns:
            Mission identifier (e.g., "S1", "S2", "S3", "S5P") or None if not found
        """
        query_lower = query.lower()
        
        # Check each mission pattern
        for mission, patterns in self.MISSION_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    if self.enable_logging:
                        logger.debug(f"Extracted mission '{mission}' from query: {query[:60]}...")
                    return mission
        
        return None
    
    def extract_missions(self, query: str) -> List[str]:
        """Extract all mission identifiers from query.
        
        Args:
            query: User query string
            
        Returns:
            List of mission identifiers found in query
        """
        query_lower = query.lower()
        found_missions = []
        
        for mission, patterns in self.MISSION_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    if mission not in found_missions:
                        found_missions.append(mission)
                    break
        
        if self.enable_logging and found_missions:
            logger.debug(f"Extracted missions {found_missions} from query: {query[:60]}...")
        
        return found_missions
    
    def extract_document_type(self, query: str) -> Optional[str]:
        """Extract document type from query.
        
        Args:
            query: User query string
            
        Returns:
            Document type identifier or None if not found
        """
        query_lower = query.lower()
        
        for doc_type, patterns in self.DOCUMENT_TYPE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    if self.enable_logging:
                        logger.debug(f"Extracted document type '{doc_type}' from query: {query[:60]}...")
                    return doc_type
        
        return None
    
    def extract_filters(self, query: str) -> Optional[Dict[str, str]]:
        """Extract metadata filters from query.
        
        Args:
            query: User query string
            
        Returns:
            Dictionary of filters to apply, or None if no filters should be applied
        """
        filters = {}
        
        # Extract mission
        mission = self.extract_mission(query)
        if mission:
            filters["mission"] = mission
        
        # Extract document type (optional, less critical)
        # doc_type = self.extract_document_type(query)
        # if doc_type:
        #     filters["document_type"] = doc_type
        
        if filters:
            if self.enable_logging:
                logger.debug(f"Metadata extractor found filters: {filters}")
            return filters
        
        if self.enable_logging:
            logger.debug("Metadata extractor: No filters found in query")
        return None
    
    def should_use_comparative_response(self, query: str, retrieved_docs: List[Dict]) -> bool:
        """Determine if a comparative response is appropriate.
        
        A comparative response is appropriate when:
        1. No specific mission was mentioned in the query
        2. Retrieved documents contain multiple missions
        
        Args:
            query: Original query
            retrieved_docs: List of retrieved documents
            
        Returns:
            True if comparative response should be used
        """
        # If mission was mentioned, don't use comparative
        if self.extract_mission(query):
            return False
        
        # Check if retrieved docs contain multiple missions
        missions_found: Set[str] = set()
        for doc in retrieved_docs:
            mission = doc.get("metadata", {}).get("mission")
            if mission:
                missions_found.add(mission)
        
        # If multiple missions found, use comparative
        return len(missions_found) > 1


__all__ = ["MetadataExtractor"]

