#!/usr/bin/env python3
"""
Script para comparar retrieval con y sin filtrado inteligente.
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.retrieval.retriever import AdvancedRetriever
from src.llm.llm_factory import get_llm
from src.utils.config import get_settings
from loguru import logger


def format_context(docs, title="Context"):
    """Format retrieved documents for display."""
    print(f"\n{'='*80}")
    print(f"📚 {title}")
    print(f"{'='*80}")
    
    for i, doc in enumerate(docs, 1):
        metadata = doc.get('metadata', {})
        score = doc.get('score', 0)
        boost_factor = doc.get('boost_factor', 1.0)
        boost_reasons = doc.get('boost_reasons', [])
        
        print(f"\n📄 Document {i}")
        print(f"   Title: {doc.get('title', 'Unknown')}")
        print(f"   Score: {score:.4f} (boost: {boost_factor:.2f}x)")
        print(f"   Has shall: {metadata.get('has_shall', False)}")
        print(f"   Has should: {metadata.get('has_should', False)}")
        print(f"   Requirement type: {metadata.get('requirement_type', 'Unknown')}")
        print(f"   Contains list: {metadata.get('contains_list', False)}")
        print(f"   Word count: {metadata.get('word_count', 0)}")
        
        if boost_reasons:
            print(f"   Boost reasons: {', '.join(boost_reasons)}")
        
        # Show text preview
        text = doc.get('contextualized_text') or doc.get('text', '')
        preview = text[:300] + "..." if len(text) > 300 else text
        print(f"   Text: {preview}")
        print("-" * 80)


def compare_retrieval(query: str, top_k: int = 5):
    """Compare retrieval with and without smart filtering."""
    
    print(f"\n🔍 QUERY: {query}")
    print(f"📊 Retrieving top {top_k} documents")
    
    # Initialize retriever
    retriever = AdvancedRetriever()
    
    # === WITHOUT FILTERING ===
    print(f"\n{'🚫 WITHOUT SMART FILTERING':=^80}")
    docs_without = retriever.retrieve(
        query=query,
        top_k=top_k,
        use_reranking=False,  # Disable for cleaner comparison
        use_hybrid=True,
        auto_extract_filters=False  # ← DISABLE filtering
    )
    
    format_context(docs_without, "Results WITHOUT Smart Filtering")
    
    # === WITH FILTERING ===
    print(f"\n{'✅ WITH SMART FILTERING':=^80}")
    docs_with = retriever.retrieve(
        query=query,
        top_k=top_k,
        use_reranking=False,  # Disable for cleaner comparison
        use_hybrid=True,
        auto_extract_filters=True  # ← ENABLE filtering
    )
    
    format_context(docs_with, "Results WITH Smart Filtering")
    
    # === COMPARISON ANALYSIS ===
    print(f"\n{'📊 COMPARISON ANALYSIS':=^80}")
    
    # Analyze metadata differences
    without_shall = sum(1 for doc in docs_without if doc.get('metadata', {}).get('has_shall', False))
    with_shall = sum(1 for doc in docs_with if doc.get('metadata', {}).get('has_shall', False))
    
    without_req = sum(1 for doc in docs_without if doc.get('metadata', {}).get('requirement_type') == 'REQUIREMENT')
    with_req = sum(1 for doc in docs_with if doc.get('metadata', {}).get('requirement_type') == 'REQUIREMENT')
    
    without_avg_score = sum(doc.get('score', 0) for doc in docs_without) / len(docs_without) if docs_without else 0
    with_avg_score = sum(doc.get('score', 0) for doc in docs_with) / len(docs_with) if docs_with else 0
    
    print(f"📈 Chunks with 'shall' (mandatory):")
    print(f"   Without filtering: {without_shall}/{len(docs_without)} ({without_shall/len(docs_without)*100:.1f}%)")
    print(f"   With filtering: {with_shall}/{len(docs_with)} ({with_shall/len(docs_with)*100:.1f}%)")
    print(f"   Improvement: {((with_shall/len(docs_with)) - (without_shall/len(docs_without)))*100:+.1f} percentage points")
    
    print(f"\n📋 Chunks with REQUIREMENT type:")
    print(f"   Without filtering: {without_req}/{len(docs_without)} ({without_req/len(docs_without)*100:.1f}%)")
    print(f"   With filtering: {with_req}/{len(docs_with)} ({with_req/len(docs_with)*100:.1f}%)")
    print(f"   Improvement: {((with_req/len(docs_with)) - (without_req/len(docs_without)))*100:+.1f} percentage points")
    
    print(f"\n⭐ Average relevance score:")
    print(f"   Without filtering: {without_avg_score:.4f}")
    print(f"   With filtering: {with_avg_score:.4f}")
    print(f"   Improvement: {(with_avg_score - without_avg_score):+.4f}")
    
    # Check for boost application
    boosted_docs = [doc for doc in docs_with if doc.get('boost_factor', 1.0) > 1.0]
    if boosted_docs:
        print(f"\n🚀 Boost applied to {len(boosted_docs)}/{len(docs_with)} documents")
        boost_reasons = set()
        for doc in boosted_docs:
            boost_reasons.update(doc.get('boost_reasons', []))
        print(f"   Boost reasons: {', '.join(boost_reasons)}")
    
    print("=" * 80)
    
    return docs_without, docs_with


def main():
    """Run the comparison."""
    
    # Test with a compliance-focused query that should benefit from filtering
    test_query = "¿Cuáles son los requisitos obligatorios (shall) para la verificación de software?"
    
    logger.info("Starting filtering comparison...")
    
    try:
        docs_without, docs_with = compare_retrieval(test_query, top_k=5)
        
        print(f"\n✅ Comparison completed!")
        print(f"📊 Retrieved {len(docs_without)} docs without filtering, {len(docs_with)} docs with filtering")
        
    except Exception as e:
        logger.error(f"Comparison failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
