"""Prompt building utilities for RAG system."""

from typing import List, Optional, Set

from src.utils.config import get_settings


def build_rag_system_prompt(
    context: str,
    standards_in_context: Optional[Set[str]] = None,
) -> str:
    """Build system prompt for RAG queries.
    
    Args:
        context: Formatted context from retrieved documents
        standards_in_context: Set of Sentinel mission identifiers found in context (e.g., {"S1", "S2", "S3"})
        
    Returns:
        Complete system prompt string
    """
    settings = get_settings()
    
    # Start with base prompt
    system_prompt = settings.prompts.rag_system_base.format(context=context)
    
    # Add comparative instructions if multiple standards detected
    if standards_in_context and len(standards_in_context) > 1:
        standards_list = ", ".join(sorted(standards_in_context))
        system_prompt += settings.prompts.rag_comparative_instruction.format(
            standards_list=standards_list
        )
    
    return system_prompt


def extract_standards_from_docs(docs: List[dict]) -> Set[str]:
    """Extract Sentinel mission identifiers from retrieved documents.
    
    Args:
        docs: List of retrieved documents with metadata
        
    Returns:
        Set of mission identifiers (e.g., {"S1", "S2", "S3", "S5P"})
    """
    missions = set()
    
    for doc in docs:
        # Try to extract mission from metadata
        metadata = doc.get("metadata", {})
        
        # Check various possible metadata fields
        mission = (
            metadata.get("mission") or
            metadata.get("mission_id") or
            # Try to extract from file_name
            _extract_mission_from_filename(doc.get("file_name", ""))
        )
        
        if mission:
            # Normalize mission identifier
            mission_normalized = _normalize_mission(mission)
            if mission_normalized:
                missions.add(mission_normalized)
    
    return missions


def _normalize_mission(mission: str) -> Optional[str]:
    """Normalize mission identifier to standard format.
    
    Examples:
        "Sentinel-1" -> "S1"
        "sentinel-2" -> "S2"
        "S3" -> "S3"
        "Sentinel-5P" -> "S5P"
    """
    if not mission:
        return None
    
    mission_lower = mission.lower().strip()
    
    # Map common variations to standard format
    mission_map = {
        "sentinel-1": "S1", "s1": "S1", "sentinel 1": "S1",
        "sentinel-2": "S2", "s2": "S2", "sentinel 2": "S2",
        "sentinel-3": "S3", "s3": "S3", "sentinel 3": "S3",
        "sentinel-5p": "S5P", "s5p": "S5P", "sentinel 5p": "S5P", "sentinel-5-p": "S5P",
    }
    
    return mission_map.get(mission_lower, mission.upper())


def _extract_mission_from_filename(filename: str) -> Optional[str]:
    """Extract Sentinel mission identifier from filename.
    
    Examples:
        "s1-mission.json" -> "S1"
        "sentinel-2-products.json" -> "S2"
        "s3-olci-instrument.json" -> "S3"
    """
    if not filename:
        return None
    
    import re
    # Look for Sentinel mission patterns
    patterns = [
        r"sentinel-?1|s1[^a-z0-9]",
        r"sentinel-?2|s2[^a-z0-9]",
        r"sentinel-?3|s3[^a-z0-9]",
        r"sentinel-?5[-\s]?p|s5p",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, filename.lower())
        if match:
            text = match.group(0).lower()
            if "sentinel-1" in text or text.startswith("s1"):
                return "S1"
            elif "sentinel-2" in text or text.startswith("s2"):
                return "S2"
            elif "sentinel-3" in text or text.startswith("s3"):
                return "S3"
            elif "sentinel-5" in text or "s5p" in text:
                return "S5P"
    
    return None

