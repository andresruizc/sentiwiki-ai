"""Shared Pydantic models for the ESA IAGen project.

This package provides validated data models organized by domain:
- enums: Enumeration types
- agent: Agent state models
- pipeline: Pipeline processing models
- llm: LLM metrics and configuration models
- retrieval: Document and retrieval models
- qdrant: Qdrant vector database models
"""

# Enums
from src.models.enums import (
    DistanceMetric,
    LLMProvider,
    PipelineStep,
    PipelineStatusType,
)

# Agent models
from src.models.agent import AgentState

# Pipeline models
from src.models.pipeline import PipelineStatus

# LLM models
from src.models.llm import LLMCompletionParams, LLMMetrics

# Retrieval models
from src.models.retrieval import (
    DocumentChunk,
    DocumentMetadata,
    GroupedSource,
    HeadingWithUrl,
    RetrievalConfig,
)

# Qdrant models
from src.models.qdrant import QdrantCollectionConfig, QdrantCollectionInfo

__all__ = [
    # Enums
    "DistanceMetric",
    "LLMProvider",
    "PipelineStep",
    "PipelineStatusType",
    # Agent
    "AgentState",
    # Pipeline
    "PipelineStatus",
    # LLM
    "LLMMetrics",
    "LLMCompletionParams",
    # Retrieval
    "DocumentMetadata",
    "DocumentChunk",
    "HeadingWithUrl",
    "GroupedSource",
    "RetrievalConfig",
    # Qdrant
    "QdrantCollectionConfig",
    "QdrantCollectionInfo",
]
