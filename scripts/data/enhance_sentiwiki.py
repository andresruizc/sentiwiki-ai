#!/usr/bin/env python3
"""Enhance existing markdown files from SentiWiki for better RAG performance."""

import json
import sys
from pathlib import Path
from typing import Optional

import click
from loguru import logger

from src.utils.markdown_cleaner_sentiwiki import MarkdownCleaner
from src.utils.logger import setup_logging
from src.utils.config import get_settings


def enhance_markdown_file(json_path: Path, md_path: Path, output_dir: Path, cleaner: MarkdownCleaner) -> bool:
    """Enhance a single markdown file.
    
    Args:
        json_path: Path to JSON file with metadata
        md_path: Path to existing markdown file
        output_dir: Output directory for enhanced markdown
        cleaner: MarkdownCleaner instance
        
    Returns:
        True if successful
    """
    try:
        # Load JSON metadata
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not data.get('success'):
            logger.warning(f"Skipping failed scrape: {json_path.name}")
            return False
        
        # Load existing markdown
        with open(md_path, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
        
        # Remove existing frontmatter if present
        if markdown_content.startswith('---'):
            parts = markdown_content.split('---', 2)
            if len(parts) >= 3:
                markdown_content = parts[2].strip()
        
        # Create enhanced markdown
        enhanced_md = cleaner.create_rag_optimized_markdown(
            markdown=data.get('markdown', markdown_content),
            metadata={
                'title': data.get('title', ''),
                'url': data.get('url', ''),
                'description': data.get('description', ''),
                'keywords': data.get('keywords', ''),
            },
            include_toc=True
        )
        
        # Save enhanced version
        output_path = output_dir / md_path.name
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(enhanced_md)
        
        # Get word count for reporting
        word_count = len(enhanced_md.split())
        original_count = len(markdown_content.split())
        reduction = ((original_count - word_count) / original_count * 100) if original_count > 0 else 0
        
        logger.success(
            f"✓ Enhanced: {md_path.name} "
            f"({original_count:,}→{word_count:,} words, {reduction:.1f}% reduction)"
        )
        return True
        
    except Exception as e:
        logger.error(f"Error enhancing {md_path.name}: {e}")
        return False


@click.command()
@click.option(
    '--sub-folder',
    type=str,
    default='sentiwiki_docs',
    help='Subfolder name under data_dir for SentiWiki files (default: sentiwiki_docs)'
)
@click.option(
    '--json-dir',
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help='Directory containing JSON files with metadata (overrides sub-folder)'
)
@click.option(
    '--md-dir',
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help='Directory containing raw markdown files (overrides sub-folder)'
)
@click.option(
    '--output-dir',
    type=click.Path(path_type=Path),
    default=None,
    help='Output directory for enhanced markdown files (overrides sub-folder)'
)
@click.option(
    '--log-dir',
    type=click.Path(path_type=Path),
    default='logs',
    help='Directory for log files'
)
def cli(sub_folder: str, json_dir: Path, md_dir: Path, output_dir: Path, log_dir: Path):
    """Enhance existing markdown files from SentiWiki for better RAG performance.
    
    This script uses SentiWiki-specific cleaners:
    - markdown_cleaner_sentiwiki
    - metadata_normalizer_sentiwiki
    
    It:
    - Removes navigation menus and boilerplate
    - Cleans up headings and links
    - Adds enhanced metadata (document type, mission, word count) with normalization
    - Includes table of contents
    - Normalizes structure for better RAG
    
    Examples:
    
        # Use default paths (data/sentiwiki_docs/)
        python scripts/data/enhance_sentiwiki.py
        
        # Custom sub-folder
        python scripts/data/enhance_sentiwiki.py --sub-folder my_sentiwiki_data
        
        # Override specific paths
        python scripts/data/enhance_sentiwiki.py \\
            --json-dir data/custom/crawl4ai \\
            --md-dir data/custom/markdown \\
            --output-dir data/custom/markdown_enhanced
    
    Note: For DataSpace documentation, use scripts/data/enhance_dataspace.py instead.
    """
    setup_logging(log_dir=log_dir, name="enhance_sentiwiki")
    
    # Get settings for data_dir
    settings = get_settings()
    
    # Use sub_folder-based paths if not explicitly provided
    if json_dir is None:
        json_dir = settings.data_dir / sub_folder / "crawl4ai"
    if md_dir is None:
        md_dir = settings.data_dir / sub_folder / "markdown"
    if output_dir is None:
        output_dir = settings.data_dir / sub_folder / "markdown_enhanced"
    
    logger.info("=" * 80)
    logger.info("Enhancing SentiWiki Markdown Files for Better RAG Performance")
    logger.info("=" * 80)
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize SentiWiki cleaner
    cleaner = MarkdownCleaner()
    
    # Get markdown files
    md_files = [f for f in md_dir.glob("*.md") if f.name != "README.md"]
    
    if not md_files:
        logger.error(f"No markdown files found in {md_dir}")
        return 1
    
    logger.info(f"Found {len(md_files)} markdown files")
    logger.info(f"JSON directory: {json_dir}")
    logger.info(f"Markdown directory: {md_dir}")
    logger.info(f"Output directory: {output_dir}")
    logger.info("")
    logger.info("Enhancements:")
    logger.info("  • Remove navigation menus and boilerplate")
    logger.info("  • Clean up headings and links")
    logger.info("  • Add enhanced metadata (document type, mission, word count)")
    logger.info("  • Normalize metadata (mission: S3, S5P, etc.)")
    logger.info("  • Include table of contents")
    logger.info("  • Normalize structure for better RAG")
    logger.info("")
    
    # Process each file
    success_count = 0
    skipped_count = 0
    total_original_words = 0
    total_enhanced_words = 0
    
    for md_file in md_files:
        # Find corresponding JSON file
        json_file = json_dir / f"{md_file.stem}.json"
        
        if not json_file.exists():
            logger.warning(f"No JSON file for {md_file.name}, skipping")
            skipped_count += 1
            continue
        
        # Count words before
        with open(md_file, 'r') as f:
            total_original_words += len(f.read().split())
        
        if enhance_markdown_file(json_file, md_file, output_dir, cleaner):
            success_count += 1
            
            # Count words after
            output_file = output_dir / md_file.name
            if output_file.exists():
                with open(output_file, 'r') as f:
                    total_enhanced_words += len(f.read().split())
    
    # Summary
    reduction = ((total_original_words - total_enhanced_words) / total_original_words * 100) if total_original_words > 0 else 0
    
    logger.info("")
    logger.info("=" * 80)
    logger.success("✅ Enhancement complete!")
    logger.info(f"   Processed: {success_count}/{len(md_files)} files")
    if skipped_count > 0:
        logger.info(f"   Skipped: {skipped_count} files (no JSON metadata)")
    logger.info(f"   Total words: {total_original_words:,} → {total_enhanced_words:,}")
    logger.info(f"   Reduction: {reduction:.1f}% (removed boilerplate/noise)")
    logger.info(f"   Location: {output_dir}")
    logger.info("")
    logger.info("💡 Benefits:")
    logger.info("   ✓ Cleaner content = Better embeddings")
    logger.info("   ✓ Enhanced metadata = Better retrieval")
    logger.info("   ✓ Normalized metadata = Consistent filtering")
    logger.info("   ✓ Structured format = Better chunking")
    logger.info("   ✓ Table of contents = Better navigation")
    logger.info("")
    logger.success("🚀 Ready for RAG pipeline!")
    logger.info("=" * 80)
    
    return 0


if __name__ == "__main__":
    sys.exit(cli())

