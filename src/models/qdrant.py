"""Qdrant-related models."""

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from src.models.enums import DistanceMetric


class QdrantCollectionConfig(BaseModel):
    """Qdrant collection configuration."""
    name: str = Field(..., min_length=1, description="Collection name")
    distance: DistanceMetric = Field(default=DistanceMetric.COSINE, description="Distance metric")
    vector_size: int = Field(default=1024, gt=0, description="Vector dimension size")
    on_disk: bool = Field(default=False, description="Store vectors on disk")

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure collection name is valid."""
        if not v or not v.strip():
            raise ValueError("Collection name cannot be empty")
        # Qdrant collection names should be alphanumeric with underscores/hyphens
        if not all(c.isalnum() or c in ('_', '-') for c in v):
            raise ValueError("Collection name must contain only alphanumeric characters, underscores, or hyphens")
        return v.strip()


class QdrantCollectionInfo(BaseModel):
    """Information about a Qdrant collection."""
    name: str = Field(..., description="Collection name")
    vectors_count: int = Field(default=0, ge=0, description="Number of vectors")
    indexed_vectors_count: int = Field(default=0, ge=0, description="Number of indexed vectors")
    points_count: int = Field(default=0, ge=0, description="Number of points")
    segments_count: int = Field(default=0, ge=0, description="Number of segments")
    config: Optional[QdrantCollectionConfig] = Field(None, description="Collection configuration")
    status: str = Field(default="unknown", description="Collection status")
