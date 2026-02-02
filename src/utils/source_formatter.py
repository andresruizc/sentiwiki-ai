"""Utility functions for formatting document sources consistently across endpoints."""

from typing import Any, Dict, List, Optional


def extract_pdf_name_from_doc(doc: Dict[str, Any]) -> str:
    """Extract PDF name from document metadata.
    
    This function extracts the original PDF name from document metadata,
    handling cases where file_name might be the enriched JSON name.
    
    Args:
        doc: Document dictionary with metadata
        
    Returns:
        PDF name without extension
    """
    import os
    metadata = doc.get("metadata", {})
    
    # Option 1: Extract from source_file path (most reliable)
    source_file = metadata.get("source_file", "")
    if source_file:
        pdf_name = os.path.basename(source_file)
        # Remove .pdf or .md extension if present
        if pdf_name.endswith(".pdf"):
            return pdf_name[:-4]
        elif pdf_name.endswith(".md"):
            return pdf_name[:-3]
        return pdf_name
    
    # Option 2: Use file_stem (should be PDF name without extension)
    file_stem = metadata.get("file_stem")
    if file_stem:
        return file_stem
    
    # Option 3: Clean file_name if it's the JSON name
    file_name = metadata.get("file_name", "")
    if file_name:
        # If file_name ends with _enhanced_enriched.json, extract PDF name
        if "_enhanced_enriched.json" in file_name:
            # Remove _enhanced_enriched.json suffix
            pdf_name = file_name.replace("_enhanced_enriched.json", "")
            # Remove .pdf or .md extension if present
            if pdf_name.endswith(".pdf"):
                pdf_name = pdf_name[:-4]
            elif pdf_name.endswith(".md"):
                pdf_name = pdf_name[:-3]
            return pdf_name
        elif file_name.endswith(".pdf"):
            return file_name[:-4]
        elif file_name.endswith(".md"):
            return file_name[:-3]
        elif file_name.endswith(".json"):
            # If it's a JSON, try to extract PDF name (remove _enhanced_enriched.json if present)
            pdf_name = file_name.replace("_enhanced_enriched.json", "").replace(".json", "")
            # Also remove .md if present after removing .json
            if pdf_name.endswith(".md"):
                pdf_name = pdf_name[:-3]
            return pdf_name
        else:
            return file_name
    
    # Fallback to title
    return doc.get("title", "Unknown")


def format_sources_for_response(
    docs: List[Dict[str, Any]], 
    limit: Optional[int] = None,
    min_relevance_percentage: float = 15.0
) -> List[Dict[str, Any]]:
    """Format document sources for API response with PDF names and score percentages.
    
    This function extracts PDF names from metadata and converts scores to percentages,
    ensuring consistent format across all endpoints. Filters out sources with relevance
    below the minimum threshold to save tokens. Groups sources by document to avoid
    showing the same document multiple times when it's split into chunks.
    
    Args:
        docs: List of document dictionaries from retriever
        limit: Optional limit to number of sources (default: None, returns all)
        min_relevance_percentage: Minimum relevance percentage to include (default: 15.0)
                                  Sources below this threshold are filtered out to save tokens
        
    Returns:
        List of formatted source dictionaries with pdf_name and score_percentage,
        grouped by document (one entry per document, with best score and all headings)
    """
    # First pass: collect all valid sources and group by document
    docs_to_process = docs[:limit] if limit else docs
    grouped_sources: Dict[str, Dict[str, Any]] = {}
    
    for doc in docs_to_process:
        # Get score and convert to percentage (scores are typically 0-1)
        score = doc.get("score", 0.0)
        score_percentage = round(score * 100, 1) if score else 0.0
        
        # Filter out sources with relevance below threshold to save tokens
        if score_percentage < min_relevance_percentage:
            continue
        
        # Extract PDF name (this is our grouping key)
        pdf_name = extract_pdf_name_from_doc(doc)
        
        # Get heading information
        heading = doc.get("heading", "")
        heading_path = doc.get("metadata", {}).get("heading_path", "")
        # Use heading_path if available, otherwise use heading
        section_name = heading_path if heading_path else heading
        
        # Get base URL for the document
        base_url = doc.get("url", "")
        
        # Get section_url from chunk metadata (ground-truth URL from SentiWiki)
        # This is extracted from the raw crawl data and is 100% accurate
        section_url = doc.get("metadata", {}).get("section_url", "")
        
        # Fallback to base_url if section_url is not available (for backward compatibility)
        if not section_url:
            section_url = base_url
        
        # Group by pdf_name
        if pdf_name not in grouped_sources:
            # First occurrence of this document
            grouped_sources[pdf_name] = {
                "title": pdf_name,
                "url": base_url,
                "heading": section_name,  # Keep first heading as primary
                "headings": [section_name] if section_name else [],  # List of all unique headings
                "headings_with_urls": [{"heading": section_name, "url": section_url}] if section_name else [],  # List with URLs
                "score": score_percentage,
                "score_percentage": score_percentage,
                "pdf_name": pdf_name,
                "text": (doc.get("contextualized_text") or doc.get("text", ""))[:200] + "...",
                "chunk_count": 1,  # Track how many chunks from this document
            }
        else:
            # Document already seen, update with best score and collect headings
            existing = grouped_sources[pdf_name]
            
            # Update to best (highest) score
            if score_percentage > existing["score_percentage"]:
                existing["score"] = score_percentage
                existing["score_percentage"] = score_percentage
                # Update text to use the chunk with best score
                existing["text"] = (doc.get("contextualized_text") or doc.get("text", ""))[:200] + "..."
            
            # Collect unique headings with their URLs
            if section_name:
                # Check if this heading already exists
                existing_headings = {h["heading"] for h in existing.get("headings_with_urls", [])}
                if section_name not in existing_headings:
                    existing["headings"].append(section_name)
                    existing.setdefault("headings_with_urls", []).append({
                        "heading": section_name,
                        "url": section_url
                    })
            
            # Increment chunk count
            existing["chunk_count"] += 1
            
            # Keep URL if we have one (prefer non-empty)
            if base_url and not existing["url"]:
                existing["url"] = base_url
    
    # Convert grouped dict to list and sort by score (best first)
    sources = list(grouped_sources.values())
    sources.sort(key=lambda x: x["score_percentage"], reverse=True)
    
    # Format headings for display (if multiple sections)
    for source in sources:
        headings_list = source.get("headings", [])
        if len(headings_list) > 1:
            # Detect common prefix to simplify display
            def find_common_prefix(strings):
                """Find the longest common prefix among a list of strings."""
                if not strings:
                    return ""
                # Split by " > " to find common path prefix
                split_strings = [s.split(" > ") for s in strings if s]
                if not split_strings:
                    return ""
                
                # Find common prefix parts
                min_length = min(len(parts) for parts in split_strings)
                common_parts = []
                
                for i in range(min_length):
                    if all(parts[i] == split_strings[0][i] for parts in split_strings):
                        common_parts.append(split_strings[0][i])
                    else:
                        break
                
                if common_parts:
                    return " > ".join(common_parts) + " > "
                return ""
            
            # Find common prefix
            common_prefix = find_common_prefix(headings_list)
            
            # Simplify headings by removing common prefix
            simplified_headings = []
            for heading in headings_list:
                if heading.startswith(common_prefix):
                    simplified = heading[len(common_prefix):].strip()
                    # If simplified is empty or just whitespace, use full heading
                    if not simplified:
                        simplified = heading
                    simplified_headings.append(simplified)
                else:
                    simplified_headings.append(heading)
            
            # Join first few headings with comma
            headings_display = ", ".join(simplified_headings[:3])
            if len(simplified_headings) > 3:
                headings_display += f" (+{len(simplified_headings) - 3} más)"
            
            source["heading"] = headings_display
        elif len(headings_list) == 1:
            source["heading"] = headings_list[0]
        else:
            # No headings, ensure it's an empty string
            source["heading"] = ""
        # Keep headings_with_urls for frontend, but also keep simplified heading string for backward compatibility
        # Remove internal headings list (not needed in response, we use headings_with_urls)
        source.pop("headings", None)
        # Remove chunk_count (internal use only, can be added back if needed for display)
        source.pop("chunk_count", None)
    
    return sources

