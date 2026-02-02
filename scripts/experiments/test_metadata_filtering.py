#!/usr/bin/env python3
"""
Script para probar el sistema de filtrado por metadatos.
"""

import sys
from pathlib import Path
from typing import List, Dict

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.retrieval.retriever import AdvancedRetriever
from src.utils.metadata_filter import MetadataFilter, SmartMetadataExtractor
from loguru import logger


def test_query_analysis():
    """Prueba el análisis de consultas."""
    print("🔍 Testing Query Analysis")
    print("=" * 50)
    
    filter_system = MetadataFilter()
    
    test_queries = [
        "¿Qué es ECSS-E-ST-10C?",
        "¿Cuáles son los requisitos obligatorios (shall) para verificación?",
        "¿Qué procedimientos se recomiendan (should) para testing?",
        "¿Cómo implementar la gestión de configuración según ECSS-M-ST-40C?",
        "¿Cuál es el procedimiento paso a paso para thermal testing?",
        "ECSS-Q-ST-80C software quality requirements",
    ]
    
    for query in test_queries:
        print(f"\nQuery: {query}")
        analysis = filter_system.analyze_query(query)
        print(f"  Type: {analysis['query_type']}")
        print(f"  Requirement Level: {analysis['requirement_level']}")
        print(f"  ECSS Standards: {analysis['ecss_standards']}")
        print(f"  Filters: {analysis['filters']}")
        
        # Test Qdrant filter generation
        qdrant_filter = filter_system.create_qdrant_filter(analysis['filters'])
        if qdrant_filter:
            print(f"  Qdrant Filter: {qdrant_filter}")


def test_retrieval_with_filtering():
    """Prueba el retrieval con filtrado de metadatos."""
    print("\n\n🚀 Testing Retrieval with Metadata Filtering")
    print("=" * 60)
    
    try:
        retriever = AdvancedRetriever()
        
        test_queries = [
            {
                "query": "¿Cuáles son los requisitos obligatorios para verificación?",
                "description": "Should find chunks with 'shall' requirements"
            },
            {
                "query": "¿Qué procedimientos se recomiendan para testing?", 
                "description": "Should find chunks with 'should' recommendations"
            },
            {
                "query": "¿Cómo implementar gestión de configuración paso a paso?",
                "description": "Should find chunks with lists/procedures"
            }
        ]
        
        for test in test_queries:
            print(f"\n📋 Test: {test['description']}")
            print(f"Query: {test['query']}")
            
            # Retrieve with smart filtering
            results = retriever.retrieve(
                query=test['query'],
                top_k=3,
                use_reranking=False,  # Disable for cleaner testing
                use_hybrid=True,
                auto_extract_filters=True
            )
            
            print(f"Results found: {len(results)}")
            
            for i, doc in enumerate(results, 1):
                metadata = doc.get('metadata', {})
                score = doc.get('score', 0)
                boost_factor = doc.get('boost_factor', 1.0)
                boost_reasons = doc.get('boost_reasons', [])
                
                print(f"\n  {i}. Score: {score:.4f} (boost: {boost_factor:.2f}x)")
                print(f"     Title: {doc.get('title', 'Unknown')[:60]}...")
                print(f"     Has shall: {metadata.get('has_shall', False)}")
                print(f"     Has should: {metadata.get('has_should', False)}")
                print(f"     Requirement type: {metadata.get('requirement_type', 'Unknown')}")
                print(f"     Contains list: {metadata.get('contains_list', False)}")
                print(f"     Word count: {metadata.get('word_count', 0)}")
                
                if boost_reasons:
                    print(f"     Boost reasons: {', '.join(boost_reasons)}")
                
                # Show text preview
                text = doc.get('text', '')[:150]
                print(f"     Text: {text}...")
            
            print("-" * 40)
    
    except Exception as e:
        logger.error(f"Error in retrieval test: {e}")
        import traceback
        traceback.print_exc()


def test_metadata_extraction():
    """Prueba la extracción de metadatos inteligente."""
    print("\n\n🧠 Testing Smart Metadata Extraction")
    print("=" * 50)
    
    extractor = SmartMetadataExtractor()
    
    test_queries = [
        "ECSS-E-ST-10C verification requirements",
        "¿Cómo implementar procedimientos de testing?",
        "¿Qué define ECSS-Q-ST-80C sobre calidad?",
        "Mandatory requirements for software development"
    ]
    
    for query in test_queries:
        print(f"\nQuery: {query}")
        
        # Test simple filters
        simple_filters = extractor.extract_filters(query)
        print(f"  Simple filters: {simple_filters}")
        
        # Test Qdrant filters
        qdrant_filters = extractor.get_qdrant_filters(query)
        print(f"  Qdrant filters: {qdrant_filters}")


def main():
    """Ejecuta todas las pruebas."""
    logger.info("Starting metadata filtering tests...")
    
    try:
        test_query_analysis()
        test_metadata_extraction()
        test_retrieval_with_filtering()
        
        print("\n\n✅ All tests completed!")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
