"""Custom exceptions for the RAG application.

This module defines a hierarchy of exceptions that provide:
- Clear error categorization for different failure modes
- Structured error information for debugging
- HTTP status code mapping for API responses
- Consistent error handling patterns across the codebase

Exception Hierarchy:
    RAGException (base)
    ├── ConfigurationError - Invalid configuration or missing settings
    ├── SecurityError - Security-related violations
    │   └── PathTraversalError - Attempted path traversal attack
    ├── RetrievalError - Document retrieval failures
    │   ├── EmbeddingError - Embedding generation failures
    │   └── RerankingError - Reranking failures (non-critical)
    ├── LLMError - LLM-related failures
    │   ├── LLMRateLimitError - Rate limit exceeded
    │   └── LLMTimeoutError - LLM request timeout
    └── ValidationError - Input validation failures
"""

from __future__ import annotations

from typing import Any, Optional


class RAGException(Exception):
    """Base exception for all RAG application errors.

    Attributes:
        message: Human-readable error description
        details: Additional context for debugging
        http_status: Suggested HTTP status code for API responses
    """

    http_status: int = 500

    def __init__(
        self,
        message: str,
        details: Optional[dict[str, Any]] = None,
        http_status: Optional[int] = None,
    ) -> None:
        self.message = message
        self.details = details or {}
        if http_status is not None:
            self.http_status = http_status
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for JSON serialization."""
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
        }


# ===== CONFIGURATION ERRORS =====

class ConfigurationError(RAGException):
    """Raised when configuration is invalid or missing."""

    http_status = 500


# ===== SECURITY ERRORS =====

class SecurityError(RAGException):
    """Base class for security-related errors."""

    http_status = 403


class PathTraversalError(SecurityError):
    """Raised when a path traversal attack is detected.

    This occurs when user input attempts to access files
    outside of allowed directories (e.g., using ../ sequences).
    """

    http_status = 400

    def __init__(
        self,
        attempted_path: str,
        allowed_directories: Optional[list[str]] = None,
    ) -> None:
        details = {
            "attempted_path": attempted_path,
            "allowed_directories": allowed_directories or [],
        }
        super().__init__(
            message=f"Path not allowed: {attempted_path}",
            details=details,
        )


# ===== RETRIEVAL ERRORS =====

class RetrievalError(RAGException):
    """Base class for retrieval-related errors."""

    http_status = 500


class EmbeddingError(RetrievalError):
    """Raised when embedding generation fails."""

    def __init__(
        self,
        message: str = "Failed to generate embeddings",
        query: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        details = {}
        if query:
            details["query_length"] = len(query)
        if model:
            details["model"] = model
        super().__init__(message=message, details=details)


class RerankingError(RetrievalError):
    """Raised when reranking fails (non-critical, can fallback).

    This error indicates degraded results but not a complete failure.
    The system should fallback to non-reranked results.
    """

    http_status = 200  # Still return results, just degraded

    def __init__(
        self,
        message: str = "Reranking failed, using original ranking",
        original_error: Optional[Exception] = None,
    ) -> None:
        details = {}
        if original_error:
            details["original_error"] = str(original_error)
        super().__init__(message=message, details=details)


# ===== LLM ERRORS =====

class LLMError(RAGException):
    """Base class for LLM-related errors."""

    http_status = 503


class LLMRateLimitError(LLMError):
    """Raised when LLM rate limit is exceeded."""

    http_status = 429

    def __init__(
        self,
        provider: str,
        retry_after: Optional[int] = None,
    ) -> None:
        details = {"provider": provider}
        if retry_after:
            details["retry_after_seconds"] = retry_after
        super().__init__(
            message=f"Rate limit exceeded for {provider}",
            details=details,
        )


class LLMTimeoutError(LLMError):
    """Raised when LLM request times out."""

    http_status = 504

    def __init__(
        self,
        provider: str,
        timeout_seconds: float,
    ) -> None:
        super().__init__(
            message=f"LLM request timed out after {timeout_seconds}s",
            details={
                "provider": provider,
                "timeout_seconds": timeout_seconds,
            },
        )


# ===== VALIDATION ERRORS =====

class ValidationError(RAGException):
    """Raised when input validation fails."""

    http_status = 400

    def __init__(
        self,
        field: str,
        message: str,
        value: Optional[Any] = None,
    ) -> None:
        details = {"field": field}
        if value is not None:
            # Don't include full value to avoid logging sensitive data
            details["value_type"] = type(value).__name__
        super().__init__(
            message=f"Validation error for '{field}': {message}",
            details=details,
        )


# ===== UTILITY FUNCTIONS =====

def handle_exception_for_api(exc: Exception) -> tuple[int, dict[str, Any]]:
    """Convert any exception to an API response tuple.

    Args:
        exc: The exception to handle

    Returns:
        Tuple of (http_status_code, error_dict)
    """
    if isinstance(exc, RAGException):
        return exc.http_status, exc.to_dict()

    # Unknown exceptions get 500
    return 500, {
        "error": "InternalError",
        "message": str(exc),
        "details": {},
    }
