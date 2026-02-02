"""Markdown cleaning utilities for RAG applications."""

import re
from typing import Dict, List, Tuple

from loguru import logger

from src.utils.metadata_normalizer_sentiwiki import MetadataNormalizer


class MarkdownCleaner:
    """Clean markdown content for better RAG performance.
    
    Used for processing full documents (e.g., during scraping or enhancement).
    """

    def __init__(self):
        """Initialize the cleaner."""
        # Patterns to remove (noise for RAG)
        self.remove_patterns = [
            r"Cookie Notice.*?Don't track me",  # Cookie notices
            r"\[ Skip to main content \].*?\n",  # Skip links
            r"Show navigation\n",
            r"Show search form\n",
            r"JavaScript errors detected.*?Close",  # JS errors
            r"Copyright © \d{4}.*?Confluence",  # Footer
            r"\[ \]\(https://.*?\"Copy to clipboard\"\)",  # Copy to clipboard links
            r"×",  # Close buttons
            r"\[ !\[\].*?Go to homepage \].*?\n",  # Logo/home links
        ]
        
        # Navigation section pattern (SentiWiki specific)
        self.nav_pattern = r"(  \* \[.*?\]\(https://sentiwiki\.copernicus\.eu.*?\)\n)+"

    def extract_title_from_content(self, markdown: str) -> Tuple[str, str]:
        """Extract the main title (first H1) and clean content.
        
        Args:
            markdown: Raw markdown content
            
        Returns:
            Tuple of (title, remaining_content)
        """
        # Find first H1
        h1_match = re.search(r"^#\s+(.+?)$", markdown, re.MULTILINE)
        if h1_match:
            title = h1_match.group(1).strip()
            # Remove the H1 from content (we'll add it back in frontmatter context)
            content = markdown[h1_match.end():].strip()
            return title, content
        return "", markdown

    def clean_navigation(self, markdown: str) -> str:
        """Remove navigation menus but keep relevant links in content.
        
        Args:
            markdown: Markdown content
            
        Returns:
            Cleaned markdown
        """
        # Remove the large navigation menu at the top (SentiWiki specific)
        markdown = re.sub(self.nav_pattern, "", markdown, flags=re.MULTILINE)
        return markdown

    # ---- Heading anchor extraction & reinjection (SentiWiki-specific) ----

    def extract_heading_anchors(self, markdown: str) -> Dict[str, str]:
        """Extract heading -> URL mapping from raw SentiWiki markdown.
        
        The raw Crawl4AI markdown for SentiWiki encodes section anchors as:
        
        ##  [ ](https://sentiwiki.copernicus.eu/web/olci-applications#OLCIApplications-MesoscalesProcessMonitoring "Copy to clipboard")Mesoscales Process Monitoring
        
        This method parses those lines and builds a mapping from the *normalized*
        heading text (e.g. 'Mesoscales Process Monitoring') to the full URL,
        including the fragment identifier.
        """
        heading_anchors: Dict[str, str] = {}

        # Match heading levels 2–6 with the SentiWiki "[ ](url \"Copy to clipboard\")Title" pattern
        # Pattern breakdown:
        # - ^(#{2,6})\s+ - heading level (##, ###, etc.)
        # - \[\s*\]\( - empty link brackets [ ](
        # - (https://sentiwiki\.copernicus\.eu[^\)]+?) - URL (non-greedy, stops before first )
        # - (?:\s+"[^"]*")? - optional "Copy to clipboard" text
        # - \) - closing parenthesis
        # - (.+)$ - heading text after the link
        pattern = re.compile(
            r'^(#{2,6})\s+\[\s*\]\('
            r'(https://sentiwiki\.copernicus\.eu[^\)]+?)'  # URL (non-greedy, stops before )
            r'(?:\s+"[^"]*")?\)'  # Optional "Copy to clipboard" then closing )
            r'(.+)$',  # Heading text after the link
            re.MULTILINE,
        )

        for match in pattern.finditer(markdown):
            heading_text = match.group(3).strip()
            url = match.group(2).strip()

            if heading_text and url:
                # Normalize heading text for matching (same normalization as inject_heading_links)
                normalized_text = self._normalize_heading_text_for_matching(heading_text)
                # Use normalized text as key
                heading_anchors[normalized_text] = url
                logger.debug(f"Extracted heading anchor: '{normalized_text}' -> {url}")

        return heading_anchors
    
    def _normalize_heading_text_for_matching(self, text: str) -> str:
        """Normalize heading text for matching (handles whitespace differences).
        
        Args:
            text: Heading text
            
        Returns:
            Normalized text (lowercase, normalized whitespace)
        """
        # Normalize whitespace (multiple spaces -> single space)
        normalized = re.sub(r'\s+', ' ', text.strip())
        return normalized

    def inject_heading_links(self, markdown: str, heading_anchors: Dict[str, str]) -> str:
        """Inject canonical SentiWiki links into cleaned markdown headings.
        
        After cleaning, headings look like:
            ##  Mesoscales Process Monitoring
        
        Using the mapping from `extract_heading_anchors`, we rewrite them as:
            ## [Mesoscales Process Monitoring](https://sentiwiki...#...)
        
        This gives us stable, ground-truth links to the original SentiWiki
        subsections instead of reconstructing anchors heuristically.
        """
        if not heading_anchors:
            return markdown

        lines = markdown.split("\n")
        heading_pattern = re.compile(r'^(#{2,6})\s+(.+)$')

        for idx, line in enumerate(lines):
            m = heading_pattern.match(line)
            if not m:
                continue

            hashes, title_part = m.group(1), m.group(2)
            clean_title = title_part.strip()

            # If we already have a markdown link in the heading, skip
            if "[" in clean_title and "](" in clean_title:
                continue

            # Normalize the heading text for matching (same normalization as extract_heading_anchors)
            normalized_title = self._normalize_heading_text_for_matching(clean_title)
            url = heading_anchors.get(normalized_title)
            
            if not url:
                # Try case-insensitive matching as fallback
                for key, value in heading_anchors.items():
                    if normalized_title.lower() == key.lower():
                        url = value
                        logger.debug(f"Matched heading (case-insensitive): '{normalized_title}' -> {url}")
                        break
            
            if not url:
                # Log unmatched headings for debugging (but don't spam)
                if len(heading_anchors) > 0:  # Only log if we have anchors to match against
                    logger.debug(f"No URL found for heading: '{normalized_title}' (available: {list(heading_anchors.keys())[:3]}...)")
                continue

            # Replace with linked heading
            lines[idx] = f"{hashes} [{clean_title}]({url})"
            logger.debug(f"Injected link into heading: '{clean_title}' -> {url}")

        return "\n".join(lines)

    def clean_boilerplate(self, markdown: str) -> str:
        """Remove boilerplate content.
        
        Args:
            markdown: Markdown content
            
        Returns:
            Cleaned markdown
        """
        for pattern in self.remove_patterns:
            markdown = re.sub(pattern, "", markdown, flags=re.DOTALL | re.MULTILINE)
        return markdown

    def normalize_headings(self, markdown: str) -> str:
        """Normalize heading structure for better hierarchy.
        
        IMPORTANT: This method should NOT remove SentiWiki heading links in the format:
        ##  [ ](url "Copy to clipboard")Heading Text
        
        Those links are needed for extract_heading_anchors to work. Instead, we just
        normalize whitespace and clean up empty link patterns.
        
        Args:
            markdown: Markdown content
            
        Returns:
            Normalized markdown
        """
        # Normalize whitespace in headings (multiple spaces -> single space)
        # But preserve the [ ](url) pattern for SentiWiki headings
        markdown = re.sub(r"^(#{2,6})\s{2,}", r"\1 ", markdown, flags=re.MULTILINE)
        
        # Only remove empty link patterns that don't have text after them
        # Pattern: ##  [ ](url)  (with nothing after)
        markdown = re.sub(r"^(#{2,6})\s+\[\s*\]\([^\)]+\)\s*$", r"\1 ", markdown, flags=re.MULTILINE)
        
        return markdown

    def extract_sections(self, markdown: str) -> List[Dict[str, str]]:
        """Extract sections with their headings for better chunking.
        
        Args:
            markdown: Markdown content
            
        Returns:
            List of sections with metadata
        """
        sections = []
        
        # Split by H2 headings
        h2_pattern = r"##\s+(.+?)(?=\n##|\Z)"
        matches = re.finditer(h2_pattern, markdown, re.DOTALL)
        
        for match in matches:
            heading = match.group(1).split('\n')[0].strip()
            content = match.group(1).strip()
            
            if content and len(content) > 50:  # Only meaningful sections
                sections.append({
                    "heading": heading,
                    "content": content,
                    "level": "h2"
                })
        
        return sections

    def clean_links(self, markdown: str) -> str:
        """Clean up excessive or redundant links.
        
        Args:
            markdown: Markdown content
            
        Returns:
            Cleaned markdown
        """
        # Keep content links but clean up formatting
        # Remove empty links
        markdown = re.sub(r"\[\s*\]\(.*?\)", "", markdown)
        
        # Clean table of contents: convert long links to just text
        # Pattern: 1. [ Long Title with Description ](https://long-url.html)
        # Replace with: 1. Long Title with Description
        toc_line_pattern = r"(\d+\.\s*)\[([^\]]+)\]\(https://[^\)]+\)"
        markdown = re.sub(toc_line_pattern, r"\1\2", markdown)
        
        # Remove very long link descriptions (keep only first part)
        def shorten_link_text(match):
            num = match.group(1)
            text = match.group(2)
            # If text is very long (100+ chars), truncate it
            if len(text) > 100:
                # Try to find a good break point (sentence end, or word boundary)
                truncated = text[:100]
                # Find last space or punctuation
                last_space = max(truncated.rfind(' '), truncated.rfind('.'), truncated.rfind(','))
                if last_space > 50:  # Only truncate if we have a good break point
                    truncated = truncated[:last_space] + "..."
                else:
                    truncated = truncated[:100] + "..."
                return f"{num}{truncated}"
            return f"{num}{text}"
        
        # Apply shortening to TOC lines
        toc_long_pattern = r"(\d+\.\s*)(.{100,})"
        markdown = re.sub(toc_long_pattern, shorten_link_text, markdown)
        
        return markdown

    def remove_excessive_whitespace(self, markdown: str) -> str:
        """Remove excessive whitespace while preserving structure.
        
        Args:
            markdown: Markdown content
            
        Returns:
            Cleaned markdown
        """
        # Replace multiple newlines with max 2
        markdown = re.sub(r"\n{3,}", "\n\n", markdown)
        
        # Remove trailing whitespace from lines
        markdown = re.sub(r"[ \t]+$", "", markdown, flags=re.MULTILINE)
        
        # Remove leading/trailing whitespace
        markdown = markdown.strip()
        
        return markdown

    def extract_metadata(self, markdown: str, original_metadata: Dict) -> Dict:
        """Extract enhanced metadata from content.
        
        Args:
            markdown: Cleaned markdown content
            original_metadata: Original metadata from scraper
            
        Returns:
            Enhanced metadata dictionary
        """
        metadata = original_metadata.copy()
        
        # Extract main title if not present
        if not metadata.get('title'):
            h1_match = re.search(r"^#\s+(.+?)$", markdown, re.MULTILINE)
            if h1_match:
                metadata['title'] = h1_match.group(1).strip()
        
        # Extract all headings for context
        headings = re.findall(r"^#{2,6}\s+(.+?)$", markdown, re.MULTILINE)
        if headings:
            metadata['sections'] = headings[:10]  # Top 10 sections
        
        # Estimate reading time (words / 200 wpm)
        word_count = len(markdown.split())
        metadata['word_count'] = word_count
        metadata['reading_time_minutes'] = max(1, word_count // 200)
        
        # Detect document type based on URL or title
        url = metadata.get('url', '').lower()
        if 'mission' in url:
            metadata['document_type'] = 'mission_overview'
        elif 'application' in url:
            metadata['document_type'] = 'applications'
        elif 'product' in url:
            metadata['document_type'] = 'products'
        elif 'processing' in url:
            metadata['document_type'] = 'processing'
        elif 'instrument' in url:
            metadata['document_type'] = 'instrument'
        else:
            metadata['document_type'] = 'general'
        
        # Extract and normalize mission from URL
        extracted_mission = MetadataNormalizer.extract_mission_from_url(url)
        if extracted_mission:
            metadata['mission'] = extracted_mission
        
        # Set source to sentiwiki (this cleaner is for SentiWiki)
        metadata['source'] = 'sentiwiki'
        
        # Normalize all metadata fields
        metadata = MetadataNormalizer.normalize_metadata(metadata)
         
        return metadata

    def clean_navigation_blocks(self, markdown: str) -> str:
        """Remove large navigation blocks that are just lists of links.
        
        Args:
            markdown: Markdown content
            
        Returns:
            Cleaned markdown
        """
        lines = markdown.split('\n')
        cleaned_lines = []
        in_nav_block = False
        nav_block_start = 0
        consecutive_nav_lines = 0
        
        for i, line in enumerate(lines):
            # Check if line is a navigation link (bullet point with dataspace link)
            is_nav_link = (
                line.strip().startswith('*') and 
                ('documentation.dataspace.copernicus.eu' in line or 'dataspace.copernicus.eu' in line)
            )
            
            # Also check for breadcrumb patterns
            is_breadcrumb = (
                line.strip().startswith('[') and 
                'documentation.dataspace.copernicus.eu' in line and
                ('!' in line or line.count('[') >= 2)
            )
            
            if is_nav_link or is_breadcrumb:
                if not in_nav_block:
                    in_nav_block = True
                    nav_block_start = i
                    consecutive_nav_lines = 1
                else:
                    consecutive_nav_lines += 1
            else:
                # If we were in a nav block and it had 3+ lines, skip it
                if in_nav_block and consecutive_nav_lines >= 3:
                    # Don't add the nav block lines
                    in_nav_block = False
                    consecutive_nav_lines = 0
                elif in_nav_block:
                    # Small nav block, keep it (might be legitimate content)
                    for j in range(nav_block_start, i):
                        cleaned_lines.append(lines[j])
                    in_nav_block = False
                    consecutive_nav_lines = 0
                
                # Add current line if it's not part of a large nav block
                if not (in_nav_block and consecutive_nav_lines >= 3):
                    cleaned_lines.append(line)
        
        # Handle nav block at end of file
        if in_nav_block and consecutive_nav_lines >= 3:
            # Skip the nav block
            pass
        elif in_nav_block:
            # Small nav block, keep it
            for j in range(nav_block_start, len(lines)):
                cleaned_lines.append(lines[j])
        
        result = '\n'.join(cleaned_lines)
        
        # Additional cleanup: remove breadcrumb patterns that might have been missed
        # Pattern: [ ! ](url) [ Documentation ](url) followed by numbered items
        breadcrumb_pattern = r"\[ ! \]\([^\)]+\)\s*\[[^\]]+\]\([^\)]+\)\s*(?:\d+\.\s*\[[^\]]+\]\([^\)]+\)\s*)+"
        result = re.sub(breadcrumb_pattern, "", result, flags=re.MULTILINE)
        
        return result

    def clean_for_rag(self, markdown: str, metadata: Dict) -> Tuple[str, Dict]:
        """Complete cleaning pipeline for RAG optimization.
        
        Args:
            markdown: Raw markdown content
            metadata: Original metadata
            
        Returns:
            Tuple of (cleaned_markdown, enhanced_metadata)
        """
        # Step 1: Remove boilerplate
        cleaned = self.clean_boilerplate(markdown)
        
        # Step 2: Remove navigation
        cleaned = self.clean_navigation(cleaned)
        
        # Step 3: Normalize headings
        cleaned = self.normalize_headings(cleaned)
        
        # Step 4: Clean links
        cleaned = self.clean_links(cleaned)
        
        # Step 5: Remove excessive whitespace
        cleaned = self.remove_excessive_whitespace(cleaned)
        
        # Step 6: Extract enhanced metadata
        enhanced_metadata = self.extract_metadata(cleaned, metadata)
        
        # Step 7: Extract sections for potential use
        sections = self.extract_sections(cleaned)
        if sections:
            enhanced_metadata['num_sections'] = len(sections)
        
        return cleaned, enhanced_metadata

    def create_rag_optimized_markdown(
        self, 
        markdown: str, 
        metadata: Dict,
        include_toc: bool = True
    ) -> str:
        """Create RAG-optimized markdown with enhanced frontmatter.
        
        Args:
            markdown: Raw markdown content
            metadata: Original metadata
            include_toc: Whether to include table of contents
            
        Returns:
            Formatted markdown string
        """
        # Extract canonical heading anchors from raw markdown *before* cleaning.
        # This uses the SentiWiki-specific "[ ](url \"Copy to clipboard\")Title"
        # pattern from the Crawl4AI output.
        heading_anchors = self.extract_heading_anchors(markdown)

        # Clean the content
        cleaned_content, enhanced_metadata = self.clean_for_rag(markdown, metadata)
        
        # Ensure metadata is normalized (extract_metadata already normalizes, but double-check)
        enhanced_metadata = MetadataNormalizer.normalize_metadata(enhanced_metadata)
        
        # Build frontmatter with normalized metadata
        frontmatter = ["---"]
        frontmatter.append(f"title: {enhanced_metadata.get('title', 'Untitled')}")
        frontmatter.append(f"url: {enhanced_metadata.get('url', '')}")
        
        if enhanced_metadata.get('description'):
            desc = enhanced_metadata['description'].replace('\n', ' ')[:200]
            frontmatter.append(f"description: {desc}")
        
        if enhanced_metadata.get('mission'):
            # Use normalized mission value
            frontmatter.append(f"mission: {enhanced_metadata['mission']}")
        
        # Use normalized document_type value
        frontmatter.append(f"document_type: {enhanced_metadata.get('document_type', 'general')}")
        frontmatter.append(f"source: {enhanced_metadata.get('source', 'sentiwiki')}")
        frontmatter.append(f"word_count: {enhanced_metadata.get('word_count', 0)}")
        frontmatter.append(f"reading_time: {enhanced_metadata.get('reading_time_minutes', 1)} min")
        
        if enhanced_metadata.get('sections'):
            frontmatter.append(f"sections: {len(enhanced_metadata['sections'])}")
        
        if enhanced_metadata.get('keywords'):
            frontmatter.append(f"keywords: {enhanced_metadata['keywords']}")
        
        frontmatter.append("---")
        frontmatter.append("")
        
        # Add title as H1
        result = "\n".join(frontmatter)
        result += f"# {enhanced_metadata.get('title', 'Untitled')}\n\n"
        
        # Add table of contents if requested and sections exist
        if include_toc and enhanced_metadata.get('sections'):
            result += "## Table of Contents\n\n"
            for i, section in enumerate(enhanced_metadata['sections'][:10], 1):
                # Clean section title (remove links and extra text)
                clean_section = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', section)  # Remove markdown links
                clean_section = re.sub(r'\s+', ' ', clean_section).strip()  # Normalize whitespace
                # Truncate if too long (keep first 100 chars)
                if len(clean_section) > 100:
                    clean_section = clean_section[:100] + "..."
                result += f"{i}. {clean_section}\n"
            result += "\n---\n\n"
        
        # Inject section links into headings using ground-truth anchors
        cleaned_with_links = self.inject_heading_links(cleaned_content, heading_anchors)

        # Add cleaned content (with heading links)
        result += cleaned_with_links
        
        return result


class ChunkCleaner:
    """Lightweight cleaner for individual chunks during chunking process.
    
    This is different from MarkdownCleaner which processes full documents.
    This class only cleans individual chunks.
    """

    IMAGE_MD_PATTERN = re.compile(r"!\[.*?\]\(.*?\)")
    IMAGE_FILE_PATTERN = re.compile(r"\b[\w\-]+\.(png|jpg|jpeg|gif)\b", re.IGNORECASE)
    SKIP_LINK_PATTERN = re.compile(r"\[.*?(skip|back to).*?\]\(.*?\)", re.IGNORECASE)
    LONE_EXCLAMATION_PATTERN = re.compile(r"^\s*!\s*$", re.MULTILINE)
    DIVIDER_PATTERN = re.compile(r"^\s*[-*_]{3,}\s*$", re.MULTILINE)
    MULTI_NEWLINE_PATTERN = re.compile(r"\n{3,}")

    def clean(self, text: str) -> str:
        """Clean a chunk of text.
        
        Args:
            text: Chunk text to clean
            
        Returns:
            Cleaned text
        """
        if not text:
            return ""

        text = self.IMAGE_MD_PATTERN.sub("", text)
        text = self.IMAGE_FILE_PATTERN.sub("", text)
        text = self.SKIP_LINK_PATTERN.sub("", text)
        text = self.LONE_EXCLAMATION_PATTERN.sub("", text)
        text = self.DIVIDER_PATTERN.sub("", text)
        text = self.MULTI_NEWLINE_PATTERN.sub("\n\n", text)

        return text.strip()

    def is_garbage_chunk(self, text: str, heading_path: str) -> bool:
        """Check if a chunk is garbage and should be discarded.
        
        Args:
            text: Chunk text
            heading_path: Path of headings leading to this chunk
            
        Returns:
            True if chunk should be discarded
        """
        if heading_path and "table of contents" in heading_path.lower():
            return True

        stripped = text.strip()
        if len(stripped) < 50:
            return True

        if not re.search(r"[a-zA-Z]{2,}", stripped):
            return True

        return False

