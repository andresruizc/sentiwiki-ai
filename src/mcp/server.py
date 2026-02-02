"""MCP server using FastMCP to expose RAG functionality."""

import os
from typing import Optional

from fastmcp import FastMCP
from loguru import logger

from src.api.main import ServiceContainer, services
from src.retrieval.retriever import AdvancedRetriever
from src.utils.prompts import build_rag_system_prompt, extract_standards_from_docs
from src.utils.config import get_settings
from src.utils.logger import setup_logger


# Reconfigure logger for MCP mode (no stdout, no colors)
# This must be done before any other imports that use the logger
setup_logger()

# Initialize MCP server
mcp = FastMCP("SentiWiki RAG")

# Get LLM service (lazy initialization)
def get_llm_service():
    """Get LLM service from container."""
    return services.get_llm()


@mcp.tool()
def query_sentiwiki(
    question: str,
    collection: Optional[str] = None,
    use_reranking: Optional[bool] = None,
    use_hybrid: Optional[bool] = None,
) -> str:
    """Query SentiWiki (Copernicus Sentinel Missions) documentation.
    
    This tool uses RAG (Retrieval-Augmented Generation) to answer questions about Sentinel missions.
    It retrieves relevant documents from the knowledge base and generates accurate answers
    based on the retrieved context.
    
    Args:
        question: The question to ask about Sentinel missions or SentiWiki documentation
        collection: Optional collection name to query from (uses default if not provided)
        use_reranking: Optional flag to enable/disable reranking (uses config default if not provided)
        use_hybrid: Optional flag to enable/disable hybrid search (uses config default if not provided)
    
    Returns:
        A comprehensive answer based on the SentiWiki documentation, including:
        - The answer to the question
        - Source documents used
        - Metadata about the retrieval process
    """
    try:
        # Get retriever for the specified collection (or default)
        retriever: AdvancedRetriever = services.get_retriever(collection_name=collection)
        
        # Get LLM service
        llm_service = get_llm_service()
        
        # Step 1: Retrieve relevant documents
        logger.info(f"Retrieving documents for question: {question[:100]}...")
        docs = retriever.retrieve(
            query=question,
            top_k=None,  # Uses default from settings.yaml
            filters=None,
            use_reranking=use_reranking,
            use_hybrid=use_hybrid,
        )
        
        if not docs:
            return "No relevant documents found in the SentiWiki database for this question."
        
        # Step 2: Format context from retrieved documents
        context_parts = []
        for i, doc in enumerate(docs, 1):
            text = doc.get("contextualized_text") or doc.get("text", "")
            score = doc.get("score", 0.0)
            title = doc.get("title", "Unknown")
            heading = doc.get("heading", "")
            
            context_parts.append(
                f"[Document {i}] {title}"
                + (f" - {heading}" if heading else "")
                + f" (Relevance: {score:.4f})\n"
                + f"Content:\n{text}\n"
            )
        context = "\n---\n\n".join(context_parts)
        
        # Step 3: Extract Sentinel missions from documents
        missions_in_context = extract_standards_from_docs(docs)
        
        # Step 4: Build system prompt
        system_prompt = build_rag_system_prompt(
            context=context,
            standards_in_context=missions_in_context,
        )
        
        # Step 5: Generate answer using LLM
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ]
        
        logger.info("Generating answer with LLM...")
        answer = llm_service.invoke(messages)
        
        # Step 6: Format response with sources
        sources_info = []
        for i, doc in enumerate(docs[:5], 1):  # Show top 5 sources
            title = doc.get("title", "Unknown")
            url = doc.get("url", "")
            heading = doc.get("heading", "")
            score = doc.get("score", 0.0)
            
            source_str = f"{i}. {title}"
            if heading:
                source_str += f" ({heading})"
            if url:
                source_str += f" - {url}"
            source_str += f" [Relevance: {score:.3f}]"
            
            sources_info.append(source_str)
        
        # Format final response
        response = f"{answer}\n\n"
        response += "---\n"
        response += f"Sources ({len(docs)} documents retrieved):\n"
        response += "\n".join(sources_info)
        
        if len(docs) > 5:
            response += f"\n... and {len(docs) - 5} more documents"
        
        return response
        
    except Exception as e:
        logger.exception(f"Error in query_sentiwiki: {str(e)}")
        return f"Error querying SentiWiki documentation: {str(e)}"


if __name__ == "__main__":
    # Run the MCP server
    # Use mcp.run() for normal operation (stdio)
    # For inspector/debugger dashboard, use: uv run dev src/mcp/server.py
    mcp.run()

