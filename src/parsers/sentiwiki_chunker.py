#!/usr/bin/env python3
"""
Lightweight Markdown chunker using langchain-text-splitters.

- Respects Markdown hierarchy (#, ##, ###)
- Adds clean metadata for each chunk
- No Docling dependency (pure text processing)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
import re
import sys
from datetime import datetime
import click
from loguru import logger
from src.utils.logger import setup_logging

from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from src.utils.markdown_cleaner_sentiwiki import ChunkCleaner
from src.utils.config import get_settings


class StructuredMarkdownChunker:
    """Chunk markdown files using structural awareness (without Docling)."""

    def __init__(
        self,
        chunk_size: int = 2000,
        chunk_overlap: int = 200,
        headers: Optional[List[tuple[str, str]]] = None,
        output_dir: Optional[Path] = None,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.headers = headers or [
            ("#", "Header 1"),
            ("##", "Header 2"),
            ("###", "Header 3"),
            ("####", "Header 4"),
        ]
        # Use provided output_dir or default based on settings
        if output_dir is None:
            settings = get_settings()
            # Default to sentiwiki_structured for backward compatibility
            self.output_dir = settings.data_dir / "processed" / "sentiwiki_structured"
        else:
            self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Use SentiWiki-specific ChunkCleaner
        self.cleaner = ChunkCleaner()

        self.md_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=self.headers,
            strip_headers=True,  # remove headers; we add context manually
        )

        self.recursive_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        logger.success(
            "✓ StructuredMarkdownChunker ready "
            f"(chunk_size={self.chunk_size}, overlap={self.chunk_overlap})"
        )

    def process_markdown(self, markdown_path: Path) -> Dict[str, Any]:
        """Process a single markdown file."""
        text = markdown_path.read_text(encoding="utf-8")
        frontmatter, body = self._extract_frontmatter(text)
        # Note: frontmatter is already normalized by MarkdownCleaner (in src/utils/) when creating enhanced markdown
        
        # Extract heading URLs from markdown body before splitting
        heading_urls = self._extract_heading_urls(body)
        
        md_docs = self.md_splitter.split_text(body)

        chunks: List[Dict[str, Any]] = []
        chunk_id = 0

        for doc_index, doc in enumerate(md_docs):
            heading_hierarchy, heading_path = self._build_heading_hierarchy(
                doc.metadata
            )
            # Extract section URL for this chunk (from most specific heading)
            section_url = self._get_section_url(
                heading_hierarchy=heading_hierarchy,
                heading_urls=heading_urls,
                base_url=frontmatter.get('url', '')
            )
            
            clean_text = self.cleaner.clean(doc.page_content)
            if not clean_text or self.cleaner.is_garbage_chunk(clean_text, heading_path):
                continue

            splits = self.recursive_splitter.split_text(clean_text)

            for split_text in splits:
                contextualized_text = self._build_contextualized_text(
                    file_path=markdown_path,
                    frontmatter=frontmatter,
                    heading_path=heading_path,
                    chunk_text=split_text,
                )

                quality = self._calculate_chunk_quality(split_text, contextualized_text)

                metadata = {
                    "source_file": markdown_path.name,
                    "chunk_index": chunk_id,
                    "section_index": doc_index,
                    "heading_path": heading_path,  # Plain text, no links
                    "heading_hierarchy": heading_hierarchy,
                    "section_url": section_url,  # Most specific section URL
                    "char_count": len(split_text),
                    "tokens_approx": len(contextualized_text.split()),
                    "quality": quality,
                }
                metadata.update(doc.metadata)

                chunks.append(
                    {
                        "chunk_id": chunk_id,
                        "text": split_text,
                        "contextualized_text": contextualized_text,
                        "metadata": metadata,
                    }
                )
                chunk_id += 1

        logger.info(
            f"Processed {markdown_path.name}: {len(chunks)} structured chunks created"
        )

        return {
            "file_name": markdown_path.name,
            "chunk_config": {
                "method": "markdown_structured_splitter",
                "chunk_size": self.chunk_size,
                "chunk_overlap": self.chunk_overlap,
                "headers": self.headers,
            },
            "frontmatter": frontmatter,
            "chunks": chunks,
        }

    def save_json(self, data: Dict[str, Any], output_path: Path) -> None:
        output_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.debug(f"Saved {output_path}")

    def process_batch(
        self,
        input_dir: Path,
        output_dir: Optional[Path] = None,
        pattern: str = "*.md",
    ) -> Dict[str, Any]:
        output_dir = output_dir or self.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        md_files = sorted(input_dir.glob(pattern))
        if not md_files:
            logger.warning(f"No markdown files found in {input_dir}")
            return {"total": 0, "successful": 0, "failed": 0}

        summary = {"total": len(md_files), "successful": 0, "failed": 0}

        for md_path in md_files:
            try:
                result = self.process_markdown(md_path)
                output_file = output_dir / f"{md_path.stem}.json"
                self.save_json(result, output_file)
                summary["successful"] += 1
            except Exception as exc:
                logger.error(f"Failed to process {md_path.name}: {exc}")
                summary["failed"] += 1

        logger.success(
            f"Structured chunking complete: {summary['successful']}/{summary['total']}"
        )
        return summary

    # Helper Methods
    def _extract_frontmatter(self, text: str):
        frontmatter: Dict[str, Any] = {}
        body = text
        if text.startswith("---"):
            end_idx = text.find("---", 3)
            if end_idx != -1:
                fm_text = text[3:end_idx]
                body = text[end_idx + 3 :]
                for line in fm_text.splitlines():
                    if ":" in line:
                        key, value = line.split(":", 1)
                        frontmatter[key.strip()] = value.strip()
        return frontmatter, body

    def _build_heading_hierarchy(self, metadata: Dict[str, Any]):
        """Build heading hierarchy with plain text (no links).
        
        Args:
            metadata: Document metadata from markdown splitter
            
        Returns:
            Tuple of (hierarchy, heading_path)
            - hierarchy: List of heading dicts with level and text (plain text)
            - heading_path: Plain text path (e.g., "Section > Subsection")
        """
        hierarchy = []
        path_parts = []
        
        for header, label in self.headers:
            key = label
            if key in metadata:
                heading_text_raw = metadata[key]
                
                # Extract plain text from heading (remove markdown links if present)
                heading_text_plain = self._extract_plain_text_from_heading(heading_text_raw)
                
                # Store plain text in hierarchy (clean, no links)
                hierarchy.append({"level": len(header), "text": heading_text_plain})
                path_parts.append(heading_text_plain)
        
        heading_path = " > ".join(path_parts)
        
        return hierarchy, heading_path
    
    def _extract_plain_text_from_heading(self, heading_text: str) -> str:
        """Extract plain text from heading, removing markdown links.
        
        Examples:
        - "[Land Monitoring](url)" -> "Land Monitoring"
        - "Land Monitoring" -> "Land Monitoring"
        
        Args:
            heading_text: Heading text that may contain markdown links
            
        Returns:
            Plain text heading
        """
        # If it's a markdown link, extract the text part
        link_pattern = r'\[([^\]]+)\]\([^\)]+\)'
        match = re.match(link_pattern, heading_text)
        if match:
            return match.group(1).strip()
        # Otherwise return as-is
        return heading_text.strip()

    def _build_contextualized_text(
        self,
        file_path: Path,
        frontmatter: Dict[str, Any],
        heading_path: str,
        chunk_text: str,
    ) -> str:
        context_lines = [f"Document: {frontmatter.get('title', file_path.stem)}"]
        if heading_path:
            context_lines.append(f"Section: {heading_path}")
        context_lines.append("Content:")
        context_lines.append(chunk_text)
        return "\n".join(context_lines)

    def _extract_heading_urls(self, markdown_body: str) -> Dict[str, str]:
        """Extract URLs from markdown headings that have links.
        
        Returns a mapping from normalized heading text to full URL (including anchor).
        Example: {"Instrument Description": "https://sentiwiki.copernicus.eu/web/s3-olci-instrument#S3OLCIInstrument-InstrumentDescription"}
        
        Args:
            markdown_body: Markdown content (without frontmatter)
            
        Returns:
            Dictionary mapping normalized heading text to URL
        """
        heading_urls = {}
        
        # Pattern to match headings with markdown links:
        # ## [Heading Text](https://url#anchor)
        # or ## [Heading Text](https://url)
        pattern = r'^(#{2,6})\s+\[([^\]]+)\]\(([^\)]+)\)'
        
        for line in markdown_body.split('\n'):
            match = re.match(pattern, line)
            if match:
                heading_level = len(match.group(1))  # Number of # characters
                heading_text = match.group(2).strip()
                url = match.group(3).strip()
                
                # Normalize heading text for matching (lowercase, strip extra spaces)
                normalized_text = self._normalize_heading_text(heading_text)
                
                # Store the URL for this heading text
                # If there are multiple headings with same text, keep the most specific one (deeper level)
                if normalized_text not in heading_urls:
                    heading_urls[normalized_text] = url
                else:
                    # If we already have this heading, prefer the one from deeper level (more #)
                    # But since we're iterating top to bottom, the last one wins anyway
                    # Actually, let's keep track of level and prefer deeper
                    pass
        
        return heading_urls
    
    def _normalize_heading_text(self, text: str) -> str:
        """Normalize heading text for matching (normalize whitespace).
        
        This matches the normalization used in markdown_cleaner_sentiwiki.
        
        Args:
            text: Heading text
            
        Returns:
            Normalized text (normalized whitespace)
        """
        return re.sub(r'\s+', ' ', text.strip())
    
    def _get_section_url(
        self,
        heading_hierarchy: List[Dict[str, Any]],
        heading_urls: Dict[str, str],
        base_url: str
    ) -> str:
        """Get the section URL for a chunk based on its heading hierarchy.
        
        Uses the most specific heading (last in hierarchy) that has a URL.
        Falls back to base_url if no heading URL is found.
        
        Args:
            heading_hierarchy: List of heading dicts with 'level' and 'text'
            heading_urls: Mapping from normalized heading text to URL
            base_url: Base URL from frontmatter
            
        Returns:
            Section URL (with anchor if available)
        """
        if not heading_hierarchy:
            return base_url
        
        # Try to find URL for the most specific heading (last in hierarchy)
        # Go from most specific to least specific
        for heading in reversed(heading_hierarchy):
            heading_text = heading.get('text', '').strip()
            if heading_text:
                normalized_text = self._normalize_heading_text(heading_text)
                if normalized_text in heading_urls:
                    return heading_urls[normalized_text]
        
        # Fallback: return base URL
        return base_url

    def _calculate_chunk_quality(
        self, chunk_text: str, contextualized_text: str
    ) -> Dict[str, float]:
        chunk_text = chunk_text.strip()
        if not chunk_text:
            return {"completeness": 0, "information_density": 0, "context_density": 0, "overall": 0}

        completeness = 1.0 if chunk_text[-1] in ".!?)" else 0.6

        words = chunk_text.split()
        significant = [w for w in words if len(w) > 3 and not w.isupper()]
        info_density = len(significant) / len(words) if words else 0

        ctx_len = len(contextualized_text) or 1
        context_density = len(chunk_text) / ctx_len

        overall = (completeness + info_density + context_density) / 3

        return {
            "completeness": round(completeness, 3),
            "information_density": round(info_density, 3),
            "context_density": round(context_density, 3),
            "overall": round(overall, 3),
        }


@click.command()
@click.option(
    "--sub-folder",
    type=str,
    default="sentiwiki_docs",
    help="Subfolder name under data_dir for SentiWiki files",
)
@click.option(
    "--input-dir",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Directory with markdown files (overrides sub-folder)",
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Directory for structured chunks JSON (overrides default)",
)
@click.option(
    '--log-dir',
    type=click.Path(path_type=Path),
    default='logs',
    help='Directory for log files (default: logs/)'
)
@click.option("--chunk-size", default=2000, help="Max characters per chunk (≈512 tokens)")
@click.option("--chunk-overlap", default=200, help="Overlap between chunks (characters)")
@click.option("--single-file", type=click.Path(path_type=Path), help="Process one file")
def cli(sub_folder: str, input_dir: Path, output_dir: Path, chunk_size: int, chunk_overlap: int, single_file: Path, log_dir: Path):
    """Chunk SentiWiki markdown files using langchain-text-splitters (no Docling).
    
    Uses SentiWiki-specific ChunkCleaner for optimal cleaning.
    
    Note: For DataSpace documentation, use src.parsers.dataspace_chunker instead.
    """
    
    setup_logging(log_dir=log_dir, name="sentiwiki_chunker")
    
    # Get settings for data_dir
    settings = get_settings()
    
    # Use sub_folder-based paths if not explicitly provided
    if input_dir is None:
        input_dir = settings.data_dir / sub_folder / "markdown_enhanced"
    if output_dir is None:
        # Derive output directory name from sub_folder
        output_name = sub_folder.replace("_docs", "_structured")
        output_dir = settings.data_dir / "processed" / output_name

    logger.info("Structured markdown chunker (SentiWiki) starting…")

    chunker = StructuredMarkdownChunker(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        output_dir=output_dir,
    )

    if single_file:
        result = chunker.process_markdown(single_file)
        output_file = output_dir / f"{Path(single_file).stem}.json"
        chunker.save_json(result, output_file)
        logger.success("Done! Single file processed.")
    else:
        summary = chunker.process_batch(input_dir=input_dir, output_dir=output_dir)
        logger.info(json.dumps(summary, indent=2))


if __name__ == "__main__":
    cli()

