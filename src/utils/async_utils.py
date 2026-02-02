"""Async utilities for running blocking operations in thread pool.

This module provides utilities to run blocking I/O operations (like model inference,
database queries, etc.) in a thread pool without blocking the async event loop.

Usage:
    from src.utils.async_utils import run_in_thread_pool

    async def my_endpoint():
        # Run blocking operation asynchronously
        result = await run_in_thread_pool(expensive_function, arg1, arg2)
"""

from __future__ import annotations

import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, TypeVar

from loguru import logger

# Type variable for generic return type
T = TypeVar("T")

# Global thread pool for CPU-bound and blocking I/O operations
# Size based on typical ML model workload (embeddings, reranking, LLM calls)
_thread_pool: ThreadPoolExecutor | None = None
_DEFAULT_MAX_WORKERS = 8  # Enough for concurrent requests without overwhelming CPU


def get_thread_pool() -> ThreadPoolExecutor:
    """Get or create the global thread pool.

    Returns:
        ThreadPoolExecutor instance for running blocking operations
    """
    global _thread_pool
    if _thread_pool is None:
        _thread_pool = ThreadPoolExecutor(
            max_workers=_DEFAULT_MAX_WORKERS,
            thread_name_prefix="async_worker_",
        )
        logger.info(f"Created thread pool with {_DEFAULT_MAX_WORKERS} workers for blocking operations")
    return _thread_pool


async def run_in_thread_pool(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run a blocking function in the thread pool without blocking event loop.

    This is the preferred way to run blocking operations (ML inference, file I/O,
    database queries) in async endpoints without blocking other requests.

    Args:
        func: The blocking function to run
        *args: Positional arguments for func
        **kwargs: Keyword arguments for func

    Returns:
        The result of func(*args, **kwargs)

    Example:
        >>> # In an async endpoint
        >>> async def query_endpoint(query: str):
        ...     # Run blocking retrieval asynchronously
        ...     docs = await run_in_thread_pool(retriever.retrieve, query)
        ...
        ...     # Run blocking LLM call asynchronously
        ...     answer = await run_in_thread_pool(llm.invoke, messages)
        ...
        ...     return {"answer": answer, "sources": docs}
    """
    loop = asyncio.get_event_loop()
    pool = get_thread_pool()

    # Use functools.partial to preserve function signature
    partial_func = functools.partial(func, *args, **kwargs)

    # Run in thread pool
    return await loop.run_in_executor(pool, partial_func)


def shutdown_thread_pool(wait: bool = True) -> None:
    """Shutdown the global thread pool.

    Args:
        wait: If True, wait for all pending tasks to complete

    Note:
        This should be called during application shutdown.
    """
    global _thread_pool
    if _thread_pool is not None:
        logger.info("Shutting down async thread pool...")
        _thread_pool.shutdown(wait=wait)
        _thread_pool = None
        logger.success("Thread pool shut down successfully")


__all__ = [
    "run_in_thread_pool",
    "get_thread_pool",
    "shutdown_thread_pool",
]
