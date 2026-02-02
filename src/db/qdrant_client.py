"""Qdrant client wrapper."""

from typing import Any, Dict, List, Optional

from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    NearestQuery,
    PointStruct,
    ScoredPoint,
    VectorParams,
)

from src.utils.config import get_settings


class QdrantManager:
    """Manager for Qdrant vector database operations."""

    def __init__(
        self,
        collection_name: Optional[str] = None,
        distance: Optional[str] = None,
    ) -> None:
        """Initialize Qdrant client."""
        self.settings = get_settings()
        self.client = QdrantClient(
            host=self.settings.qdrant.host,
            port=self.settings.qdrant.port,
        )
        self.collection_name = collection_name or self.settings.qdrant.collection_name
        self.distance = distance or self.settings.qdrant.distance

    def create_collection(
        self,
        recreate: bool = False,
        vector_size: Optional[int] = None,
        distance: Optional[str] = None,
    ) -> None:
        """Create collection if it doesn't exist.

        Args:
            recreate: If True, delete and recreate collection
            vector_size: Size of embedding vectors
            distance: Distance metric name
        """
        if recreate and self.client.collection_exists(self.collection_name):
            logger.info(f"Deleting existing collection: {self.collection_name}")
            self.client.delete_collection(self.collection_name)

        if not self.client.collection_exists(self.collection_name):
            logger.info(f"Creating collection: {self.collection_name}")

            distance_map = {
                "Cosine": Distance.COSINE,
                "Euclid": Distance.EUCLID,
                "Dot": Distance.DOT,
            }

            size = vector_size or self.settings.qdrant.vector_size
            metric = distance or self.distance

            if size is None:
                raise ValueError(
                    "vector_size must be provided either via settings or argument"
                )

            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=size,
                    distance=distance_map[metric],
                ),
            )
            logger.info(f"Collection {self.collection_name} created successfully")
        else:
            logger.info(f"Collection {self.collection_name} already exists")

    def insert_documents(
        self,
        documents: List[Dict[str, Any]],
        embeddings: List[List[float]],
    ) -> None:
        """Insert documents with embeddings.

        Args:
            documents: List of document dictionaries
            embeddings: List of embedding vectors
        """
        if len(documents) != len(embeddings):
            raise ValueError("Number of documents must match number of embeddings")

        points = []
        for idx, (doc, embedding) in enumerate(zip(documents, embeddings)):
            point = PointStruct(
                id=idx,
                vector=embedding,
                payload={
                    "text": doc.get("text", ""),
                    "contextualized_text": doc.get("contextualized_text", ""),
                    **doc.get("metadata", {}),
                },
            )
            points.append(point)

        # Insert in batches
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            self.client.upsert(collection_name=self.collection_name, points=batch)
            logger.info(f"Inserted batch {i // batch_size + 1}/{(len(points) + batch_size - 1) // batch_size}")

        logger.info(f"Successfully inserted {len(points)} documents")

    def search(
        self,
        query_vector: List[float],
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[ScoredPoint]:
        """Search for similar documents.

        Args:
            query_vector: Query embedding vector
            limit: Maximum number of results
            filters: Optional metadata filters

        Returns:
            List of scored search results
        """
        query_filter = None
        if filters:
            conditions = []
            for key, value in filters.items():
                conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))
            query_filter = Filter(must=conditions)

        # Try the simplest approach: use search method directly if available
        if hasattr(self.client, 'search'):
            try:
                results = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=query_vector,
                    limit=limit,
                    query_filter=query_filter,
                )
                return results if isinstance(results, list) else list(results)
            except Exception as e:
                logger.debug(f"Direct search method failed: {e}, trying query_points")
        
        # Fallback: use query_points with proper Query construction
        try:
            from qdrant_client.models import Query
            # NearestQuery needs 'nearest' parameter (the vector itself)
            nearest = NearestQuery(nearest=query_vector)
            # Query wraps NearestQuery with filter and top
            # Construct as dict first, then convert to Query
            query_data = {"nearest": nearest}
            if query_filter:
                query_data["filter"] = query_filter
            if limit:
                query_data["top"] = limit
            
            # Try to use query_points with the dict structure
            # Qdrant's query_points might accept dict directly
            try:
                results = self.client.query_points(
                    collection_name=self.collection_name,
                    query=query_data,  # type: ignore
                )
                return results.points if hasattr(results, 'points') else results
            except (TypeError, AttributeError, ValueError):
                # If dict doesn't work, we need to construct Query properly
                # Query is a Union type, so we construct it from the dict
                # Using model_validate if available (Pydantic v2)
                try:
                    query = Query.model_validate(query_data)  # type: ignore
                except (AttributeError, ValueError):
                    # Fallback: construct manually using the Union members
                    # Since Query is Union[NearestQuery, ...], we pass NearestQuery directly
                    # But we need filter and top, so we use query_points with separate params
                    results = self.client.query_points(
                        collection_name=self.collection_name,
                        query=nearest,  # type: ignore
                        limit=limit,
                        query_filter=query_filter,
                    )
                    return results.points if hasattr(results, 'points') else results
                else:
                    results = self.client.query_points(
                        collection_name=self.collection_name,
                        query=query,
                    )
                    return results.points if hasattr(results, 'points') else results
        except Exception as final_error:
            logger.error(f"All search methods failed. Last error: {final_error}")
            raise

    def get_collection_info(self) -> Dict[str, Any]:
        """Get collection information.

        Returns:
            Dictionary with collection stats
        """
        info = self.client.get_collection(self.collection_name)
        result = {
            "status": getattr(info, "status", "unknown"),
        }
        if hasattr(info, "points_count"):
            result["points_count"] = info.points_count
        if hasattr(info, "vectors_count"):
            result["vectors_count"] = info.vectors_count
        if hasattr(info, "vectors"):
            result["vectors"] = info.vectors
        if hasattr(info, "config"):
            result["config"] = info.config
        return result

    def get_collection_vector_size(self) -> Optional[int]:
        """Get the vector size of the current collection.

        Returns:
            Vector size (dimension) of the collection, or None if not found
        """
        try:
            info = self.client.get_collection(self.collection_name)
            
            # Try multiple ways to access vector size
            # Method 1: Direct access via config.params.vectors.size
            if hasattr(info, "config") and info.config:
                config = info.config
                
                # Handle config as object
                if hasattr(config, "params"):
                    params = config.params
                    if hasattr(params, "vectors"):
                        vectors = params.vectors
                        # Handle both single vector config and named vectors
                        if hasattr(vectors, "size"):
                            return vectors.size
                        elif isinstance(vectors, dict):
                            # Named vectors case - get first vector config
                            for vector_config in vectors.values():
                                if hasattr(vector_config, "size"):
                                    return vector_config.size
                
                # Method 2: Try accessing as dict (if config is dict-like)
                if isinstance(config, dict):
                    params = config.get("params", {})
                    vectors = params.get("vectors")
                    if vectors:
                        if isinstance(vectors, dict):
                            # Check if it's a single vector config with 'size' key
                            if "size" in vectors:
                                return vectors["size"]
                            # Or named vectors - get first vector config
                            for vector_config in vectors.values():
                                if isinstance(vector_config, dict) and "size" in vector_config:
                                    return vector_config["size"]
                        elif hasattr(vectors, "size"):
                            return vectors.size
            
            # Method 3: Try accessing via get_collection_info (which might have different structure)
            collection_info = self.get_collection_info()
            config_dict = collection_info.get("config")
            if config_dict:
                if isinstance(config_dict, dict):
                    params = config_dict.get("params", {})
                    vectors = params.get("vectors")
                    if vectors and isinstance(vectors, dict):
                        if "size" in vectors:
                            return vectors["size"]
                        # Named vectors
                        for vector_config in vectors.values():
                            if isinstance(vector_config, dict) and "size" in vector_config:
                                return vector_config["size"]
            
            return None
        except Exception as e:
            logger.warning(f"Failed to get vector size for collection {self.collection_name}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None

