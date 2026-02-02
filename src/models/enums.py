"""Enums for the ESA IAGen project."""

from enum import Enum


class DistanceMetric(str, Enum):
    """Vector distance metrics for Qdrant."""
    COSINE = "Cosine"
    EUCLID = "Euclid"
    DOT = "Dot"


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    GROQ = "groq"
    TOGETHER = "together"
    OPENROUTER = "openrouter"
    OLLAMA = "ollama"


class PipelineStep(str, Enum):
    """Pipeline processing steps."""
    SCRAPING = "scraping"
    ENHANCING = "enhancing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INGESTION = "ingestion"
    COMPLETED = "completed"
    FAILED = "failed"


class PipelineStatusType(str, Enum):
    """Pipeline status types."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
