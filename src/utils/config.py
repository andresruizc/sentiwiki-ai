"""Configuration management using Pydantic settings."""

import os
from pathlib import Path
from typing import List, Literal, Optional, Dict, Any

import yaml
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class QdrantSettings(BaseSettings):
    """Qdrant vector database settings."""

    model_config = SettingsConfigDict(
        extra="ignore",
        env_prefix="QDRANT__",  # Read QDRANT__HOST, QDRANT__PORT from env
    )

    host: str = "localhost"
    port: int = 6333
    collection_name: str = "sentiwiki_docs"
    vector_size: int = 3072
    distance: Literal["Cosine", "Euclid", "Dot"] = "Cosine"
    on_disk_payload: bool = True

    @field_validator('port')
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Ensure port is in valid range."""
        if not 1 <= v <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v

    @field_validator('collection_name')
    @classmethod
    def validate_collection_name(cls, v: str) -> str:
        """Ensure collection name is valid."""
        if not v or not v.strip():
            raise ValueError("Collection name cannot be empty")
        # Qdrant collection names should be alphanumeric with underscores/hyphens
        if not all(c.isalnum() or c in ('_', '-') for c in v):
            raise ValueError("Collection name must contain only alphanumeric characters, underscores, or hyphens")
        return v.strip()

    @field_validator('vector_size')
    @classmethod
    def validate_vector_size(cls, v: int) -> int:
        """Ensure vector size is positive."""
        if v <= 0:
            raise ValueError("Vector size must be positive")
        return v


class EmbeddingsSettings(BaseSettings):
    """Embeddings model settings."""

    model_config = SettingsConfigDict(extra="ignore")

    provider: Literal["openai", "huggingface"] = "huggingface"
    model: str = "BAAI/bge-large-en-v1.5"
    dimension: int = 3072
    batch_size: int = 100
    # Mapping of vector sizes to embedding models (for collections with different embedding sizes)
    # Format: {vector_size: model_name}
    # Example: {384: "BAAI/bge-small-en-v1.5", 1024: "BAAI/bge-large-en-v1.5"}
    vector_size_to_model: Optional[Dict[int, str]] = None

    @field_validator('dimension')
    @classmethod
    def validate_dimension(cls, v: int) -> int:
        """Ensure dimension is positive."""
        if v <= 0:
            raise ValueError("Embedding dimension must be positive")
        return v

    @field_validator('batch_size')
    @classmethod
    def validate_batch_size(cls, v: int) -> int:
        """Ensure batch size is positive."""
        if v <= 0:
            raise ValueError("Batch size must be positive")
        return v

    @field_validator('model')
    @classmethod
    def validate_model(cls, v: str) -> str:
        """Ensure model name is not empty."""
        if not v or not v.strip():
            raise ValueError("Model name cannot be empty")
        return v.strip()


class LLMConfig(BaseSettings):
    """Individual LLM configuration."""

    model_config = SettingsConfigDict(extra="ignore")

    provider: str = "anthropic"  # Supports any LiteLLM provider: openai, anthropic, google, cohere, etc.
    model: str = "claude-3-haiku-20240307"
    temperature: float = 0.1
    max_tokens: int = 4096
    streaming: bool = True
    prompt_caching: bool = False  # Enable prompt caching for faster responses (only supported for Anthropic)

    @field_validator('temperature')
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        """Ensure temperature is in valid range."""
        if not 0.0 <= v <= 2.0:
            raise ValueError("Temperature must be between 0.0 and 2.0")
        return v

    @field_validator('max_tokens')
    @classmethod
    def validate_max_tokens(cls, v: int) -> int:
        """Ensure max_tokens is positive."""
        if v <= 0:
            raise ValueError("max_tokens must be positive")
        return v

    @field_validator('provider', 'model')
    @classmethod
    def validate_not_empty(cls, v: str) -> str:
        """Ensure string fields are not empty."""
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()


class LLMSettings(BaseSettings):
    """LLM settings with separate configs for router, RAG, and direct."""

    model_config = SettingsConfigDict(extra="ignore")

    # Default/fallback LLM
    provider: str = "anthropic"  # Supports any LiteLLM provider: openai, anthropic, google, cohere, etc.
    model: str = "claude-3-haiku-20240307"
    temperature: float = 0.1
    max_tokens: int = 4096
    streaming: bool = True
    prompt_caching: bool = False  # Enable prompt caching for faster responses (only supported for Anthropic)

    # Separate LLM configs for different paths
    router: Optional[LLMConfig] = None
    rag: Optional[LLMConfig] = None
    direct: Optional[LLMConfig] = None
    eval_llm: Optional[LLMConfig] = None  # LLM config for RAGAS evaluation

    @field_validator('temperature')
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        """Ensure temperature is in valid range."""
        if not 0.0 <= v <= 2.0:
            raise ValueError("Temperature must be between 0.0 and 2.0")
        return v

    @field_validator('max_tokens')
    @classmethod
    def validate_max_tokens(cls, v: int) -> int:
        """Ensure max_tokens is positive."""
        if v <= 0:
            raise ValueError("max_tokens must be positive")
        return v

    @field_validator('provider', 'model')
    @classmethod
    def validate_not_empty(cls, v: str) -> str:
        """Ensure string fields are not empty."""
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()


class RetrievalSettings(BaseSettings):
    """Retrieval settings."""

    model_config = SettingsConfigDict(extra="ignore")

    top_k: int = 20
    rerank_top_n: int = 5
    hybrid_search_enabled: bool = True
    hybrid_search_alpha: float = 0.7
    reranker_model: str = "ms-marco-MiniLM-L-12-v2"
    reranker_enabled: bool = True
    metadata_filtering_enabled: bool = True  # CRITICAL: Enabled to ensure mission-specific queries filter correctly (e.g., Sentinel-1 vs Sentinel-2)

    @field_validator('top_k')
    @classmethod
    def validate_top_k(cls, v: int) -> int:
        """Ensure top_k is positive and reasonable."""
        if v <= 0:
            raise ValueError("top_k must be positive")
        if v > 1000:
            raise ValueError("top_k should not exceed 1000 for performance reasons")
        return v

    @field_validator('rerank_top_n')
    @classmethod
    def validate_rerank_top_n(cls, v: int) -> int:
        """Ensure rerank_top_n is positive."""
        if v <= 0:
            raise ValueError("rerank_top_n must be positive")
        return v

    @field_validator('hybrid_search_alpha')
    @classmethod
    def validate_alpha(cls, v: float) -> float:
        """Ensure alpha is between 0 and 1."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("hybrid_search_alpha must be between 0.0 and 1.0")
        return v

    @model_validator(mode='after')
    def validate_rerank_not_greater_than_top_k(self) -> 'RetrievalSettings':
        """Ensure rerank_top_n doesn't exceed top_k."""
        if self.rerank_top_n > self.top_k:
            raise ValueError(f"rerank_top_n ({self.rerank_top_n}) cannot exceed top_k ({self.top_k})")
        return self


class DoclingSettings(BaseSettings):
    """Docling processing settings."""
    
    model_config = SettingsConfigDict(extra="ignore")
    
    extract_tables: bool = True
    extract_images: bool = False
    ocr_enabled: bool = True


class ParsingSettings(BaseSettings):
    """Document parsing settings."""

    model_config = SettingsConfigDict(extra="ignore")

    docling: DoclingSettings = Field(default_factory=DoclingSettings)
    chunk_size: int = 512
    chunk_overlap: int = 50

    @field_validator('chunk_size')
    @classmethod
    def validate_chunk_size(cls, v: int) -> int:
        """Ensure chunk size is positive and reasonable."""
        if v <= 0:
            raise ValueError("chunk_size must be positive")
        if v > 10000:
            raise ValueError("chunk_size should not exceed 10000 for performance reasons")
        return v

    @field_validator('chunk_overlap')
    @classmethod
    def validate_chunk_overlap(cls, v: int) -> int:
        """Ensure chunk overlap is non-negative."""
        if v < 0:
            raise ValueError("chunk_overlap must be non-negative")
        return v

    @model_validator(mode='after')
    def validate_overlap_not_greater_than_size(self) -> 'ParsingSettings':
        """Ensure chunk_overlap doesn't exceed chunk_size."""
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(f"chunk_overlap ({self.chunk_overlap}) must be less than chunk_size ({self.chunk_size})")
        return self


class LangSmithSettings(BaseSettings):
    """LangSmith monitoring settings."""
    
    model_config = SettingsConfigDict(extra="ignore")
    
    enabled: bool = True
    api_key: Optional[str] = None  # Set via LANGSMITH_API_KEY or LANGCHAIN_API_KEY env var
    project_name: str = "ecss-standards-agent"
    tracing: bool = True


class AgentSettings(BaseSettings):
    """Agent settings."""

    model_config = SettingsConfigDict(extra="ignore")

    max_iterations: int = 5
    enable_reasoning_trace: bool = True
    router_prompt: str = ""
    direct_llm_system_prompt: str = ""
    decompose_prompt: str = ""
    grade_documents_prompt: str = ""
    rewrite_question_prompt: str = ""
    # Relevance threshold for document grading (0.0-1.0)
    # Documents with top_3_avg_score >= threshold are considered relevant
    relevance_threshold: float = 0.5
    langsmith: LangSmithSettings = Field(default_factory=LangSmithSettings)

    @field_validator('max_iterations')
    @classmethod
    def validate_max_iterations(cls, v: int) -> int:
        """Ensure max_iterations is positive and reasonable."""
        if v <= 0:
            raise ValueError("max_iterations must be positive")
        if v > 100:
            raise ValueError("max_iterations should not exceed 100 to prevent infinite loops")
        return v

    @field_validator('relevance_threshold')
    @classmethod
    def validate_relevance_threshold(cls, v: float) -> float:
        """Ensure relevance_threshold is between 0 and 1."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("relevance_threshold must be between 0.0 and 1.0")
        return v


class RateLimitSettings(BaseSettings):
    """Rate limiting settings."""

    model_config = SettingsConfigDict(extra="ignore")

    requests_per_minute: int = 60

    @field_validator('requests_per_minute')
    @classmethod
    def validate_requests_per_minute(cls, v: int) -> int:
        """Ensure requests_per_minute is positive."""
        if v <= 0:
            raise ValueError("requests_per_minute must be positive")
        return v


class APISettings(BaseSettings):
    """API settings."""

    model_config = SettingsConfigDict(extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: List[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)

    @field_validator('port')
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Ensure port is in valid range."""
        if not 1 <= v <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v

    @field_validator('host')
    @classmethod
    def validate_host(cls, v: str) -> str:
        """Ensure host is not empty."""
        if not v or not v.strip():
            raise ValueError("Host cannot be empty")
        return v.strip()


class LoggingSettings(BaseSettings):
    """Logging preferences."""

    model_config = SettingsConfigDict(extra="ignore")

    level: str = "INFO"
    format: Literal["text", "json"] = "text"


class PromptSettings(BaseSettings):
    """Prompt templates settings."""
    
    model_config = SettingsConfigDict(extra="ignore")
    
    rag_system_base: str = """You are an expert assistant for Copernicus Sentinel Missions documentation (SentiWiki).
Answer questions based on the provided context from SentiWiki documentation.

IMPORTANT: Always attempt to answer the question using the provided context. The context documents have been retrieved as potentially relevant to the question. Even if the relevance is not perfect, extract and synthesize information from the context to provide the best possible answer.

Only say you couldn't find information if the context is completely unrelated to the question. Otherwise, use the context to provide a helpful answer, even if it's partial or requires inference.

Format your response in a clear and structured way. Be precise and factual. When referencing specific Sentinel missions, always include the mission identifier (e.g., Sentinel-1, Sentinel-2, Sentinel-3, Sentinel-5P).

Context:
{context}"""
    
    rag_comparative_instruction: str = """

IMPORTANT: The context contains information from multiple Sentinel missions ({standards_list}).
- If the question is generic (doesn't specify a mission), provide a COMPARATIVE response that distinguishes between the different missions.
- Example: "Sentinel-1 uses SAR imaging, while Sentinel-2 uses multi-spectral optical imaging."
- Do NOT assume a single mission unless the question explicitly mentions one.
- Clearly label which information belongs to which mission."""


class ObservabilitySettings(BaseSettings):
    """Top-level observability settings."""

    model_config = SettingsConfigDict(extra="ignore")

    logging: LoggingSettings = Field(default_factory=LoggingSettings)


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    # API Keys
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Component settings
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    embeddings: EmbeddingsSettings = Field(default_factory=EmbeddingsSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    parsing: ParsingSettings = Field(default_factory=ParsingSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    api: APISettings = Field(default_factory=APISettings)
    prompts: PromptSettings = Field(default_factory=PromptSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)

    # Paths
    project_root: Path = Field(default_factory=lambda: Path(__file__).parent.parent.parent)
    data_dir: Path = Field(default_factory=lambda: Path(__file__).parent.parent.parent / "data")
    config_dir: Path = Field(
        default_factory=lambda: Path(__file__).parent.parent.parent / "config"
    )

    # Logging
    log_level: str = "INFO"

    @classmethod
    def load_from_yaml(cls, yaml_path: Path) -> "Settings":
        """Load settings from YAML file.
        
        Environment variables override YAML values for nested settings.
        """
        with open(yaml_path) as f:
            config_dict = yaml.safe_load(f)

        # Flatten nested config
        settings_dict = {}
        if "qdrant" in config_dict:
            # Create QdrantSettings - check environment variables first
            qdrant_dict = config_dict["qdrant"].copy()
            # Override with environment variables if they exist
            if "QDRANT__HOST" in os.environ:
                qdrant_dict["host"] = os.environ["QDRANT__HOST"]
            if "QDRANT__PORT" in os.environ:
                qdrant_dict["port"] = int(os.environ["QDRANT__PORT"])
            if "QDRANT__COLLECTION_NAME" in os.environ:
                qdrant_dict["collection_name"] = os.environ["QDRANT__COLLECTION_NAME"]
            settings_dict["qdrant"] = QdrantSettings(**qdrant_dict)
        if "embeddings" in config_dict:
            embeddings_dict = config_dict["embeddings"].copy()
            # Handle vector_size_to_model mapping if present
            if "vector_size_to_model" in embeddings_dict:
                # Convert keys to int if they're strings (YAML might parse as strings)
                vector_size_map = embeddings_dict["vector_size_to_model"]
                if isinstance(vector_size_map, dict):
                    embeddings_dict["vector_size_to_model"] = {
                        int(k): v for k, v in vector_size_map.items()
                    }
            settings_dict["embeddings"] = EmbeddingsSettings(**embeddings_dict)
        if "llm" in config_dict:
            llm_dict = config_dict["llm"].copy()
            # Handle nested LLM configs (router, rag, direct)
            if "router" in llm_dict:
                llm_dict["router"] = LLMConfig(**llm_dict["router"])
            if "rag" in llm_dict:
                llm_dict["rag"] = LLMConfig(**llm_dict["rag"])
            if "direct" in llm_dict:
                llm_dict["direct"] = LLMConfig(**llm_dict["direct"])
            settings_dict["llm"] = LLMSettings(**llm_dict)
        if "retrieval" in config_dict:
            retrieval_dict = config_dict["retrieval"]
            if "hybrid_search" in retrieval_dict:
                retrieval_dict["hybrid_search_enabled"] = retrieval_dict["hybrid_search"]["enabled"]
                retrieval_dict["hybrid_search_alpha"] = retrieval_dict["hybrid_search"]["alpha"]
            if "reranker" in retrieval_dict:
                retrieval_dict["reranker_model"] = retrieval_dict["reranker"]["model"]
                retrieval_dict["reranker_enabled"] = retrieval_dict["reranker"]["enabled"]
            settings_dict["retrieval"] = RetrievalSettings(**retrieval_dict)
        if "parsing" in config_dict:
            parsing_dict = config_dict["parsing"].copy()
            if "docling" in parsing_dict:
                parsing_dict["docling"] = DoclingSettings(**parsing_dict["docling"])
            settings_dict["parsing"] = ParsingSettings(**parsing_dict)
        if "agent" in config_dict:
            agent_dict = config_dict["agent"].copy()
            if "langsmith" in agent_dict:
                agent_dict["langsmith"] = LangSmithSettings(**agent_dict["langsmith"])
            settings_dict["agent"] = AgentSettings(**agent_dict)
        if "api" in config_dict:
            api_dict = config_dict["api"].copy()
            if "rate_limit" in api_dict:
                api_dict["rate_limit"] = RateLimitSettings(**api_dict["rate_limit"])
            # Override CORS origins from environment variable if set
            if "API__CORS_ORIGINS" in os.environ:
                cors_origins_str = os.environ["API__CORS_ORIGINS"]
                # Support comma-separated list
                api_dict["cors_origins"] = [origin.strip() for origin in cors_origins_str.split(",")]
            settings_dict["api"] = APISettings(**api_dict)
        if "prompts" in config_dict:
            settings_dict["prompts"] = PromptSettings(**config_dict["prompts"])
        if "observability" in config_dict:
            settings_dict["observability"] = ObservabilitySettings(**config_dict["observability"])

        return cls(**settings_dict)


# Global settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create settings instance."""
    global _settings
    if _settings is None:
        config_path = Path(__file__).parent.parent.parent / "config" / "settings.yaml"
        if config_path.exists():
            _settings = Settings.load_from_yaml(config_path)
        else:
            _settings = Settings()
    return _settings


# Convenience function
settings = get_settings()

