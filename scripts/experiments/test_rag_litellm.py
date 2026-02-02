#!/usr/bin/env python3
"""Test RAG pipeline with LiteLLM and Anthropic."""

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import click
from loguru import logger

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.llm.llm_factory import get_llm
from src.retrieval.retriever import AdvancedRetriever
from src.utils.config import Settings, get_settings
from src.utils.logger import setup_logger


def format_context(docs: List[Dict[str, Any]]) -> str:
    """Format retrieved documents as context for the LLM."""
    context_parts = []
    for i, doc in enumerate(docs, 1):
        title = doc.get("title", "Unknown")
        url = doc.get("url", "")
        text = doc.get("contextualized_text") or doc.get("text", "")
        score = doc.get("score", 0.0)
        
        context_parts.append(
            f"[Document {i}] {title}\n"
            f"Source: {url}\n"
            f"Relevance Score: {score:.4f}\n"
            f"Content:\n{text}\n"
        )
    
    return "\n---\n\n".join(context_parts)


def create_rag_prompt(query: str, context: str, docs: List[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    """Create a RAG prompt with query and context.
    
    Args:
        query: User question
        context: Formatted context from retrieved documents
        docs: List of retrieved documents (for detecting multiple standards)
    """
    # Import here to avoid circular dependencies
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.utils.prompts import build_rag_system_prompt, extract_standards_from_docs
    
    # Extract ECSS standards from documents
    standards_in_context = extract_standards_from_docs(docs) if docs else None
    
    # Build system prompt using centralized function
    system_prompt = build_rag_system_prompt(
        context=context,
        standards_in_context=standards_in_context,
    )
    
    user_prompt = f"""Context from documentation:

{context}

Question: {query}

Please provide a comprehensive answer based on the context above."""
    
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def summarize_documents(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Reduce document payload for observability."""
    summary = []
    for doc in docs:
        metadata = doc.get("metadata", {})
        summary.append(
            {
                "id": doc.get("id"),
                "score": doc.get("score"),
                "title": doc.get("title"),
                "url": doc.get("url"),
                "mission": metadata.get("mission"),
                "document_type": metadata.get("document_type"),
                "heading_path": doc.get("heading") or metadata.get("heading_path"),
                "char_count": len(doc.get("text", "")),
                "contextualized_char_count": len(doc.get("contextualized_text", "")),
            }
        )
    return summary


def calculate_retrieval_metrics(docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate detailed retrieval metrics."""
    if not docs:
        return {
            "count": 0,
            "avg_score": 0.0,
            "min_score": 0.0,
            "max_score": 0.0,
            "score_std": 0.0,
        }
    
    scores = [doc.get("score", 0.0) for doc in docs]
    missions = [doc.get("metadata", {}).get("mission") for doc in docs if doc.get("metadata", {}).get("mission")]
    missions_count = len(set(missions))
    
    import statistics
    return {
        "count": len(docs),
        "avg_score": statistics.mean(scores) if scores else 0.0,
        "min_score": min(scores) if scores else 0.0,
        "max_score": max(scores) if scores else 0.0,
        "score_std": statistics.stdev(scores) if len(scores) > 1 else 0.0,
        "unique_missions": missions_count,
        "missions": list(set(missions))[:5],  # Top 5 unique missions
        "total_chars": sum(len(doc.get("text", "")) for doc in docs),
        "avg_chars_per_doc": sum(len(doc.get("text", "")) for doc in docs) / len(docs) if docs else 0,
    }


def extract_llm_metrics(llm_response: Any, llm_wrapper) -> Dict[str, Any]:
    """Extract detailed LLM metrics from response."""
    metrics = {
        "model": getattr(llm_wrapper, "model", "unknown"),
        "temperature": getattr(llm_wrapper, "temperature", None),
        "max_tokens": getattr(llm_wrapper, "max_tokens", None),
    }
    
    # Extract token usage
    if hasattr(llm_response, "usage"):
        usage = llm_response.usage
        metrics["prompt_tokens"] = getattr(usage, "prompt_tokens", None)
        metrics["completion_tokens"] = getattr(usage, "completion_tokens", None)
        metrics["total_tokens"] = getattr(usage, "total_tokens", None)
    elif isinstance(llm_response, dict) and "usage" in llm_response:
        usage = llm_response["usage"]
        metrics["prompt_tokens"] = usage.get("prompt_tokens")
        metrics["completion_tokens"] = usage.get("completion_tokens")
        metrics["total_tokens"] = usage.get("total_tokens")
    
    # Calculate cost
    try:
        import litellm
        cost = litellm.completion_cost(completion_response=llm_response)
        if cost is not None:
            metrics["cost"] = cost
            metrics["cost_per_1k_tokens"] = (cost / metrics["total_tokens"] * 1000) if metrics.get("total_tokens") else None
    except Exception:
        pass
    
    return metrics


def run_rag_query(
    query: str,
    top_k: int,
    retriever: AdvancedRetriever,
    llm,
    mode: str,
    use_hybrid: Optional[bool] = None,
    use_reranking: Optional[bool] = None,
    use_filtering: Optional[bool] = None,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Execute retrieval + generation."""
    docs: List[Dict[str, Any]] = []
    
    try:
        # === RETRIEVAL PHASE ===
        retrieval_start = time.perf_counter()
        docs = retriever.retrieve(
            query=query,
            top_k=top_k,
            use_hybrid=use_hybrid,
            use_reranking=use_reranking,
            auto_extract_filters=use_filtering,  # Use parameter (None = config default)
        )
        retrieval_ms = (time.perf_counter() - retrieval_start) * 1000

        # === CONTEXT PREPARATION ===
        context_prep_start = time.perf_counter()
        context = format_context(docs)
        context_length = len(context)
        messages = create_rag_prompt(query, context, docs=docs)
        context_prep_ms = (time.perf_counter() - context_prep_start) * 1000

        # === LLM GENERATION PHASE ===
        llm_start = time.perf_counter()
        response = llm.invoke(messages)
        llm_ms = (time.perf_counter() - llm_start) * 1000

        return response, docs

    except Exception as exc:
        raise


@click.command()
@click.option(
    "-q",
    "--query",
    type=str,
    required=False,
    help="Query to ask (if not provided, will use interactive mode)",
)
@click.option(
    "-k",
    "--top-k",
    type=int,
    default=5,
    help="Number of documents to retrieve",
)
@click.option(
    "--model",
    type=str,
    default=None,
    help="Model name (e.g., 'claude-3-5-sonnet-20241022')",
)
@click.option(
    "--api-key",
    type=str,
    default=None,
    help="Anthropic API key (or set ANTHROPIC_API_KEY env var)",
)
@click.option(
    "-i",
    "--interactive",
    is_flag=True,
    help="Run in interactive mode",
)
@click.option(
    "--collection",
    type=str,
    default=None,
    help="Qdrant collection name (defaults to config)",
)
@click.option(
    "--no-hybrid",
    is_flag=True,
    default=False,
    help="Disable hybrid search (use only semantic search)",
)
@click.option(
    "--no-reranking",
    is_flag=True,
    default=False,
    help="Disable reranking (use only initial retrieval scores)",
)
@click.option(
    "--no-filtering",
    is_flag=True,
    default=False,
    help="Disable metadata filtering",
)
def main(
    query: str | None,
    top_k: int,
    model: str | None,
    api_key: str | None,
    interactive: bool,
    collection: str | None,
    no_hybrid: bool,
    no_reranking: bool,
    no_filtering: bool,
):
    """Test RAG pipeline with LiteLLM and Anthropic."""
    setup_logger()
    settings = get_settings()
    
    # Get API key from parameter, env var, or settings
    if not api_key:
        api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        # Try to get from settings (which loads from .env)
        api_key = getattr(settings, "anthropic_api_key", None)
    
    if not api_key:
        logger.error(
            "ANTHROPIC_API_KEY not found. Please:\n"
            "  1. Set it in .env file: ANTHROPIC_API_KEY=your-key\n"
            "  2. Or export it: export ANTHROPIC_API_KEY=your-key\n"
            "  3. Or use --api-key flag: --api-key your-key"
        )
        sys.exit(1)
    
    logger.info("Initializing RAG components...")

    # Initialize retriever
    retriever = AdvancedRetriever(collection_name=collection)
    logger.success("✓ Retriever initialized")
    logger.info(f"Hybrid search: {'DISABLED' if no_hybrid else 'ENABLED (from config)'}")
    logger.info(f"Reranking: {'DISABLED' if no_reranking else 'ENABLED (from config)'}")
    
    # Initialize LLM with LiteLLM
    llm = get_llm(
        provider="anthropic",
        model=model,
        api_key=api_key,
        streaming=False,  # Set to True for streaming responses
    )
    logger.success(f"✓ LLM initialized: {llm.model}")
    
    if interactive:
        logger.info("Running in interactive mode. Type 'quit' or 'exit' to stop.")
        while True:
            try:
                user_query = input("\n🔍 Your question: ").strip()
                if not user_query or user_query.lower() in ["quit", "exit", "q"]:
                    logger.info("Goodbye!")
                    break
                
                logger.info(f"Running query with top_k={top_k}")
                response, docs = run_rag_query(
                    query=user_query,
                    top_k=top_k,
                    retriever=retriever,
                    llm=llm,
                    mode="interactive",
                    use_hybrid=False if no_hybrid else None,
                    use_reranking=False if no_reranking else None,
                    use_filtering=False if no_filtering else None,
                )
                logger.success("✓ Response generated")
                
                # Display results
                print("\n" + "=" * 80)
                print(f"📝 Answer:")
                print("=" * 80)
                print(response)
                print("=" * 80)
                
                # Show sources
                print("\n📚 Sources:")
                for i, doc in enumerate(docs[:3], 1):  # Show top 3
                    print(f"  {i}. {doc.get('title', 'Unknown')} (score: {doc.get('score', 0):.4f})")
                    print(f"     {doc.get('url', '')}")
                
            except KeyboardInterrupt:
                logger.info("\nGoodbye!")
                break
            except Exception as e:
                logger.error(f"Error: {e}")
                import traceback
                traceback.print_exc()
    
    else:
        if not query:
            logger.error("Query is required in non-interactive mode. Use -q/--query or -i/--interactive")
            sys.exit(1)
        
        logger.info(f"Query: {query}")
        
        logger.info(f"Running query with top_k={top_k}")
        response, docs = run_rag_query(
            query=query,
            top_k=top_k,
            retriever=retriever,
            llm=llm,
            mode="cli",
            use_hybrid=False if no_hybrid else None,
            use_reranking=False if no_reranking else None,
            use_filtering=False if no_filtering else None,
        )
        logger.success("✓ Response generated")
        
        # Display results
        print("\n" + "=" * 80)
        print(f"📝 Question: {query}")
        print("=" * 80)
        print(f"\n📝 Answer:")
        print(response)
        print("=" * 80)
        
        # Show sources
        print("\n📚 Top Sources:")
        for i, doc in enumerate(docs[:5], 1):
            print(f"  {i}. {doc.get('title', 'Unknown')} (score: {doc.get('score', 0):.4f})")
            print(f"     {doc.get('url', '')}")


if __name__ == "__main__":
    main()

