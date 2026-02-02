"""Advanced retrieval with reranking and hybrid search."""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from loguru import logger

from src.db.qdrant_client import QdrantManager
from src.utils.metadata_filter import SmartMetadataExtractor
from src.utils.config import get_settings

try:
    from sentence_transformers import SentenceTransformer, CrossEncoder
except ImportError:  # pragma: no cover
    SentenceTransformer = None
    CrossEncoder = None

try:
    from langchain_openai import OpenAIEmbeddings
except ImportError:  # pragma: no cover
    OpenAIEmbeddings = None


class _ModelRegistry:
    """Singleton registry for shared ML models.

    This class ensures that expensive ML models (embedder, reranker) are loaded
    only once and shared across all AdvancedRetriever instances. This prevents:
    - OOM errors from multiple model instances
    - Slow startup from repeated model loading
    - Wasted GPU/CPU memory

    Thread-safe implementation using double-checked locking pattern.

    Usage:
        # Models are automatically shared via AdvancedRetriever
        retriever1 = AdvancedRetriever(collection_name="collection_a")
        retriever2 = AdvancedRetriever(collection_name="collection_b")
        # Both share the same embedder and reranker instances
    """

    _instance: Optional["_ModelRegistry"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "_ModelRegistry":
        if cls._instance is None:
            with cls._lock:
                # Double-check after acquiring lock
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        # Prevent re-initialization
        if self._initialized:
            return

        self._embedder: Any = None
        self._reranker: Any = None
        self._embedder_lock = threading.Lock()
        self._reranker_lock = threading.Lock()
        self._initialized = True

        # Cache config to detect changes
        self._embedder_config: Optional[tuple[str, str]] = None
        self._reranker_config: Optional[str] = None

    def get_embedder(
        self,
        provider: str,
        model_name: str,
        api_key: Optional[str] = None,
    ) -> Any:
        """Get or create embedder instance.

        Args:
            provider: Embedding provider ("huggingface" or "openai")
            model_name: Model identifier
            api_key: API key for OpenAI (optional)

        Returns:
            Embedder instance (SentenceTransformer or OpenAIEmbeddings)

        Raises:
            ImportError: If required library is not installed
            ValueError: If provider is not supported
        """
        config_key = (provider, model_name)

        # Fast path: already loaded with same config
        if self._embedder is not None and self._embedder_config == config_key:
            return self._embedder

        with self._embedder_lock:
            # Double-check after acquiring lock
            if self._embedder is not None and self._embedder_config == config_key:
                return self._embedder

            # Config changed or first load
            if self._embedder is not None:
                logger.warning(
                    f"Embedder config changed from {self._embedder_config} to {config_key}. "
                    "Creating new embedder instance."
                )

            self._embedder = self._create_embedder(provider, model_name, api_key)
            self._embedder_config = config_key
            return self._embedder

    def _create_embedder(
        self,
        provider: str,
        model_name: str,
        api_key: Optional[str],
    ) -> Any:
        """Create a new embedder instance."""
        if provider == "huggingface":
            if SentenceTransformer is None:
                raise ImportError(
                    "sentence-transformers is required for huggingface embeddings. "
                    "Install with: pip install sentence-transformers"
                )
            logger.info(f"Loading SentenceTransformer: {model_name}")
            embedder = SentenceTransformer(model_name)
            logger.success(f"✓ SentenceTransformer loaded: {model_name}")
            return embedder

        if provider == "openai":
            if OpenAIEmbeddings is None:
                raise ImportError(
                    "langchain-openai is required for OpenAI embeddings. "
                    "Install with: pip install langchain-openai"
                )
            logger.info(f"Using OpenAI embeddings: {model_name}")
            return OpenAIEmbeddings(model=model_name, api_key=api_key)

        raise ValueError(f"Unsupported embedding provider: {provider}")

    def get_reranker(self, model_name: str, enabled: bool = True) -> Optional[Any]:
        """Get or create reranker instance.

        Args:
            model_name: Reranker model identifier
            enabled: Whether reranking is enabled

        Returns:
            CrossEncoder instance or None if disabled/unavailable
        """
        if not enabled:
            return None

        # Fast path: already loaded with same config
        if self._reranker is not None and self._reranker_config == model_name:
            return self._reranker

        with self._reranker_lock:
            # Double-check after acquiring lock
            if self._reranker is not None and self._reranker_config == model_name:
                return self._reranker

            self._reranker = self._create_reranker(model_name)
            self._reranker_config = model_name
            return self._reranker

    def _create_reranker(self, model_name: str) -> Optional[Any]:
        """Create a new reranker instance."""
        if CrossEncoder is None:
            logger.warning(
                "CrossEncoder not available. Install sentence-transformers: "
                "pip install sentence-transformers"
            )
            return None

        # Detect model type and add prefix if needed
        is_bge_model = model_name.startswith("BAAI/") or "bge-reranker" in model_name.lower()
        is_cross_encoder = model_name.startswith("cross-encoder/")

        if not is_cross_encoder and not is_bge_model:
            model_name = f"cross-encoder/{model_name}"

        try:
            model_type = "BGE Reranker" if is_bge_model else "CrossEncoder"
            logger.info(f"Loading {model_type} reranker: {model_name}")
            reranker = CrossEncoder(model_name)
            logger.success(f"✓ {model_type} loaded successfully: {model_name}")
            return reranker
        except Exception as e:
            logger.error(f"Failed to load reranker: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None


# Global model registry instance
_model_registry = _ModelRegistry()


class AdvancedRetriever:
    """Advanced retriever with reranking and hybrid search capabilities.

    This class uses a shared model registry to prevent loading ML models
    multiple times. Different collections can be used without reloading models.

    Attributes:
        collection_name: Name of the Qdrant collection to search
        embedder: Shared embedding model (singleton)
        reranker: Shared reranking model (singleton)
    """

    def __init__(self, collection_name: Optional[str] = None) -> None:
        """Initialize retriever with optional collection override.

        Args:
            collection_name: Qdrant collection to search. If None, uses default
                           from settings. Changing collection does NOT reload models.
        """
        self.settings = get_settings()

        # Use provided collection or default from settings
        self._collection_name = collection_name or self.settings.qdrant.collection_name
        self.qdrant = QdrantManager(collection_name=self._collection_name)

        # Detect collection vector size and select appropriate embedding model
        collection_vector_size = self.qdrant.get_collection_vector_size()
        
        # Select embedding model based on collection vector size
        self.embed_provider = self.settings.embeddings.provider
        vector_size_to_model = self.settings.embeddings.vector_size_to_model or {}
        
        if collection_vector_size and collection_vector_size in vector_size_to_model:
            # Use model mapped to this vector size
            self.embed_model_name = vector_size_to_model[collection_vector_size]
            logger.info(
                f"Collection {self._collection_name} has vector_size={collection_vector_size}, "
                f"using embedding model: {self.embed_model_name}"
            )
        else:
            # Use default model from config
            self.embed_model_name = self.settings.embeddings.model
            if collection_vector_size:
                logger.warning(
                    f"Collection {self._collection_name} has vector_size={collection_vector_size}, "
                    f"but no mapping found in config. Using default model: {self.embed_model_name}. "
                    f"Please add mapping in embeddings.vector_size_to_model if needed."
                )
            else:
                logger.info(
                    f"Could not detect vector size for collection {self._collection_name}, "
                    f"using default embedding model: {self.embed_model_name}"
                )
        
        # Retrieval settings (read once from config)
        self.top_k_default = self.settings.retrieval.top_k
        self.normalize_embeddings = self.embed_provider == "huggingface"
        self.reranker_enabled = self.settings.retrieval.reranker_enabled
        self.rerank_top_n = self.settings.retrieval.rerank_top_n
        self.reranker_model = self.settings.retrieval.reranker_model
        self.hybrid_search_enabled = self.settings.retrieval.hybrid_search_enabled
        self.hybrid_alpha = self.settings.retrieval.hybrid_search_alpha
        self.metadata_filtering_enabled = self.settings.retrieval.metadata_filtering_enabled

        # Get shared model instances from registry (no reloading!)
        # The registry will cache models by (provider, model_name) key
        self.embedder = _model_registry.get_embedder(
            provider=self.embed_provider,
            model_name=self.embed_model_name,
            api_key=getattr(self.settings, "openai_api_key", None),
        )
        self.reranker = _model_registry.get_reranker(
            model_name=self.reranker_model,
            enabled=self.reranker_enabled,
        )

        # Metadata extractors (lightweight, OK to create per instance)
        self.smart_metadata_extractor = SmartMetadataExtractor()

        # Store collection vector size for validation
        self._collection_vector_size = collection_vector_size

        logger.success(
            f"Retriever ready (collection={self._collection_name}, "
            f"vector_size={collection_vector_size}, "
            f"provider={self.embed_provider}, model={self.embed_model_name}, "
            f"reranking={self.reranker_enabled}, hybrid_search={self.hybrid_search_enabled})"
        )

    @property
    def collection_name(self) -> str:
        """Get current collection name."""
        return self._collection_name

    def with_collection(self, collection_name: str) -> "AdvancedRetriever":
        """Create a new retriever for a different collection (shares models).

        This is more explicit than creating a new AdvancedRetriever instance
        and makes it clear that models are shared.

        Args:
            collection_name: Name of the collection to use

        Returns:
            New AdvancedRetriever instance with shared models
        """
        return AdvancedRetriever(collection_name=collection_name)

    def _embed_query(self, query: str) -> List[float]:
        if self.embed_provider == "huggingface":
            # BGE models require instruction prefix for queries (not documents!)
            # This significantly improves retrieval quality (+15-20%)
            query_text = query
            if "bge" in self.embed_model_name.lower():
                query_text = f"Represent this sentence for searching relevant passages: {query}"
            
            embedding = self.embedder.encode(
                [query_text],
                normalize_embeddings=self.normalize_embeddings,
            )[0]
            embedding_list = embedding.tolist() if hasattr(embedding, "tolist") else embedding
            
            # Validate embedding dimension matches collection vector size
            if self._collection_vector_size:
                embedding_dim = len(embedding_list)
                if embedding_dim != self._collection_vector_size:
                    raise ValueError(
                        f"Embedding dimension mismatch: model '{self.embed_model_name}' produces "
                        f"{embedding_dim}-dimensional embeddings, but collection '{self._collection_name}' "
                        f"requires {self._collection_vector_size}-dimensional vectors. "
                        f"Please update embeddings.vector_size_to_model mapping in config/settings.yaml "
                        f"to map vector_size {self._collection_vector_size} to the correct model."
                    )
            
            return embedding_list

        embedding_list = self.embedder.embed_query(query)
        
        # Validate embedding dimension for OpenAI embeddings too
        if self._collection_vector_size:
            embedding_dim = len(embedding_list)
            if embedding_dim != self._collection_vector_size:
                raise ValueError(
                    f"Embedding dimension mismatch: model '{self.embed_model_name}' produces "
                    f"{embedding_dim}-dimensional embeddings, but collection '{self._collection_name}' "
                    f"requires {self._collection_vector_size}-dimensional vectors."
                )
        
        return embedding_list

    def _rerank_documents(
        self,
        query: str,
        documents: List[Dict[str, any]],
        top_n: int,
    ) -> List[Dict[str, any]]:
        """Rerank documents using reranker model (CrossEncoder or BGE) from sentence-transformers."""
        if not self.reranker:
            logger.warning("Reranker not available, returning documents without reranking")
            return documents[:top_n]
        
        if len(documents) == 0:
            logger.warning("No documents to rerank")
            return documents
        
        # Even if we have fewer documents than top_n, we should still rerank them
        # to improve the ordering
        logger.debug(f"Reranking {len(documents)} documents (requested top_n={top_n})")
        
        # Log BEFORE reranking
        logger.info("=" * 80)
        logger.info("🔄 RERANKING: Before (Initial Retrieval Scores)")
        logger.info("=" * 80)
        logger.info(f"Query: {query}")
        logger.info(f"Retrieved {len(documents)} candidates, showing top {min(10, len(documents))}:")
        logger.info("-" * 80)
        
        for i, doc in enumerate(documents[:10], 1):
            title = doc.get("title", "Unknown")
            score = doc.get("score", 0.0)
            # Score interpretation
            if score >= 0.8:
                score_label = "Very High"
            elif score >= 0.7:
                score_label = "High"
            elif score >= 0.6:
                score_label = "Medium"
            elif score >= 0.5:
                score_label = "Low"
            else:
                score_label = "Very Low"
            
            logger.info(
                f"  {i:2d}. {title[:55]:<55} | "
                f"Relevance: {score:.4f} ({score_label})"
            )
        
        try:
            # Prepare query-document pairs for reranker
            texts = [
                doc.get("contextualized_text") or doc.get("text", "")
                for doc in documents
            ]
            
            # Reranker API: predict([query, text] pairs)
            pairs = [[query, text] for text in texts]
            logger.debug(f"Reranking {len(pairs)} query-document pairs with reranker model")
            
            scores = self.reranker.predict(pairs)
            
            # Normalize reranker scores to 0-1 range (rerankers can return scores in various ranges)
            # This ensures consistent score interpretation across different reranker models
            if len(scores) > 0:
                min_score = min(scores)
                max_score = max(scores)
                score_range = max_score - min_score
                
                if score_range > 0:
                    # Min-max normalization: (score - min) / (max - min)
                    normalized_scores = [(s - min_score) / score_range for s in scores]
                else:
                    # All scores are the same, set to 0.5 (medium relevance)
                    normalized_scores = [0.5] * len(scores)
            else:
                normalized_scores = []
            
            # Sort by reranking scores (using normalized scores for sorting)
            scored_docs = list(zip(documents, normalized_scores, scores))
            scored_docs.sort(key=lambda x: x[1], reverse=True)
            
            reranked_docs = []
            for doc, normalized_score, raw_rerank_score in scored_docs[:top_n]:
                doc_copy = doc.copy()
                # Preserve original Qdrant score for reference
                doc_copy["qdrant_score"] = doc.get("score", 0.0)  # Original Qdrant similarity score
                doc_copy["rerank_score"] = float(raw_rerank_score)  # Raw reranker score (for debugging)
                doc_copy["score"] = float(normalized_score)  # Use normalized reranker score (0-1) as primary
                reranked_docs.append(doc_copy)
            
            # Log AFTER reranking
            logger.info("=" * 80)
            logger.info("🔄 RERANKING: After (Reranker Scores - Normalized to 0-1)")
            logger.info("=" * 80)
            logger.info(f"Reranker model: {self.reranker_model}")
            logger.info(f"Top {len(reranked_docs)} results (reranked scores, normalized to 0-1):")
            logger.info("-" * 80)
            
            # Show comparison
            for i, doc in enumerate(reranked_docs[:10], 1):
                title = doc.get("title", "Unknown")
                normalized_score = doc.get("score", 0.0)  # This is now normalized reranker score (0-1)
                raw_rerank_score = doc.get("rerank_score", normalized_score)  # Raw reranker score
                qdrant_score = doc.get("qdrant_score", 0.0)  # Original Qdrant similarity score
                
                # Find original position
                original_idx = next(
                    (idx for idx, d in enumerate(documents) if d.get("id") == doc.get("id")),
                    i - 1
                )
                original_score = qdrant_score  # Use preserved Qdrant score
                
                score_change = normalized_score - original_score
                position_change = ""
                if original_idx != i - 1:
                    pos_delta = original_idx - (i - 1)
                    if pos_delta > 0:
                        position_change = f" | Moved up {pos_delta} positions ({original_idx + 1}→{i})"
                    else:
                        position_change = f" | Moved down {abs(pos_delta)} positions ({original_idx + 1}→{i})"
                else:
                    position_change = " | Position unchanged"
                
                change_symbol = "📈" if score_change > 0.01 else "📉" if score_change < -0.01 else "➡️"
                
                # Score interpretation (using normalized score)
                if normalized_score >= 0.8:
                    score_label = "Very High"
                elif normalized_score >= 0.7:
                    score_label = "High"
                elif normalized_score >= 0.6:
                    score_label = "Medium"
                elif normalized_score >= 0.5:
                    score_label = "Low"
                else:
                    score_label = "Very Low"
                
                logger.info(
                    f"  {i:2d}. {title[:45]:<45} | "
                    f"Relevance: {normalized_score:.4f} ({score_label}) [Qdrant: {qdrant_score:.4f}, Rerank: {raw_rerank_score:.2f}]"
                )
                logger.info(
                    f"      └─ Qdrant: {original_score:.4f} → Reranker: {normalized_score:.4f} "
                    f"({change_symbol} {score_change:+.4f}){position_change}"
                )
            
            logger.info("=" * 80)
            logger.debug(f"Reranked {len(documents)} documents to top {len(reranked_docs)}")
            return reranked_docs
            
        except Exception as e:
            logger.warning(f"Reranking failed: {e}, returning original results")
            import traceback
            logger.debug(traceback.format_exc())
            return documents[:top_n]

    def _hybrid_search(
        self,
        query: str,
        query_vector: List[float],
        limit: int,
        filters: Optional[Dict[str, any]] = None,
    ) -> List[any]:
        """Perform hybrid search (semantic + keyword) using Qdrant."""
        if not self.hybrid_search_enabled:
            # Fallback to pure semantic search
            return self.qdrant.search(
                query_vector=query_vector,
                limit=limit,
                filters=filters,
            )
        
        try:
            # Step 1: Get semantic search results
            expanded_limit = int(limit * 1.5)  # Get more results for hybrid scoring
            
            semantic_results = self.qdrant.search(
                query_vector=query_vector,
                limit=expanded_limit,
                filters=filters,
            )
            
            # Log BEFORE hybrid search
            logger.info("=" * 80)
            logger.info("🔍 HYBRID SEARCH: Before (Semantic Only)")
            logger.info("=" * 80)
            logger.info(f"Query: {query}")
            logger.info(f"Retrieved {len(semantic_results)} candidates, showing top {min(10, len(semantic_results))}:")
            logger.info("-" * 80)
            for i, point in enumerate(semantic_results[:10], 1):
                payload = point.payload or {}
                title = payload.get("title") or payload.get("file_name", "Unknown")
                score = point.score
                # Score interpretation
                if score >= 0.8:
                    score_label = "Very High"
                elif score >= 0.7:
                    score_label = "High"
                elif score >= 0.6:
                    score_label = "Medium"
                elif score >= 0.5:
                    score_label = "Low"
                else:
                    score_label = "Very Low"
                
                logger.info(
                    f"  {i:2d}. {title[:55]:<55} | "
                    f"Relevance: {score:.4f} ({score_label})"
                )
            
            # Step 2: Apply keyword matching boost
            query_keywords = set(query.lower().split())
            scored_results = []
            
            for point in semantic_results:
                payload = point.payload or {}
                text = (payload.get("contextualized_text") or payload.get("text", "")).lower()
                
                # Count keyword matches
                text_words = set(text.split())
                keyword_matches = len(query_keywords.intersection(text_words))
                keyword_score = keyword_matches / max(len(query_keywords), 1)
                
                # Combine semantic and keyword scores
                semantic_score = point.score
                hybrid_score = (
                    self.hybrid_alpha * semantic_score +
                    (1 - self.hybrid_alpha) * keyword_score
                )
                
                # Create a simple object that mimics ScoredPoint structure
                # Instead of creating a new ScoredPoint (which has strict validation),
                # we'll create a simple object with the same interface
                class HybridScoredPoint:
                    """Simple wrapper that mimics ScoredPoint interface."""
                    def __init__(self, original_point: Any, new_score: float):
                        self.id = original_point.id
                        self.score = new_score
                        self.payload = original_point.payload
                        self.vector = getattr(original_point, 'vector', None)
                        self.version = getattr(original_point, 'version', None)
                
                hybrid_point = HybridScoredPoint(point, hybrid_score)
                scored_results.append(hybrid_point)
            
            # Sort by hybrid score and return top_k
            scored_results.sort(key=lambda x: x.score, reverse=True)
            final_results = scored_results[:limit]
            
            # Log AFTER hybrid search
            logger.info("=" * 80)
            logger.info("🔍 HYBRID SEARCH: After (Semantic + Keyword)")
            logger.info("=" * 80)
            logger.info(f"Hybrid alpha: {self.hybrid_alpha:.1%} semantic + {1-self.hybrid_alpha:.1%} keyword")
            logger.info(f"Query keywords: {', '.join(query_keywords)}")
            logger.info(f"Top {len(final_results)} results (hybrid scores):")
            logger.info("-" * 80)
            
            # Show comparison for top results
            for i, hybrid_point in enumerate(final_results[:10], 1):
                payload = hybrid_point.payload or {}
                title = payload.get("title") or payload.get("file_name", "Unknown")
                
                # Find original semantic score
                original_score = next(
                    (p.score for p in semantic_results if p.id == hybrid_point.id),
                    hybrid_point.score
                )
                
                # Calculate keyword score
                text = (payload.get("contextualized_text") or payload.get("text", "")).lower()
                text_words = set(text.split())
                keyword_matches = len(query_keywords.intersection(text_words))
                keyword_score = keyword_matches / max(len(query_keywords), 1)
                
                # Calculate hybrid components
                semantic_component = self.hybrid_alpha * original_score
                keyword_component = (1 - self.hybrid_alpha) * keyword_score
                hybrid_score = hybrid_point.score
                
                score_change = hybrid_score - original_score
                change_symbol = "📈" if score_change > 0.01 else "📉" if score_change < -0.01 else "➡️"
                
                # Find position change
                original_pos = next(
                    (idx + 1 for idx, p in enumerate(semantic_results) if p.id == hybrid_point.id),
                    i
                )
                pos_change = ""
                if original_pos != i:
                    pos_change = f" | Pos: {original_pos}→{i}"
                
                # Score interpretation
                if hybrid_score >= 0.8:
                    score_label = "Very High"
                elif hybrid_score >= 0.7:
                    score_label = "High"
                elif hybrid_score >= 0.6:
                    score_label = "Medium"
                elif hybrid_score >= 0.5:
                    score_label = "Low"
                else:
                    score_label = "Very Low"
                
                logger.info(
                    f"  {i:2d}. {title[:45]:<45} | "
                    f"Relevance: {hybrid_score:.4f} ({score_label})"
                )
                logger.info(
                    f"      └─ Semantic: {original_score:.4f} ({semantic_component:.4f}) + "
                    f"Keyword: {keyword_score:.4f} ({keyword_component:.4f}) = "
                    f"{hybrid_score:.4f} {change_symbol} {score_change:+.4f} | "
                    f"Matches: {keyword_matches}/{len(query_keywords)}{pos_change}"
                )
            
            logger.info("=" * 80)
            
            return final_results
            
        except Exception as e:
            logger.warning(f"Hybrid search failed: {e}, falling back to semantic search")
            return self.qdrant.search(
                query_vector=query_vector,
                limit=limit,
                filters=filters,
            )

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, str]] = None,
        use_reranking: Optional[bool] = None,
        use_hybrid: Optional[bool] = None,
        auto_extract_filters: Optional[bool] = None,
    ) -> List[Dict[str, any]]:
        """Retrieve top chunks with optional reranking and hybrid search.
        
        Args:
            query: Search query
            top_k: Number of results to return (after reranking if enabled)
            filters: Metadata filters (if None and auto_extract_filters=True, will extract from query)
            use_reranking: Override reranking setting (default: from config)
            use_hybrid: Override hybrid search setting (default: from config)
            auto_extract_filters: Automatically extract filters from query if filters is None
        
        Returns:
            List of documents with scores (reranked if enabled)
        """
        # ====================================================================
        # SMART METADATA FILTERING: Extract and apply intelligent filters
        # ====================================================================
        filters_source = None
        original_filters = filters
        qdrant_filters = None
        
        # Use config default if auto_extract_filters is None
        use_filtering = auto_extract_filters if auto_extract_filters is not None else self.metadata_filtering_enabled
        
        if filters is None and use_filtering:
            # Extract filters from query using smart metadata extractor
            qdrant_filters = self.smart_metadata_extractor.get_qdrant_filters(query)
            if qdrant_filters:
                filters_source = "smart-extracted"
                logger.info(f"Smart filters applied: {qdrant_filters}")
        
        if filters is not None and original_filters is None:
            # Filters were auto-extracted
            filters_source = "auto-extracted"
        elif filters is not None:
            # Filters were provided explicitly
            filters_source = "explicit"
        
        # Log metadata filtering status (only if filtering is enabled)
        if use_filtering:
            logger.info("=" * 80)
            logger.info("🔍 METADATA FILTERING")
            logger.info("=" * 80)
            logger.info(f"Query: {query}")
            # Show both qdrant_filters and filters if they exist
            active_filters = qdrant_filters or filters
            if active_filters:
                logger.info(f"✅ Filters ACTIVE: {active_filters}")
                logger.info(f"   Source: {filters_source}")
                if qdrant_filters:
                    logger.info(f"   Type: Smart Qdrant filters (will be used for search)")
                else:
                    logger.info(f"   Type: Simple metadata filters (will be used for search)")
                logger.info(f"   Effect: Search will be limited to matching metadata")
            else:
                logger.info("❌ Filters INACTIVE: No metadata filters applied")
                logger.info("   Effect: Search across all documents (all missions)")
            logger.info("=" * 80)
        else:
            logger.info("=" * 80)
            logger.info("🔍 METADATA FILTERING: DISABLED")
            logger.info("=" * 80)
        
        # Determine final top_k for initial retrieval
        final_top_k = top_k or self.top_k_default
        
        # If reranking enabled, retrieve more candidates first
        if use_reranking if use_reranking is not None else self.reranker_enabled:
            initial_limit = max(final_top_k, self.rerank_top_n * 2)  # Get more for reranking
        else:
            initial_limit = final_top_k
        
        query_vector = self._embed_query(query)
        logger.debug(f"Searching with vector size: {len(query_vector)}, limit: {initial_limit}")
        
        # Perform search (hybrid or semantic)
        use_hybrid_search = use_hybrid if use_hybrid is not None else self.hybrid_search_enabled
        
        # Use smart Qdrant filters if available, otherwise convert simple filters
        search_filters = qdrant_filters if qdrant_filters else filters
        
        # Perform initial search with filters
        if use_hybrid_search:
            results = self._hybrid_search(
                query=query,
                query_vector=query_vector,
                limit=initial_limit,
                filters=search_filters,
            )
        else:
            # Pure semantic search without hybrid logs
            logger.info("=" * 80)
            logger.info("🔍 SEMANTIC SEARCH ONLY")
            logger.info("=" * 80)
            results = self.qdrant.search(
                query_vector=query_vector,
                limit=initial_limit,
                filters=search_filters,
            )
        
        # Fallback: If filters returned 0 results, retry without filters
        if len(results) == 0 and search_filters:
            logger.warning(f"⚠️  Filtered search returned 0 results. Retrying without filters...")
            logger.warning(f"   Original filters: {search_filters}")
            if use_hybrid_search:
                results = self._hybrid_search(
                    query=query,
                    query_vector=query_vector,
                    limit=initial_limit,
                    filters=None,  # Retry without filters
                )
            else:
                results = self.qdrant.search(
                    query_vector=query_vector,
                    limit=initial_limit,
                    filters=None,  # Retry without filters
                )
            if len(results) > 0:
                logger.info(f"✅ Fallback search found {len(results)} documents (filters were too restrictive)")
                # Mark that we're using fallback results
                filters_source = "fallback-no-filters"

        # Convert to documents
        documents: List[Dict[str, any]] = []
        mission_counts = {}
        for point in results:
            payload = point.payload or {}
            mission = payload.get("mission", "Unknown")
            mission_counts[mission] = mission_counts.get(mission, 0) + 1
            
            documents.append(
                {
                    "id": point.id,
                    "score": point.score,
                    "text": payload.get("text", ""),
                    "contextualized_text": payload.get("contextualized_text", ""),
                    "title": payload.get("title") or payload.get("file_name") or payload.get("mission", "Unknown"),
                    "url": payload.get("url") or payload.get("source", ""),
                    "heading": payload.get("heading_path") or payload.get("heading", ""),
                    "metadata": payload,
                }
            )
        
        # Apply smart metadata boosting
        if documents and filters_source == "smart-extracted":
            logger.info("🚀 Applying smart metadata boosting...")
            documents = self.smart_metadata_extractor.enhance_results(query, documents)
        
        # Log retrieval results with metadata breakdown
        logger.info("=" * 80)
        logger.info("📊 RETRIEVAL RESULTS")
        logger.info("=" * 80)
        logger.info(f"Total documents retrieved: {len(documents)}")
        if mission_counts:
            logger.info("Documents by mission:")
            for mission, count in sorted(mission_counts.items(), key=lambda x: x[1], reverse=True):
                logger.info(f"  - {mission}: {count} document(s)")
        
        # Show if filters were effective
        if filters:
            expected_mission = filters.get("mission")
            if expected_mission:
                actual_missions = set(mission_counts.keys())
                if expected_mission in actual_missions and len(actual_missions) == 1:
                    logger.info(f"✅ Filter effective: All results from {expected_mission} (as expected)")
                elif expected_mission in actual_missions:
                    logger.warning(f"⚠️  Filter partially effective: Expected only {expected_mission}, but found: {actual_missions}")
                else:
                    logger.error(f"❌ Filter ineffective: Expected {expected_mission}, but found: {actual_missions}")
        
        # Show if comparative response might be needed
        if not filters and len(mission_counts) > 1:
            missions_list = ", ".join(sorted(mission_counts.keys()))
            logger.info(f"💡 Multiple missions detected ({missions_list}): Comparative response recommended")
        
        logger.info("=" * 80)

        # Apply reranking if enabled
        use_rerank = use_reranking if use_reranking is not None else self.reranker_enabled
        # When reranking is enabled, use rerank_top_n instead of final_top_k
        # This ensures we only return the top reranked documents, not all retrieved ones
        return_limit = self.rerank_top_n if use_rerank and self.reranker else final_top_k
        logger.debug(
            f"Reranking check: use_rerank={use_rerank}, "
            f"reranker_loaded={self.reranker is not None}, "
            f"documents_count={len(documents)}, "
            f"final_top_k={final_top_k}, "
            f"rerank_top_n={self.rerank_top_n}, "
            f"return_limit={return_limit}"
        )
        if use_rerank and self.reranker and len(documents) > 0:
            logger.info(f"🔄 Applying reranking to {len(documents)} documents (returning top {return_limit})")
            # Rerank all documents, then take rerank_top_n (not final_top_k)
            documents = self._rerank_documents(
                query=query,
                documents=documents,
                top_n=return_limit,
            )
        else:
            # Just take top_k without reranking
            if use_rerank and not self.reranker:
                logger.warning("Reranking enabled but reranker not loaded, skipping reranking")
            elif use_rerank and len(documents) == 0:
                logger.warning("Reranking enabled but no documents to rerank")
            else:
                logger.debug(f"Skipping reranking, returning top {return_limit} documents")
            documents = documents[:return_limit]

        return documents

    async def retrieve_async(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, str]] = None,
        use_reranking: Optional[bool] = None,
        use_hybrid: Optional[bool] = None,
        auto_extract_filters: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """Async version of retrieve() - runs in thread pool to avoid blocking event loop.

        This method is identical to retrieve() but runs asynchronously, allowing
        other requests to be processed while waiting for model inference.

        Use this in async endpoints to prevent blocking the event loop during:
        - Embedding generation (~50-200ms)
        - Vector search (~10-50ms)
        - Reranking (~100-500ms for 20 documents)

        Args:
            query: Search query
            top_k: Number of results to return (after reranking if enabled)
            filters: Metadata filters (if None and auto_extract_filters=True, will extract from query)
            use_reranking: Override reranking setting (default: from config)
            use_hybrid: Override hybrid search setting (default: from config)
            auto_extract_filters: Automatically extract filters from query if filters is None

        Returns:
            List of documents with scores (reranked if enabled)

        Example:
            >>> # In async endpoint
            >>> async def query_endpoint(query: str):
            ...     retriever = AdvancedRetriever()
            ...     docs = await retriever.retrieve_async(query, top_k=5)
            ...     return {"results": docs}
        """
        import asyncio

        # Run the blocking retrieve() in thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,  # Use default executor
            lambda: self.retrieve(
                query=query,
                top_k=top_k,
                filters=filters,
                use_reranking=use_reranking,
                use_hybrid=use_hybrid,
                auto_extract_filters=auto_extract_filters,
            ),
        )


__all__ = ["AdvancedRetriever"]

