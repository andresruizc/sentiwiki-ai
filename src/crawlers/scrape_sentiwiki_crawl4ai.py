"""Enhanced web scraper for SentiWiki using Crawl4AI for better GenAI data extraction."""

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Set
from urllib.parse import urljoin, urlparse

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from loguru import logger
from tqdm.asyncio import tqdm

from src.utils.markdown_cleaner_sentiwiki import MarkdownCleaner
from src.utils.config import get_settings


class SentiWikiCrawl4AIScraper:
    """Enhanced scraper for SentiWiki using Crawl4AI for GenAI applications."""

    def __init__(self, sub_folder: str = "sentiwiki_docs") -> None:
        """Initialize the scraper.
        
        Args:
            sub_folder: Subfolder name under data_dir for SentiWiki outputs
        """
        self.settings = get_settings()
        self.base_url = "https://sentiwiki.copernicus.eu/web/sentiwiki"
        self.sub_folder = sub_folder
        self.output_dir = self.settings.data_dir / self.sub_folder / "crawl4ai"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Markdown output directory (for easy visualization and Docling)
        self.markdown_dir = self.settings.data_dir / self.sub_folder / "markdown"
        self.markdown_dir.mkdir(parents=True, exist_ok=True)
        
        # PDF download directory
        self.pdf_dir = self.settings.data_dir / self.sub_folder / "pdfs"
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize markdown cleaner for RAG optimization
        self.markdown_cleaner = MarkdownCleaner()

    async def scrape_page(self, crawler: AsyncWebCrawler, url: str) -> Dict[str, Any]:
        """Scrape a single page with Crawl4AI.

        Args:
            crawler: The web crawler instance
            url: URL to scrape

        Returns:
            Dictionary containing page content and metadata
        """
        try:
            logger.info(f"Scraping with Crawl4AI: {url}")
            
            # Configure crawler for optimal GenAI extraction
            run_config = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,  # Always get fresh content
                wait_for_images=False,
                screenshot=False,
                # Crawl4AI will extract clean markdown optimized for LLMs
            )

            result = await crawler.arun(url=url, config=run_config)

            if result.success:
                # Extract links for crawling - handle both dict and string formats
                internal_links = []
                if hasattr(result, 'links') and result.links:
                    raw_links = result.links.get("internal", [])
                    # Convert to list of strings if they're dicts
                    for link in raw_links:
                        if isinstance(link, dict):
                            # Extract URL from dict (common format: {'url': 'http://...'} or {'href': '...'})
                            url_str = link.get('url') or link.get('href') or link.get('link', '')
                            if url_str:
                                internal_links.append(url_str)
                        elif isinstance(link, str):
                            internal_links.append(link)
                
                # Crawl4AI provides optimized markdown for GenAI
                markdown = result.markdown if hasattr(result, 'markdown') else ""
                
                # Extract metadata
                metadata = result.metadata if hasattr(result, 'metadata') else {}
                
                # Extract PDF links
                pdf_links = self._extract_pdf_links(result.html if hasattr(result, 'html') else "")
                
                return {
                    "url": url,
                    "title": metadata.get("title", ""),
                    "description": metadata.get("description", ""),
                    "keywords": metadata.get("keywords", ""),
                    "markdown": markdown,  # Clean markdown optimized for LLMs
                    "links": internal_links,
                    "pdf_links": pdf_links,
                    "metadata": metadata,
                    "success": True,
                }
            else:
                logger.error(f"Failed to scrape {url}: {result.error_message}")
                return {"url": url, "success": False, "error": result.error_message}

        except Exception as e:
            logger.error(f"Error scraping {url}: {str(e)}")
            return {"url": url, "success": False, "error": str(e)}

    def _extract_pdf_links(self, html: str) -> List[str]:
        """Extract PDF links from HTML.
        
        Args:
            html: HTML content
            
        Returns:
            List of PDF URLs
        """
        from bs4 import BeautifulSoup
        
        pdf_links = []
        soup = BeautifulSoup(html, 'html.parser')
        
        for link in soup.find_all('a', href=True):
            href = link['href']
            if href.lower().endswith('.pdf'):
                absolute_url = urljoin(self.base_url, href)
                pdf_links.append(absolute_url)
        
        return pdf_links

    async def download_pdf(self, url: str, session: Any = None) -> bool:
        """Download a PDF file.
        
        Args:
            url: URL of the PDF
            session: aiohttp session (optional)
            
        Returns:
            True if successful
        """
        try:
            import aiohttp
            
            # Create safe filename
            filename = url.split("/")[-1]
            filename = re.sub(r'[^\w\-\.]', '_', filename)
            output_path = self.pdf_dir / filename
            
            # Skip if already downloaded
            if output_path.exists():
                logger.info(f"PDF already exists: {filename}")
                return True
            
            logger.info(f"Downloading PDF: {filename}")
            
            if session is None:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=60) as response:
                        if response.status == 200:
                            content = await response.read()
                            with open(output_path, 'wb') as f:
                                f.write(content)
                            logger.info(f"✓ Downloaded: {filename} ({len(content)} bytes)")
                            return True
            else:
                async with session.get(url, timeout=60) as response:
                    if response.status == 200:
                        content = await response.read()
                        with open(output_path, 'wb') as f:
                            f.write(content)
                        logger.info(f"✓ Downloaded: {filename} ({len(content)} bytes)")
                        return True
            
            logger.error(f"Failed to download PDF: {url}")
            return False
            
        except Exception as e:
            logger.error(f"Error downloading PDF {url}: {str(e)}")
            return False

    async def discover_pages(
        self, 
        crawler: AsyncWebCrawler, 
        max_depth: int = 2
    ) -> List[str]:
        """Discover all pages in SentiWiki using BFS.

        Args:
            crawler: The web crawler instance
            max_depth: Maximum depth to crawl

        Returns:
            List of discovered URLs
        """
        logger.info(f"Discovering pages from {self.base_url} (max depth: {max_depth})")

        visited: Set[str] = set()
        to_visit: List[tuple[str, int]] = [(self.base_url, 0)]
        all_pages: List[str] = []

        while to_visit:
            url, depth = to_visit.pop(0)
            
            if url in visited or depth > max_depth:
                continue
                
            visited.add(url)
            
            # Skip non-wiki pages
            if not self._is_valid_wiki_url(url):
                continue
            
            result = await self.scrape_page(crawler, url)
            
            if result["success"]:
                all_pages.append(url)
                
                # Add new links if we haven't reached max depth
                if depth < max_depth:
                    for link in result.get("links", []):
                        if link not in visited and self._is_valid_wiki_url(link):
                            to_visit.append((link, depth + 1))
            
            # Rate limiting
            await asyncio.sleep(1)
            
        logger.info(f"Discovered {len(all_pages)} unique pages")
        return all_pages

    def _is_valid_wiki_url(self, url: str) -> bool:
        """Check if URL is a valid wiki page.
        
        Args:
            url: URL to check
            
        Returns:
            True if valid wiki URL
        """
        parsed = urlparse(url)
        
        # Must be from sentiwiki domain
        if parsed.netloc != "sentiwiki.copernicus.eu":
            return False
        
        # Must be under /web/
        if not parsed.path.startswith("/web/"):
            return False
        
        # Skip certain patterns
        skip_patterns = [
            '/download/',
            '/search',
            '.pdf',
            '.zip',
            '.xml',
            '#',
            'javascript:',
        ]
        
        for pattern in skip_patterns:
            if pattern in url:
                return False
        
        return True

    async def scrape_all(
        self, 
        max_depth: int = 2, 
        max_pages: int = 500,
        download_pdfs: bool = True
    ) -> None:
        """Scrape all SentiWiki pages with Crawl4AI.
        
        Args:
            max_depth: Maximum depth for discovery
            max_pages: Maximum number of pages to scrape
            download_pdfs: Whether to download PDFs
        """
        browser_config = BrowserConfig(
            headless=True,
            verbose=False,
        )

        async with AsyncWebCrawler(config=browser_config) as crawler:
            # Discover all pages
            urls = await self.discover_pages(crawler, max_depth=max_depth)
            
            # Limit number of pages
            if len(urls) > max_pages:
                logger.warning(f"Found {len(urls)} pages, limiting to {max_pages}")
                urls = urls[:max_pages]

            # Scrape each page
            logger.info(f"Scraping {len(urls)} pages with Crawl4AI")
            all_results = []
            all_pdf_links = []

            for url in tqdm(urls, desc="Scraping pages"):
                result = await self.scrape_page(crawler, url)
                all_results.append(result)
                
                # Collect PDF links
                if result.get("success") and result.get("pdf_links"):
                    all_pdf_links.extend(result["pdf_links"])

                # Save individual page
                if result["success"]:
                    # Create safe filename
                    page_id = re.sub(r'[^\w\-]', '_', url.split("/")[-1] or "index")
                    
                    # Save JSON (complete data with metadata)
                    json_path = self.output_dir / f"{page_id}.json"
                    with open(json_path, "w", encoding="utf-8") as f:
                        json.dump(result, f, indent=2, ensure_ascii=False)
                    
                    # Save RAG-optimized Markdown (cleaned and enhanced)
                    markdown_path = self.markdown_dir / f"{page_id}.md"
                    
                    # Create RAG-optimized markdown with the cleaner
                    rag_markdown = self.markdown_cleaner.create_rag_optimized_markdown(
                        markdown=result.get('markdown', ''),
                        metadata={
                            'title': result.get('title', ''),
                            'url': result.get('url', ''),
                            'description': result.get('description', ''),
                            'keywords': result.get('keywords', ''),
                        },
                        include_toc=True  # Include table of contents for better navigation
                    )
                    
                    with open(markdown_path, "w", encoding="utf-8") as f:
                        f.write(rag_markdown)

                # Rate limiting
                await asyncio.sleep(1)

            # Download PDFs if requested
            if download_pdfs and all_pdf_links:
                await self._download_all_pdfs(list(set(all_pdf_links)))

            # Save summary
            summary = {
                "total_pages": len(all_results),
                "successful": sum(1 for r in all_results if r["success"]),
                "failed": sum(1 for r in all_results if not r["success"]),
                "urls": [r["url"] for r in all_results if r["success"]],
                "failed_urls": [r["url"] for r in all_results if not r["success"]],
                "total_pdfs_found": len(all_pdf_links),
                "unique_pdfs": len(set(all_pdf_links)),
                "pdf_links": list(set(all_pdf_links)),
                "output_directories": {
                    "json": str(self.output_dir),
                    "markdown": str(self.markdown_dir),
                    "pdfs": str(self.pdf_dir) if download_pdfs else None,
                }
            }

            summary_path = self.output_dir / "scraping_summary.json"
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2)

            logger.info(
                f"Scraping complete: {summary['successful']}/{summary['total_pages']} pages successful"
            )
            logger.info(f"JSON files saved to: {self.output_dir}")
            logger.info(f"Markdown files saved to: {self.markdown_dir}")
            
            if summary['failed'] > 0:
                logger.warning(f"Failed to scrape {summary['failed']} pages")
            
            if download_pdfs:
                logger.info(f"Found {summary['unique_pdfs']} unique PDF files")
                logger.info(f"PDFs saved to: {self.pdf_dir}")

    async def _download_all_pdfs(self, pdf_urls: List[str]) -> None:
        """Download all PDF files.
        
        Args:
            pdf_urls: List of PDF URLs
        """
        import aiohttp
        
        logger.info(f"Downloading {len(pdf_urls)} PDF files...")
        
        async with aiohttp.ClientSession() as session:
            tasks = [self.download_pdf(url, session) for url in pdf_urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            successful = sum(1 for r in results if r is True)
            logger.info(f"Downloaded {successful}/{len(pdf_urls)} PDFs successfully")


async def main() -> None:
    """Main entry point."""
    # FASE 1: Scraping básico de SentiWiki (ACTUAL - SUFICIENTE PARA MVP)
    scraper = SentiWikiCrawl4AIScraper()
    await scraper.scrape_all(
        max_depth=2,              # Profundidad actual
        max_pages=200,            # Límite actual
        download_pdfs=False        # Descargar PDFs si los encuentra
    )
    
    # FASE 2 (FUTURO): Expansión con deep crawling
    # Ver docs/FUTURE_EXPANSION_ROADMAP.md para implementación
    # Usar deep_crawl_strategy nativo de Crawl4AI cuando sea necesario


if __name__ == "__main__":
    asyncio.run(main())

