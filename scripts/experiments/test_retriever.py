#!/usr/bin/env python3
"""
Test script for the RAG retriever.

Allows testing retrieval directly from terminal without starting the API.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import click
from loguru import logger

from src.retrieval.retriever import AdvancedRetriever
from src.utils.config import get_settings


def print_result(result: dict, index: int):
    """Pretty print a retrieval result."""
    print(f"\n{'='*80}")
    print(f"Result #{index + 1} (Score: {result['score']:.4f})")
    print(f"{'='*80}")
    print(f"📄 Source: {result.get('title', 'N/A')}")
    print(f"🔗 URL: {result.get('url', 'N/A')}")
    print(f"📍 Heading: {result.get('heading_path', 'N/A')}")
    print(f"📊 Quality: {result.get('quality', {}).get('overall', 'N/A')}")
    print(f"\n📝 Content:")
    print("-" * 80)
    # Show first 500 chars of content
    content = result.get('text', '')
    if len(content) > 500:
        print(content[:500] + "...")
    else:
        print(content)
    print("-" * 80)


@click.command()
@click.option(
    '--query', '-q',
    type=str,
    help='Query to search for'
)
@click.option(
    '--top-k', '-k',
    type=int,
    default=5,
    help='Number of results to retrieve (default: 5)'
)
@click.option(
    '--interactive', '-i',
    is_flag=True,
    help='Interactive mode: keep asking for queries'
)
@click.option(
    '--collection',
    type=str,
    default=None,
    help='Qdrant collection name (default: from settings)'
)
@click.option(
    '--no-hybrid',
    is_flag=True,
    default=False,
    help='Disable hybrid search (use only semantic search)'
)
@click.option(
    '--no-reranking',
    is_flag=True,
    default=False,
    help='Disable reranking (use only initial retrieval scores)'
)
@click.option(
    '--no-filtering',
    is_flag=True,
    default=False,
    help='Disable metadata filtering'
)
def main(query: str, top_k: int, interactive: bool, collection: str, no_hybrid: bool, no_reranking: bool, no_filtering: bool):
    """Test the RAG retriever from command line."""
    
    logger.info("Initializing retriever...")
    
    # Override collection if provided
    settings = get_settings()
    if collection:
        settings.qdrant.collection_name = collection
    
    try:
        retriever = AdvancedRetriever()
        logger.success("✓ Retriever initialized")
        logger.info(f"Collection: {settings.qdrant.collection_name}")
        logger.info(f"Embedding provider: {settings.embeddings.provider}")
        logger.info(f"Embedding model: {settings.embeddings.model}")
        logger.info(f"Hybrid search: {'DISABLED' if no_hybrid else 'ENABLED (from config)'}")
        logger.info(f"Reranking: {'DISABLED' if no_reranking else 'ENABLED (from config)'}")
        logger.info(f"Metadata filtering: {'DISABLED' if no_filtering else 'ENABLED (from config)'}")
        
        # Get collection info
        try:
            info = retriever.qdrant.get_collection_info()
            logger.info(f"Collection info: {info}")
        except Exception as e:
            logger.warning(f"Could not get collection info: {e}")
        
        if interactive:
            # Interactive mode
            print("\n" + "="*80)
            print("🔍 Interactive RAG Retriever")
            print("="*80)
            print("Type your queries (or 'quit'/'exit' to stop)\n")
            
            while True:
                try:
                    user_query = input("Query: ").strip()
                    
                    if not user_query or user_query.lower() in ['quit', 'exit', 'q']:
                        print("\n👋 Goodbye!")
                        break
                    
                    logger.info(f"Searching for: {user_query}")
                    results = retriever.retrieve(
                        query=user_query,
                        top_k=top_k,
                        use_hybrid=False if no_hybrid else None,
                        use_reranking=False if no_reranking else None,
                        auto_extract_filters=False if no_filtering else None,
                    )
                    
                    if not results:
                        print("\n❌ No results found")
                        continue
                    
                    print(f"\n✅ Found {len(results)} results:")
                    for i, result in enumerate(results):
                        print_result(result, i)
                    
                    print("\n" + "="*80 + "\n")
                    
                except KeyboardInterrupt:
                    print("\n\n👋 Goodbye!")
                    break
                except Exception as e:
                    logger.error(f"Error: {e}")
                    print(f"\n❌ Error: {e}\n")
        
        elif query:
            # Single query mode
            logger.info(f"Searching for: {query}")
            results = retriever.retrieve(
                query=query,
                top_k=top_k,
                use_hybrid=False if no_hybrid else None,
                use_reranking=False if no_reranking else None,
                auto_extract_filters=False if no_filtering else None,
            )
            
            if not results:
                print("\n❌ No results found")
                return
            
            print(f"\n✅ Found {len(results)} results for: '{query}'")
            for i, result in enumerate(results):
                print_result(result, i)
        
        else:
            # No query provided
            click.echo("Error: Please provide a query with --query/-q or use --interactive/-i mode")
            click.echo("\nExamples:")
            click.echo("  python scripts/test_retriever.py -q 'What are Sentinel-1 applications?'")
            click.echo("  python scripts/test_retriever.py -i")
            click.echo("  python scripts/test_retriever.py -q 'SAR imaging' -k 10")
            click.echo("  python scripts/test_retriever.py -q 'SAR imaging' --no-hybrid --no-reranking")
            sys.exit(1)
    
    except Exception as e:
        logger.error(f"Failed to initialize retriever: {e}")
        logger.exception(e)
        sys.exit(1)


if __name__ == "__main__":
    main()

