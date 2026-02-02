"""Agent-related models."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class AgentState(BaseModel):
    """State for the routing agent."""
    # Core fields
    query: str = Field(..., min_length=1, description="User query")
    route: Optional[str] = Field(None, description="Routing decision (RAG, DIRECT, etc.)")
    answer: str = Field(default="", description="Generated answer")
    sources: List[Dict[str, Any]] = Field(default_factory=list, description="Formatted source documents")
    context: str = Field(default="", description="Retrieved context for generation")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    # Agentic RAG fields
    retrieved_docs: List[Dict[str, Any]] = Field(default_factory=list, description="Raw retrieved documents")
    rewritten_query: Optional[str] = Field(None, description="Rewritten query for better retrieval")
    grade_score: Optional[str] = Field(None, description="Document relevance grade (yes/no)")
    rewrite_attempted: bool = Field(default=False, description="Whether query rewrite was attempted")

    # Relevance scoring fields (from retrieval scores)
    relevance_avg_score: Optional[float] = Field(None, description="Average relevance score")
    relevance_top_score: Optional[float] = Field(None, description="Top relevance score")
    relevance_top_5_avg: Optional[float] = Field(None, description="Average of top 5 scores")

    # Query decomposition fields
    sub_queries: Optional[List[str]] = Field(None, description="Decomposed sub-queries for complex questions")

    @field_validator('query')
    @classmethod
    def validate_query(cls, v: str) -> str:
        """Ensure query is not empty."""
        if not v or not v.strip():
            raise ValueError("Query cannot be empty")
        return v.strip()

    # Support dictionary-style access for LangGraph compatibility
    def __getitem__(self, key: str) -> Any:
        """Allow dict-style access: state['key']."""
        return getattr(self, key)

    def __setitem__(self, key: str, value: Any) -> None:
        """Allow dict-style assignment: state['key'] = value."""
        setattr(self, key, value)

    def get(self, key: str, default: Any = None) -> Any:
        """Allow dict.get() style access."""
        return getattr(self, key, default)

    def keys(self):
        """Return field names for dict-like iteration."""
        return self.model_fields.keys()

    def __iter__(self):
        """Allow iteration over field names."""
        return iter(self.model_fields.keys())

    def items(self):
        """Return (key, value) pairs for dict-like iteration."""
        return ((key, getattr(self, key)) for key in self.model_fields.keys())

    # Allow arbitrary types for backward compatibility with LangGraph
    model_config = {"arbitrary_types_allowed": True}
