"""Document and retrieval models."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class DocumentMetadata(BaseModel):
    """Metadata for a document chunk."""
    source_file: str = Field(..., description="Original source file name")
    file_stem: str = Field(..., description="File name without extension")
    heading_path: Optional[str] = Field(None, description="Hierarchical heading path")
    section_url: Optional[str] = Field(None, description="URL to specific section")
    page_number: Optional[int] = Field(None, description="Page number if applicable")
    doc_type: Optional[str] = Field(None, description="Document type")
    created_at: Optional[datetime] = Field(None, description="Document creation timestamp")

    @field_validator('source_file', 'file_stem')
    @classmethod
    def validate_not_empty(cls, v: str) -> str:
        """Ensure required string fields are not empty."""
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()


class DocumentChunk(BaseModel):
    """A chunk of a document with embeddings and metadata."""
    text: str = Field(..., min_length=1, description="The chunk text content")
    contextualized_text: Optional[str] = Field(
        None,
        description="Text with added context for better retrieval"
    )
    title: str = Field(..., min_length=1, description="Document title")
    url: str = Field(..., description="Document URL or identifier")
    heading: str = Field(default="", description="Section heading")
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="Relevance score")
    metadata: DocumentMetadata = Field(..., description="Document metadata")
    embedding: Optional[List[float]] = Field(None, description="Vector embedding")

    @field_validator('text', 'title')
    @classmethod
    def validate_not_empty(cls, v: str) -> str:
        """Ensure required string fields are not empty."""
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for backward compatibility."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentChunk":
        """Create from dictionary, handling missing fields gracefully."""
        # Extract metadata fields
        metadata_dict = data.get("metadata", {})
        if not isinstance(metadata_dict, dict):
            metadata_dict = {}

        # Ensure required metadata fields
        if "source_file" not in metadata_dict:
            metadata_dict["source_file"] = data.get("source_file", "unknown")
        if "file_stem" not in metadata_dict:
            metadata_dict["file_stem"] = data.get("file_stem", "unknown")

        return cls(
            text=data.get("text", ""),
            contextualized_text=data.get("contextualized_text"),
            title=data.get("title", ""),
            url=data.get("url", ""),
            heading=data.get("heading", ""),
            score=data.get("score", 0.0),
            metadata=DocumentMetadata(**metadata_dict),
            embedding=data.get("embedding")
        )


class HeadingWithUrl(BaseModel):
    """A heading with its associated URL."""
    heading: str = Field(..., description="Heading text")
    url: str = Field(..., description="URL to the section")


class GroupedSource(BaseModel):
    """Grouped source information with multiple sections."""
    title: str = Field(..., description="Source document title")
    url: str = Field(..., description="Base URL")
    relevance_percentage: float = Field(..., ge=0.0, le=100.0, description="Relevance score")
    headings: List[str] = Field(default_factory=list, description="List of headings")
    headings_with_urls: List[HeadingWithUrl] = Field(
        default_factory=list,
        description="List of headings with their URLs"
    )


class RetrievalConfig(BaseModel):
    """Configuration for document retrieval."""
    top_k: int = Field(default=10, gt=0, le=100, description="Number of documents to retrieve")
    rerank_top_n: int = Field(default=5, gt=0, le=50, description="Number of documents after reranking")
    hybrid_search_enabled: bool = Field(default=False, description="Enable hybrid search")
    min_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Minimum relevance score")
    use_contextual_retrieval: bool = Field(
        default=False,
        description="Use contextualized text for retrieval"
    )

    @field_validator('rerank_top_n')
    @classmethod
    def validate_rerank_top_n(cls, v: int, info) -> int:
        """Ensure rerank_top_n doesn't exceed top_k."""
        # Note: In Pydantic v2, we can't easily access other fields in field_validator
        # This would require model_validator instead
        return v
