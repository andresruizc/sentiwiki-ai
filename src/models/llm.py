"""LLM-related models."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from src.models.enums import LLMProvider


class LLMMetrics(BaseModel):
    """Metrics for LLM usage and costs."""
    model: str = Field(..., description="Model identifier")
    provider: Optional[LLMProvider] = Field(None, description="LLM provider")
    temperature: float = Field(default=0.0, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: int = Field(default=1024, gt=0, description="Maximum tokens to generate")
    prompt_tokens: Optional[int] = Field(None, ge=0, description="Tokens in prompt")
    completion_tokens: Optional[int] = Field(None, ge=0, description="Tokens in completion")
    total_tokens: Optional[int] = Field(None, ge=0, description="Total tokens used")
    cost: Optional[float] = Field(None, ge=0.0, description="Total cost in USD")
    cost_per_1k_tokens: Optional[float] = Field(None, ge=0.0, description="Cost per 1K tokens")
    duration_seconds: Optional[float] = Field(None, ge=0.0, description="Duration of request")

    @field_validator('temperature')
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        """Ensure temperature is in valid range."""
        if not 0.0 <= v <= 2.0:
            raise ValueError("Temperature must be between 0.0 and 2.0")
        return v


class LLMCompletionParams(BaseModel):
    """Parameters for LLM completion requests."""
    model: str = Field(..., description="Model identifier")
    messages: List[Dict[str, Any]] = Field(..., description="Conversation messages")
    temperature: float = Field(default=0.0, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: int = Field(default=1024, gt=0, description="Maximum tokens to generate")
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0, description="Nucleus sampling parameter")
    stop: Optional[List[str]] = Field(None, description="Stop sequences")
    stream: bool = Field(default=False, description="Stream response")

    @field_validator('temperature')
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        """Ensure temperature is in valid range."""
        if not 0.0 <= v <= 2.0:
            raise ValueError("Temperature must be between 0.0 and 2.0")
        return v
