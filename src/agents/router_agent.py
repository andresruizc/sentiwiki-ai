"""LangGraph agent for routing queries to RAG or direct LLM."""

import json
import os
import re
from typing import Any, Dict, List, Literal, Optional

# LangChain messages not needed - using dict format for LLM service
from langgraph.graph import END, StateGraph
from loguru import logger

from src.llm.llm_factory import get_llm
from src.models.agent import AgentState
from src.retrieval.retriever import AdvancedRetriever
from src.utils.config import get_settings
from src.utils.prompts import build_rag_system_prompt, extract_standards_from_docs
from src.utils.source_formatter import format_sources_for_response

try:
    from langsmith import traceable
    from langchain_core.runnables import RunnableConfig
except ImportError:
    # Fallback if langsmith not available
    def traceable(func):
        return func

    class RunnableConfig:
        pass


class RouterAgent:
    """LangGraph agent that routes queries to RAG or direct LLM."""
    
    def __init__(
        self,
        retriever: Optional[AdvancedRetriever] = None,
        router_llm: Optional[Any] = None,
        rag_llm: Optional[Any] = None,
        direct_llm: Optional[Any] = None,
        collection_name: Optional[str] = None,
    ):
        """Initialize the router agent.
        
        Args:
            retriever: AdvancedRetriever instance (optional, will create if not provided)
            router_llm: LLM wrapper for routing decisions (optional, will create from config)
            rag_llm: LLM wrapper for RAG path (optional, will create from config)
            direct_llm: LLM wrapper for direct path (optional, will create from config)
            collection_name: Collection name for retriever (optional)
        """
        self.settings = get_settings()
        
        # Initialize retriever
        self.retriever = retriever or AdvancedRetriever(collection_name=collection_name)
        
        # Initialize separate LLM services for each path
        # Router LLM (for routing decisions)
        router_config = self.settings.llm.router or self.settings.llm
        self.router_llm = router_llm or get_llm(
            provider=router_config.provider,
            model=router_config.model,
            temperature=router_config.temperature,
            max_tokens=router_config.max_tokens,
            streaming=getattr(router_config, "streaming", False),
            prompt_caching=getattr(router_config, "prompt_caching", False),
        )
        
        # RAG LLM (for technical queries with context)
        rag_config = self.settings.llm.rag or self.settings.llm
        self.rag_llm = rag_llm or get_llm(
            provider=rag_config.provider,
            model=rag_config.model,
            temperature=rag_config.temperature,
            max_tokens=rag_config.max_tokens,
            streaming=getattr(rag_config, "streaming", True),
            prompt_caching=getattr(rag_config, "prompt_caching", False),
        )
        
        # Direct LLM (for simple conversational queries)
        direct_config = self.settings.llm.direct or self.settings.llm
        self.direct_llm = direct_llm or get_llm(
            provider=direct_config.provider,
            model=direct_config.model,
            temperature=direct_config.temperature,
            max_tokens=direct_config.max_tokens,
            streaming=getattr(direct_config, "streaming", True),
            prompt_caching=getattr(direct_config, "prompt_caching", False),
        )
        
        # Keep llm_service for backward compatibility (defaults to RAG LLM)
        self.llm_service = self.rag_llm
        
        # Setup LangSmith if enabled
        self._setup_langsmith()
        
        # Build the graph
        self.graph = self._build_graph()
        
        logger.success(
            f"✅ RouterAgent initialized:\n"
            f"   🔀 Router LLM: {router_config.provider}/{router_config.model}\n"
            f"   📚 RAG LLM: {rag_config.provider}/{rag_config.model}\n"
            f"   💬 Direct LLM: {direct_config.provider}/{direct_config.model}"
        )
    
    def _setup_langsmith(self) -> None:
        """Setup LangSmith monitoring."""
        langsmith_config = self.settings.agent.langsmith
        
        if langsmith_config.enabled:
            # Set LangSmith API key from env or config
            # LangSmith accepts both LANGSMITH_API_KEY and LANGCHAIN_API_KEY
            api_key = (
                langsmith_config.api_key
                or os.getenv("LANGSMITH_API_KEY")
                or os.getenv("LANGCHAIN_API_KEY")
            )
            
            if api_key:
                # Set both env vars for compatibility
                os.environ["LANGSMITH_API_KEY"] = api_key
                os.environ["LANGCHAIN_API_KEY"] = api_key
                
                # Use project name from env if set, otherwise from config
                project_name = os.getenv("LANGSMITH_PROJECT") or os.getenv("LANGCHAIN_PROJECT") or langsmith_config.project_name
                os.environ["LANGSMITH_PROJECT"] = project_name
                os.environ["LANGCHAIN_PROJECT"] = project_name
                
                # Set tracing flag (respect env if already set, otherwise use config)
                tracing_enabled = (
                    os.getenv("LANGSMITH_TRACING", "").lower() == "true"
                    or os.getenv("LANGCHAIN_TRACING_V2", "").lower() == "true"
                    or langsmith_config.tracing
                )
                tracing_str = "true" if tracing_enabled else "false"
                os.environ["LANGSMITH_TRACING"] = tracing_str
                os.environ["LANGCHAIN_TRACING_V2"] = tracing_str
                
                # Set endpoint if provided in env (important for EU endpoints)
                if os.getenv("LANGSMITH_ENDPOINT"):
                    os.environ["LANGSMITH_ENDPOINT"] = os.getenv("LANGSMITH_ENDPOINT")
                    logger.info(f"✅ LangSmith enabled: project={project_name}, endpoint={os.getenv('LANGSMITH_ENDPOINT')}")
                else:
                    logger.info(f"✅ LangSmith enabled: project={project_name}")
            else:
                logger.warning(
                    "⚠️ LangSmith enabled but no API key found. "
                    "Set LANGSMITH_API_KEY or LANGCHAIN_API_KEY environment variable."
                )
        else:
            logger.info("LangSmith monitoring disabled")
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state graph with agentic RAG flow.
        
        Flow:
        1. router -> decides RAG or DIRECT
        2. If RAG:
           - decompose -> retrieve -> grade -> (generate_answer OR rewrite_question -> retrieve -> grade -> generate_answer)
        3. If DIRECT:
           - direct -> END
        """
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("router", self._route_query)
        workflow.add_node("decompose", self._decompose_query)
        workflow.add_node("retrieve", self._retrieve_node)
        workflow.add_node("grade", self._grade_documents)
        workflow.add_node("rewrite_question", self._rewrite_question)
        workflow.add_node("generate_answer", self._generate_answer)
        workflow.add_node("direct", self._direct_node)
        
        # Set entry point
        workflow.set_entry_point("router")
        
        # Add conditional edges from router
        workflow.add_conditional_edges(
            "router",
            self._should_use_rag,
            {
                "RAG": "decompose",  # Decompose before retrieving
                "DIRECT": "direct",
            }
        )
        
        # Decompose always leads to retrieve
        workflow.add_edge("decompose", "retrieve")
        
        # After retrieval, grade documents
        workflow.add_edge("retrieve", "grade")
        
        # After grading, decide: generate answer or rewrite question
        workflow.add_conditional_edges(
            "grade",
            self._should_rewrite,
            {
                "generate_answer": "generate_answer",
                "rewrite_question": "rewrite_question",
            }
        )
        
        # After rewriting, retrieve again (but only once)
        workflow.add_edge("rewrite_question", "retrieve")
        
        # Both generate_answer and direct lead to END
        workflow.add_edge("generate_answer", END)
        workflow.add_edge("direct", END)
        
        return workflow.compile()
    
    @traceable(name="route_query")
    def _route_query(self, state: AgentState) -> AgentState:
        """Route the query to determine if RAG is needed."""
        query = state.query
        logger.info("=" * 80)
        logger.info("🔀 ROUTER AGENT: Starting routing decision")
        logger.info(f"Query: {query[:100]}...")
        logger.info("=" * 80)
        
        # IMPORTANT: Do NOT call retriever here - only decide route
        # Use LLM to determine route
        router_prompt = self.settings.agent.router_prompt
        if not router_prompt:
            # Fallback: simple keyword-based routing
            sentinel_keywords = ["sentinel", "sentiwiki", "copernicus", "s1", "s2", "s3", "s5p", "sar", "olci", "slstr", "mission", "product", "application", "processing"]
            query_lower = query.lower()
            needs_rag = any(keyword in query_lower for keyword in sentinel_keywords)
            route = "RAG" if needs_rag else "DIRECT"
        else:
            # Use LLM for routing
            messages = [
                {"role": "system", "content": router_prompt},
                {"role": "user", "content": f"Query: {query}\n\nRespond with ONLY one word: RAG or DIRECT"},
            ]
            
            # Log routing LLM call
            logger.info("=" * 80)
            logger.info("🤖 LLM CALL: Router Decision")
            logger.info("=" * 80)
            logger.info(f"📝 Query: {query}")
            estimated_tokens = (len(router_prompt) + len(query) + 50) // 4
            logger.info(f"📊 Estimated Prompt Tokens: ~{estimated_tokens:,}")
            logger.info("🚀 Invoking Router LLM...")
            logger.info("=" * 80)
            
            try:
                response = self.router_llm.invoke(messages)
                route = response.strip().upper()
                
                # Log token usage
                llm_metrics = self.router_llm.get_last_response_metrics()
                if llm_metrics:
                    logger.info("=" * 80)
                    logger.info("💰 Router LLM Token Usage")
                    logger.info("=" * 80)
                    prompt_tokens = llm_metrics.prompt_tokens
                    completion_tokens = llm_metrics.completion_tokens
                    total_tokens = llm_metrics.total_tokens
                    logger.info(f"📥 Prompt Tokens: {prompt_tokens:,}" if isinstance(prompt_tokens, int) else f"📥 Prompt Tokens: {prompt_tokens}")
                    logger.info(f"📤 Completion Tokens: {completion_tokens:,}" if isinstance(completion_tokens, int) else f"📤 Completion Tokens: {completion_tokens}")
                    logger.info(f"📊 Total Tokens: {total_tokens:,}" if isinstance(total_tokens, int) else f"📊 Total Tokens: {total_tokens}")
                    logger.info(f"✅ Route Decision: {route}")
                    logger.info("=" * 80)
                
                # Validate response
                if route not in ["RAG", "DIRECT"]:
                    logger.warning(f"Invalid route response: {route}, defaulting to RAG")
                    route = "RAG"
            except Exception as e:
                logger.error(f"Error in routing: {e}, defaulting to RAG")
                route = "RAG"
        
        logger.info(f"✅ Route determined: {route}")
        logger.info("=" * 80)
        logger.info("🔀 ROUTER AGENT: Routing decision complete")
        logger.info("=" * 80)
        return state.model_copy(update={"route": route})
    
    @traceable(name="decompose_query")
    def _decompose_query(self, state: AgentState) -> AgentState:
        """Decompose complex queries into sub-queries for better retrieval.

        For simple queries, returns the original query as a single-item list.
        For complex queries (comparisons, multiple topics), splits into sub-queries.

        This ensures backward compatibility: simple queries work exactly as before.
        """
        query = state.query
        
        logger.info("=" * 80)
        logger.info("🔀 DECOMPOSE NODE: Analyzing query complexity")
        logger.info(f"Original query: {query[:200]}...")
        logger.info("=" * 80)
        
        try:
            # Get decomposition prompt from config
            decompose_prompt_template = (
                self.settings.agent.decompose_prompt
                if getattr(self.settings.agent, "decompose_prompt", None)
                else (
                    "You are an expert query decomposer for Copernicus Sentinel Missions documentation.\n"
                    "Your task is to break down complex questions into a list of simple, independent search queries.\n\n"
                    "RULES - Decompose if the question:\n"
                    "1. Explicitly compares two or more topics (e.g., 'Sentinel-1 vs Sentinel-2', 'Which is better')\n"
                    "2. Asks about capabilities/techniques applied to a mission (e.g., 'Can I do InSAR with Sentinel-2?' needs info about BOTH InSAR requirements AND Sentinel-2 sensor type)\n"
                    "3. Mentions a technique/method AND a mission where you need to understand both separately\n"
                    "4. Asks about compatibility between a technique and a mission\n"
                    "5. Asks for multiple distinct pieces of information about different entities or concepts\n\n"
                    "DO NOT decompose if the question is simple and focuses on a single topic/entity.\n\n"
                    "Examples:\n"
                    "- 'What is Sentinel-1?' → ['What is Sentinel-1?']\n"
                    "- 'Which has wider swath: Sentinel-1 IW or Sentinel-2?' → ['Sentinel-1 IW swath width', 'Sentinel-2 swath width']\n"
                    "- 'Compare Sentinel-1 and Sentinel-2' → ['Sentinel-1 specifications', 'Sentinel-2 specifications']\n"
                    "- 'Can I do InSAR with Sentinel-2?' → ['InSAR sensor requirements', 'Sentinel-2 sensor type']\n\n"
                    "User Question: {question}\n\n"
                    "Respond ONLY with a JSON list of strings. Example: [\"query 1\", \"query 2\"]"
                )
            )
            
            decompose_prompt = decompose_prompt_template.format(question=query)
            
            # Use RAG LLM for decomposition (needs to understand context)
            messages = [
                {"role": "user", "content": decompose_prompt},
            ]
            
            response = self.rag_llm.invoke(messages, max_tokens=300)
            response = response.strip()
            
            # Parse JSON response
            # Handle cases where LLM adds explanation text before/after JSON
            sub_queries = None
            
            # Strategy 1: Try to find JSON array in response (handles text before/after)
            json_match = re.search(r'\[.*?\]', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                try:
                    sub_queries = json.loads(json_str)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse JSON array from response: {json_str}")
            
            # Strategy 2: Try parsing the entire response as JSON
            if sub_queries is None:
                try:
                    sub_queries = json.loads(response)
                except json.JSONDecodeError:
                    pass
            
            # Strategy 3: Try to extract list from markdown code blocks
            if sub_queries is None:
                code_block_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', response, re.DOTALL)
                if code_block_match:
                    try:
                        sub_queries = json.loads(code_block_match.group(1))
                    except json.JSONDecodeError:
                        pass
            
            # Fallback: use original query
            if sub_queries is None:
                logger.warning(f"Could not parse decomposition response: {response[:200]}...")
                sub_queries = [query]  # Fallback to original
            
            # Validate: ensure we have a list of strings
            if not isinstance(sub_queries, list) or not all(isinstance(q, str) for q in sub_queries):
                logger.warning(f"Invalid decomposition result: {sub_queries}, using original query")
                sub_queries = [query]
            
            # Safety check: if empty list, use original
            if not sub_queries:
                logger.warning("Decomposition returned empty list, using original query")
                sub_queries = [query]
            
            # Log decomposition result
            if len(sub_queries) == 1 and sub_queries[0] == query:
                logger.info("✅ Query is simple, no decomposition needed")
            else:
                logger.info(f"✅ Query decomposed into {len(sub_queries)} sub-queries:")
                for i, sq in enumerate(sub_queries, 1):
                    logger.info(f"   {i}. {sq[:100]}...")
            
            logger.info("=" * 80)

            return state.model_copy(update={"sub_queries": sub_queries})
        except Exception as e:
            logger.exception(f"Error in decompose node: {e}, using original query")
            # On error, use original query as single-item list (backward compatible)
            return state.model_copy(update={"sub_queries": [query]})
    
    def _should_use_rag(self, state: AgentState) -> Literal["RAG", "DIRECT"]:
        """Determine which path to take based on routing decision."""
        route = state.get("route")
        logger.info(f"🔀 Conditional edge check: route={route}, will return {'RAG' if route == 'RAG' else 'DIRECT'}")
        if route == "RAG":
            return "RAG"
        return "DIRECT"
    
    @traceable(name="retrieve_node")
    def _retrieve_node(self, state: AgentState) -> AgentState:
        """Retrieve documents for the query(s).
        
        Handles multiple scenarios:
        1. If rewritten_query exists: uses rewritten query (single query after rewrite)
        2. If sub_queries exists: retrieves for each sub-query and combines results
        3. Otherwise: uses original query (backward compatible)
        
        For decomposed queries, retrieves documents for each sub-query and combines them,
        removing duplicates to create a comprehensive context.
        """
        rewrite_attempted = state.get("rewrite_attempted", False)
        
        # Determine which queries to use
        if rewrite_attempted and state.get("rewritten_query"):
            # After rewrite: use rewritten query (single query)
            queries_to_run = [state["rewritten_query"]]
            logger.info("=" * 80)
            logger.info("📚 RETRIEVE NODE: Starting document retrieval (after rewrite)")
            logger.info(f"Using rewritten query: {state['rewritten_query'][:100]}...")
        elif state.get("sub_queries"):
            # Use decomposed sub-queries
            queries_to_run = state["sub_queries"]
            logger.info("=" * 80)
            logger.info("📚 RETRIEVE NODE: Starting document retrieval (decomposed query)")
            logger.info(f"Number of sub-queries: {len(queries_to_run)}")
            for i, q in enumerate(queries_to_run, 1):
                logger.info(f"  Sub-query {i}: {q[:100]}...")
        else:
            # Fallback: use original query (backward compatible)
            queries_to_run = [state["query"]]
            logger.info("=" * 80)
            logger.info("📚 RETRIEVE NODE: Starting document retrieval")
            logger.info(f"Query: {state['query'][:100]}...")
        
        logger.info("=" * 80)
        
        try:
            all_docs = []
            
            # Retrieve documents for each query
            for i, query in enumerate(queries_to_run, 1):
                if len(queries_to_run) > 1:
                    logger.info(f"📚 Searching for sub-query {i}/{len(queries_to_run)}: {query[:100]}...")
                else:
                    logger.info("📚 RETRIEVE NODE: Calling retriever.retrieve()...")
                
                docs = self.retriever.retrieve(
                    query=query,
                    top_k=None,  # Use default from config
                    filters=None,
                    use_reranking=True,
                    use_hybrid=True,
                )
                
                logger.info(f"✅ Retrieved {len(docs)} documents for this query")
                all_docs.extend(docs)
            
            # Remove duplicates based on document ID or content hash
            unique_docs = self._deduplicate_docs(all_docs)
            
            logger.info(f"✅ Total unique documents retrieved: {len(unique_docs)} (from {len(all_docs)} total)")
            logger.info("=" * 80)

            return state.model_copy(update={"retrieved_docs": unique_docs})
        except Exception as e:
            logger.exception(f"Error in retrieve node: {e}")
            return state.model_copy(update={"retrieved_docs": []})
    
    def _deduplicate_docs(self, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate documents from the list.
        
        Uses document ID if available, otherwise uses content hash.
        """
        seen = set()
        unique_docs = []
        
        for doc in docs:
            # Try to use document ID first
            doc_id = doc.get("id") or doc.get("document_id")
            if doc_id:
                if doc_id not in seen:
                    seen.add(doc_id)
                    unique_docs.append(doc)
            else:
                # Fallback: use content hash
                content = doc.get("text", "") or doc.get("contextualized_text", "")
                content_hash = hash(content[:500])  # Hash first 500 chars
                if content_hash not in seen:
                    seen.add(content_hash)
                    unique_docs.append(doc)
        
        return unique_docs
    
    def _grade_documents(self, state: AgentState) -> AgentState:
        """Grade retrieved documents using relevance scores from retrieval.
        
        Uses the relevance scores from the retrieval system instead of LLM grading.
        This is more efficient and accurate since the retrieval system already calculated
        semantic similarity scores.
        """
        query = state["query"]
        docs = state.get("retrieved_docs", [])
        
        logger.info("=" * 80)
        logger.info("📊 GRADE NODE: Evaluating document relevance using retrieval scores")
        logger.info(f"Query: {query[:100]}...")
        logger.info(f"Documents to evaluate: {len(docs)}")
        logger.info("=" * 80)
        
        if not docs:
            logger.warning("⚠️  No documents retrieved, marking as not relevant")
            return state.model_copy(update={"grade_score": "no",
                "relevance_avg_score": 0.0,
                "relevance_top_score": 0.0,
                "relevance_top_5_avg": 0.0,})
        
        try:
            # Extract relevance scores from documents
            scores = []
            for doc in docs:
                score = doc.get("score", 0.0)
                if score is not None:
                    scores.append(float(score))
            
            if not scores:
                logger.warning("⚠️  No scores found in documents, marking as not relevant")
                return state.model_copy(update={"grade_score": "no",
                    "relevance_avg_score": 0.0,
                    "relevance_top_score": 0.0,
                    "relevance_top_5_avg": 0.0,})
            
            # Calculate metrics
            avg_score = sum(scores) / len(scores)
            top_score = max(scores)
            top_5_avg = sum(sorted(scores, reverse=True)[:5]) / min(5, len(scores))
            
            # Get threshold from config (default: 0.5)
            relevance_threshold = getattr(self.settings.agent, "relevance_threshold", 0.5)
            
            # Determine if documents are relevant
            # Use top_5_avg for better judgment (top documents matter more)
            is_relevant = top_5_avg >= relevance_threshold
            
            grade_score = "yes" if is_relevant else "no"
            
            logger.info(f"📊 Relevance Scores:")
            logger.info(f"   Top score: {top_score:.4f}")
            logger.info(f"   Top 5 average: {top_5_avg:.4f}")
            logger.info(f"   Overall average: {avg_score:.4f}")
            logger.info(f"   Threshold: {relevance_threshold:.4f}")
            logger.info(f"✅ Grade decision: {grade_score} (top_5_avg {'>=' if is_relevant else '<'} threshold)")
            logger.info("=" * 80)
            
            return state.model_copy(update={"grade_score": grade_score,
                "relevance_avg_score": avg_score,
                "relevance_top_score": top_score,
                "relevance_top_5_avg": top_5_avg,})
        except Exception as e:
            logger.exception(f"Error in grade node: {e}, defaulting to 'no'")
            return state.model_copy(update={"grade_score": "no",
                "relevance_avg_score": 0.0,
                "relevance_top_score": 0.0,
                "relevance_top_5_avg": 0.0,})
    
    def _should_rewrite(self, state: AgentState) -> Literal["generate_answer", "rewrite_question"]:
        """Determine whether to rewrite question or generate answer based on grade."""
        grade_score = state.get("grade_score")
        rewrite_attempted = state.get("rewrite_attempted", False)
        
        # If documents are relevant, generate answer
        if grade_score == "yes":
            logger.info("✅ Documents are relevant, proceeding to generate answer")
            return "generate_answer"
        
        # If documents are not relevant but we've already rewritten once, generate answer anyway
        if rewrite_attempted:
            logger.warning("⚠️  Documents not relevant after rewrite, generating answer anyway")
            return "generate_answer"
        
        # If documents are not relevant and we haven't rewritten yet, rewrite the question
        logger.info("❌ Documents not relevant, rewriting question")
        return "rewrite_question"
    
    @traceable(name="rewrite_question")
    def _rewrite_question(self, state: AgentState) -> AgentState:
        """Rewrite the original user question to improve retrieval.
        
        Uses retrieved documents to understand what's available in the knowledge base
        and rewrite the query to better match available content.
        """
        query = state["query"]
        docs = state.get("retrieved_docs", [])
        
        logger.info("=" * 80)
        logger.info("🔄 REWRITE NODE: Rewriting question")
        logger.info(f"Original query: {query[:100]}...")
        logger.info(f"Retrieved documents: {len(docs)}")
        logger.info("=" * 80)
        
        try:
            # Format retrieved documents summary for context
            docs_summary = ""
            if docs:
                # Include top 3-5 documents to give context about what's available
                docs_summary_parts = []
                for i, doc in enumerate(docs[:5], 1):
                    text = doc.get("contextualized_text") or doc.get("text", "")
                    # Truncate to keep it concise (200 chars per doc)
                    text = text[:200] + "..." if len(text) > 200 else text
                    title = doc.get("title", "Unknown")
                    docs_summary_parts.append(
                        f"[Document {i}] {title}\n"
                        f"Content preview: {text}\n"
                    )
                docs_summary = "\n---\n\n".join(docs_summary_parts)
            
            # Get rewrite prompt from config
            rewrite_prompt_template = (
                self.settings.agent.rewrite_question_prompt
                if self.settings.agent.rewrite_question_prompt
                else (
                    "You are a question rewriting assistant. Your task is to improve a user question for better document retrieval.\n"
                    "The original question did not retrieve relevant documents. Rewrite it to be more specific, "
                    "include relevant keywords, and clarify the intent.\n\n"
                    "Original question:\n"
                    "-------\n"
                    "{question}\n"
                    "-------\n"
                    "{retrieved_docs_context}"
                    "Formulate an improved question. Respond with ONLY the improved question, no prefixes or explanations:"
                )
            )
            
            # Build context about retrieved documents and relevance scores
            relevance_info = ""
            if state.get("relevance_top_5_avg") is not None:
                relevance_info = (
                    f"\n⚠️ RELEVANCE SCORES (Low - triggering rewrite):\n"
                    f"   Top 5 average: {state.get('relevance_top_5_avg', 0.0):.4f}\n"
                    f"   Overall average: {state.get('relevance_avg_score', 0.0):.4f}\n"
                    f"   Top score: {state.get('relevance_top_score', 0.0):.4f}\n"
                    f"   Threshold: {getattr(self.settings.agent, 'relevance_threshold', 0.5):.4f}\n"
                    f"   The documents retrieved have low relevance scores, indicating the query needs improvement.\n\n"
                )
            
            if docs_summary:
                retrieved_docs_context = (
                    f"{relevance_info}"
                    f"The following documents were retrieved but had LOW RELEVANCE SCORES:\n"
                    "-------\n"
                    f"{docs_summary}\n"
                    "-------\n"
                    "Use this information to understand what topics are available in the knowledge base. "
                    "Rewrite the question to better match the available content, using terms and concepts "
                    "that are more likely to retrieve documents with HIGHER relevance scores.\n\n"
                )
            else:
                retrieved_docs_context = (
                    f"{relevance_info}"
                    "No documents were retrieved, or documents had very low relevance scores. "
                    "Rewrite the question to be more specific and use terminology that matches SentiWiki documentation.\n\n"
                )
            
            rewrite_prompt = rewrite_prompt_template.format(
                question=query,
                retrieved_docs_context=retrieved_docs_context
            )
            
            # Use RAG LLM for rewriting (needs more tokens than router LLM)
            # Router LLM has max_tokens=20 which is too low for full queries
            messages = [
                {"role": "user", "content": rewrite_prompt},
            ]
            
            # Log rewrite LLM call
            logger.info("=" * 80)
            logger.info("🤖 LLM CALL: Query Rewriting")
            logger.info("=" * 80)
            logger.info(f"📝 Original Query: {query}")
            logger.info(f"📊 Rewrite Prompt Length: {len(rewrite_prompt):,} characters")
            estimated_tokens = len(rewrite_prompt) // 4
            logger.info(f"📊 Estimated Prompt Tokens: ~{estimated_tokens:,}")
            logger.debug(f"📄 Rewrite Prompt (Full Content):")
            logger.debug("-" * 80)
            for i, line in enumerate(rewrite_prompt.split('\n'), 1):
                logger.debug(f"{i:4d} | {line}")
            logger.debug("-" * 80)
            logger.info("🚀 Invoking LLM for query rewriting...")
            logger.info("=" * 80)
            
            # Temporarily override max_tokens for rewriting (need more than 20)
            rewritten = self.rag_llm.invoke(messages, max_tokens=200)
            
            # Log token usage
            llm_metrics = self.rag_llm.get_last_response_metrics()
            if llm_metrics:
                logger.info("=" * 80)
                logger.info("💰 Rewrite LLM Token Usage")
                logger.info("=" * 80)
                prompt_tokens = llm_metrics.prompt_tokens
                completion_tokens = llm_metrics.completion_tokens
                total_tokens = llm_metrics.total_tokens
                logger.info(f"📥 Prompt Tokens: {prompt_tokens:,}" if isinstance(prompt_tokens, int) else f"📥 Prompt Tokens: {prompt_tokens}")
                logger.info(f"📤 Completion Tokens: {completion_tokens:,}" if isinstance(completion_tokens, int) else f"📤 Completion Tokens: {completion_tokens}")
                logger.info(f"📊 Total Tokens: {total_tokens:,}" if isinstance(total_tokens, int) else f"📊 Total Tokens: {total_tokens}")
                logger.info(f"✅ Rewritten Query: {rewritten}")
                logger.info("=" * 80)
            rewritten = rewritten.strip()
            
            # Validate rewritten query is not empty or too short
            if not rewritten or len(rewritten) < 10:
                logger.warning(f"⚠️  Rewritten query is too short or empty: '{rewritten}', using original query")
                rewritten = query
            
            # Clean up common LLM prefixes that might be included
            prefixes_to_remove = [
                "Improved question:",
                "Improved question:\n",
                "Refined question:",
                "Refined question:\n",
                "Better question:",
                "Better question:\n",
                "Here is the improved question:",
                "Here is the improved question:\n",
            ]
            for prefix in prefixes_to_remove:
                if rewritten.lower().startswith(prefix.lower()):
                    rewritten = rewritten[len(prefix):].strip()
                # Also check if it's on a separate line
                if "\n" in rewritten:
                    first_line = rewritten.split("\n")[0].strip()
                    if first_line.lower() in [p.lower().rstrip(":") for p in prefixes_to_remove]:
                        rewritten = "\n".join(rewritten.split("\n")[1:]).strip()
            
            logger.info(f"✅ Rewritten query: {rewritten[:100]}...")
            logger.info("=" * 80)
            
            return state.model_copy(update={"rewritten_query": rewritten,
                "rewrite_attempted": True,})
        except Exception as e:
            logger.exception(f"Error in rewrite node: {e}")
            # On error, just use original query
            return state.model_copy(update={"rewritten_query": query,
                "rewrite_attempted": True,})
    
    @traceable(name="generate_answer")
    def _generate_answer(self, state: AgentState) -> AgentState:
        """Generate final answer from retrieved documents.
        
        Uses rewritten_query if available (since that's what retrieved the documents),
        otherwise uses original query.
        """
        # Use rewritten query if available, otherwise use original
        # The rewritten query is what actually retrieved the documents, so we should use it
        rewritten_query = state.get("rewritten_query")
        original_query = state["query"]
        
        # Validate rewritten query is complete (not truncated)
        if rewritten_query:
            # Check if query looks incomplete (ends with incomplete words, very short, etc.)
            if len(rewritten_query) < 15 or rewritten_query.endswith((" its", " the", " a ", " an ", " of", " in", " on", " at")):
                logger.warning(f"⚠️  Rewritten query appears incomplete: '{rewritten_query}', falling back to original")
                query_for_answer = original_query
            else:
                query_for_answer = rewritten_query
        else:
            query_for_answer = original_query
        
        docs = state.get("retrieved_docs", [])
        
        logger.info("=" * 80)
        logger.info("✍️  GENERATE ANSWER NODE: Generating final answer")
        logger.info(f"Original query: {original_query[:100]}...")
        if state.get("rewritten_query"):
            logger.info(f"Using rewritten query: {query_for_answer[:100]}...")
        logger.info(f"Documents: {len(docs)}")
        logger.info("=" * 80)
        
        if not docs:
            logger.warning("⚠️  No documents available, generating answer without context")
            return state.model_copy(update={
                "answer": "I couldn't find relevant information in the SentiWiki documentation to answer your question. Please try rephrasing your question or being more specific.",
                "sources": [],
                "context": "",
                "metadata": {
                    **state.get("metadata", {}),
                    "mode": "rag",
                    "num_docs": 0,
                    "rewrite_attempted": state.get("rewrite_attempted", False),
                    "rewritten_query": state.get("rewritten_query"),
                    "grade_score": state.get("grade_score"),
                    "relevance_avg_score": state.get("relevance_avg_score"),
                    "relevance_top_score": state.get("relevance_top_score"),
                    "relevance_top_5_avg": state.get("relevance_top_5_avg"),
                    "decomposed": state.get("sub_queries") is not None and len(state.get("sub_queries", [])) > 1,
                    "num_sub_queries": len(state.get("sub_queries", [])) if state.get("sub_queries") else 1,
                },
            })
        
        try:
            # Format context
            context_parts = []
            for i, doc in enumerate(docs, 1):
                text = doc.get("contextualized_text") or doc.get("text", "")
                score = doc.get("score", 0.0)
                context_parts.append(
                    f"[Document {i}] {doc.get('title', 'Unknown')} "
                    f"(Relevance: {score:.4f})\n"
                    f"Content:\n{text}\n"
                )
            context = "\n---\n\n".join(context_parts)
            
            # Extract ECSS standards
            standards_in_context = extract_standards_from_docs(docs)
            
            # Build system prompt
            system_prompt = build_rag_system_prompt(
                context=context,
                standards_in_context=standards_in_context,
            )
            
            # Prepare messages
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query_for_answer},
            ]
            
            # ====================================================================
            # DETAILED LOGGING: Context and Token Information
            # ====================================================================
            logger.info("=" * 80)
            logger.info("🤖 LLM CALL: RAG Answer Generation")
            logger.info("=" * 80)
            logger.info(f"📝 Query: {query_for_answer}")
            if state.get("rewritten_query"):
                logger.info(f"🔄 Original Query: {original_query}")
                logger.info(f"✅ Using rewritten query (improved for retrieval)")
            logger.info("")
            logger.info(f"📊 Context Statistics:")
            logger.info(f"   - Documents: {len(docs)}")
            logger.info(f"   - Context Length: {len(context):,} characters")
            logger.info(f"   - System Prompt Length: {len(system_prompt):,} characters")
            logger.info(f"   - User Query Length: {len(query_for_answer):,} characters")
            # Estimate tokens (rough: ~4 chars per token)
            estimated_tokens = (len(system_prompt) + len(query_for_answer)) // 4
            logger.info(f"   - Estimated Prompt Tokens: ~{estimated_tokens:,}")
            logger.info("")
            # Document summary logging (only to log files, not terminal)
            logger.debug(f"📄 Documents Used as Context:")
            logger.debug("-" * 80)
            for i, doc in enumerate(docs, 1):
                title = doc.get('title', 'Unknown')
                score = doc.get('score', 0.0)
                text = doc.get("contextualized_text") or doc.get("text", "")
                text_length = len(text)
                url = doc.get('url', '')
                heading = doc.get('heading', '')
                logger.debug(f"  [{i}/{len(docs)}] {title} | Score: {score:.4f} | Length: {text_length:,} chars (~{text_length//4:,} tokens)")
                if url:
                    logger.debug(f"      URL: {url}")
                if heading:
                    logger.debug(f"      Heading: {heading}")
            logger.debug("-" * 80)
            logger.debug("")
            logger.debug(f"📋 Full System Prompt (for review):")
            logger.debug("-" * 80)
            # Log system prompt with line numbers for easier review
            for i, line in enumerate(system_prompt.split('\n'), 1):
                logger.debug(f"{i:4d} | {line}")
            logger.debug("-" * 80)
            logger.debug("")
            logger.info("🚀 Invoking LLM...")
            logger.info("=" * 80)
            
            # Generate answer using RAG LLM
            answer = self.rag_llm.invoke(messages)
            
            # Log token usage after LLM call
            llm_metrics = self.rag_llm.get_last_response_metrics()
            if llm_metrics:
                logger.info("=" * 80)
                logger.info("💰 LLM CALL COMPLETED: Token Usage")
                logger.info("=" * 80)
                prompt_tokens = llm_metrics.prompt_tokens
                completion_tokens = llm_metrics.completion_tokens
                total_tokens = llm_metrics.total_tokens
                logger.info(f"📥 Prompt Tokens: {prompt_tokens:,}" if isinstance(prompt_tokens, int) else f"📥 Prompt Tokens: {prompt_tokens}")
                logger.info(f"📤 Completion Tokens: {completion_tokens:,}" if isinstance(completion_tokens, int) else f"📤 Completion Tokens: {completion_tokens}")
                logger.info(f"📊 Total Tokens: {total_tokens:,}" if isinstance(total_tokens, int) else f"📊 Total Tokens: {total_tokens}")
                if llm_metrics.cost:
                    logger.info(f"💵 Cost: ${llm_metrics.cost:.6f}")
                logger.info("=" * 80)
            
            # Format sources using shared utility function
            sources = format_sources_for_response(docs, limit=None)
            
            logger.info("✅ Answer generated successfully")
            logger.info("=" * 80)
            
            return state.model_copy(update={"answer": answer,
                "sources": sources,
                "context": context[:1000] + "..." if len(context) > 1000 else context,
                "metadata": {
                    **state.get("metadata", {}),
                    "mode": "rag",
                    "num_docs": len(docs),
                    "collection": self.retriever.qdrant.collection_name,
                    "rewrite_attempted": state.get("rewrite_attempted", False),
                    "rewritten_query": state.get("rewritten_query"),
                    "grade_score": state.get("grade_score"),
                    "relevance_avg_score": state.get("relevance_avg_score"),
                    "relevance_top_score": state.get("relevance_top_score"),
                    "relevance_top_5_avg": state.get("relevance_top_5_avg"),
                    "decomposed": state.get("sub_queries") is not None and len(state.get("sub_queries", [])) > 1,
                    "num_sub_queries": len(state.get("sub_queries", [])) if state.get("sub_queries") else 1,
                },
            })
        except Exception as e:
            logger.exception(f"Error in generate answer node: {e}")
            return state.model_copy(update={
                "answer": f"I encountered an error while generating the answer: {str(e)})",
                "sources": [],
                "context": "",
            })
    
    @traceable(name="direct_node")
    def _direct_node(self, state: AgentState) -> AgentState:
        """Execute direct LLM generation (no RAG).
        
        NOTE: This node should ONLY be executed AFTER router decides route="DIRECT".
        No retrieval should happen here!
        """
        query = state["query"]
        route = state.get("route")
        
        logger.info("=" * 80)
        logger.info("💬 DIRECT NODE: Starting direct LLM generation")
        logger.info(f"Query: {query[:100]}...")
        logger.info(f"Route from state: {route}")
        logger.info("⚠️  No retrieval should happen in this node!")
        logger.info("=" * 80)
        
        try:
            # Use direct LLM system prompt
            system_prompt = self.settings.agent.direct_llm_system_prompt
            if not system_prompt:
                system_prompt = "You are a helpful AI assistant for Copernicus Sentinel Missions documentation (SentiWiki)."
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ]
            
            # Log direct LLM call
            logger.info("=" * 80)
            logger.info("🤖 LLM CALL: Direct Answer Generation (No RAG)")
            logger.info("=" * 80)
            logger.info(f"📝 Query: {query}")
            logger.info(f"📊 System Prompt Length: {len(system_prompt):,} characters")
            logger.info(f"📊 User Query Length: {len(query):,} characters")
            estimated_tokens = (len(system_prompt) + len(query)) // 4
            logger.info(f"📊 Estimated Prompt Tokens: ~{estimated_tokens:,}")
            logger.debug(f"📋 System Prompt (Full Content):")
            logger.debug("-" * 80)
            for i, line in enumerate(system_prompt.split('\n'), 1):
                logger.debug(f"{i:4d} | {line}")
            logger.debug("-" * 80)
            logger.info("🚀 Invoking Direct LLM...")
            logger.info("=" * 80)
            
            answer = self.direct_llm.invoke(messages)
            
            # Log token usage
            llm_metrics = self.direct_llm.get_last_response_metrics()
            if llm_metrics:
                logger.info("=" * 80)
                logger.info("💰 Direct LLM Token Usage")
                logger.info("=" * 80)
                prompt_tokens = llm_metrics.prompt_tokens
                completion_tokens = llm_metrics.completion_tokens
                total_tokens = llm_metrics.total_tokens
                logger.info(f"📥 Prompt Tokens: {prompt_tokens:,}" if isinstance(prompt_tokens, int) else f"📥 Prompt Tokens: {prompt_tokens}")
                logger.info(f"📤 Completion Tokens: {completion_tokens:,}" if isinstance(completion_tokens, int) else f"📤 Completion Tokens: {completion_tokens}")
                logger.info(f"📊 Total Tokens: {total_tokens:,}" if isinstance(total_tokens, int) else f"📊 Total Tokens: {total_tokens}")
                if llm_metrics.cost:
                    logger.info(f"💵 Cost: ${llm_metrics.cost:.6f}")
                logger.info("=" * 80)
            
            return state.model_copy(update={"answer": answer,
                "sources": [],
                "context": "",
                "metadata": {
                    **state.get("metadata", {}),
                    "mode": "direct",
                },
            })
        except Exception as e:
            logger.exception(f"Error in direct node: {e}")
            return state.model_copy(update={"answer": f"I encountered an error: {str(e)})",
                "sources": [],
                "context": "",
            })
    
    def invoke(self, query: str, config: Optional[RunnableConfig] = None) -> AgentState:
        """Invoke the agent with a query.
        
        Args:
            query: User query
            config: Optional LangGraph config (for LangSmith tracing)
            
        Returns:
            AgentState with answer, sources, and metadata
        """
        logger.info("=" * 80)
        logger.info("🚀 ROUTER AGENT: Starting invoke()")
        logger.info(f"Query: {query[:100]}...")
        logger.info("NOTE: retriever.retrieve() should ONLY be called in _rag_node(), NOT in _route_query()")
        logger.info("=" * 80)
        
        initial_state: AgentState = {
            "query": query,
            "route": None,
            "answer": "",
            "sources": [],
            "context": "",
            "metadata": {},
            "retrieved_docs": [],
            "rewritten_query": None,
            "grade_score": None,
            "rewrite_attempted": False,
            "relevance_avg_score": None,
            "relevance_top_score": None,
            "relevance_top_5_avg": None,
            "sub_queries": None,
        }
        
        result = self.graph.invoke(initial_state, config=config)
        
        logger.info("=" * 80)
        logger.info("🚀 ROUTER AGENT: invoke() complete")
        logger.info(f"Final route: {result.get('route', 'UNKNOWN')}")
        logger.info("=" * 80)
        
        return result
    
    async def astream(self, query: str, config: Optional[RunnableConfig] = None):
        """Stream the agent execution.
        
        Args:
            query: User query
            config: Optional LangGraph config
            
        Yields:
            AgentState updates as they occur
        """
        initial_state: AgentState = {
            "query": query,
            "route": None,
            "answer": "",
            "sources": [],
            "context": "",
            "metadata": {},
            "retrieved_docs": [],
            "rewritten_query": None,
            "grade_score": None,
            "rewrite_attempted": False,
            "relevance_avg_score": None,
            "relevance_top_score": None,
            "relevance_top_5_avg": None,
            "sub_queries": None,
        }
        
        async for state in self.graph.astream(initial_state, config=config):
            yield state


__all__ = ["RouterAgent", "AgentState"]

