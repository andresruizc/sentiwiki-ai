"""Security utilities for input validation and sanitization.

This module provides security-focused utilities to prevent common
vulnerabilities like path traversal, injection attacks, and other
input-based exploits.

Usage:
    from src.utils.security import validate_path, sanitize_filename

    # Validate a user-provided path
    safe_path = validate_path(user_input, allowed_dirs=[settings.data_dir])

    # Sanitize a filename
    safe_name = sanitize_filename(user_filename)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Sequence

from src.utils.exceptions import PathTraversalError, ValidationError


def validate_path(
    path_str: str,
    allowed_dirs: Optional[Sequence[Path | str]] = None,
    must_exist: bool = True,
) -> Path:
    """Validate and resolve a path, preventing directory traversal attacks.

    This function:
    1. Resolves the path to its absolute form (resolving symlinks and ..)
    2. Checks that the resolved path is within allowed directories
    3. Optionally checks that the path exists

    Args:
        path_str: The path string to validate (can be relative or absolute)
        allowed_dirs: List of allowed parent directories. If None, uses
                     current working directory.
        must_exist: If True, raises error if path doesn't exist

    Returns:
        Resolved Path object that is guaranteed to be safe

    Raises:
        PathTraversalError: If path is outside allowed directories
        ValidationError: If path is empty or doesn't exist when required

    Example:
        >>> from src.utils.config import get_settings
        >>> settings = get_settings()
        >>> safe_path = validate_path(
        ...     "/data/documents/report.pdf",
        ...     allowed_dirs=[settings.data_dir],
        ... )
    """
    if not path_str or not path_str.strip():
        raise ValidationError(
            field="path",
            message="Path cannot be empty",
            value=path_str,
        )

    # Convert to Path and resolve to absolute path
    # This resolves symlinks, .., and other path tricks
    path = Path(path_str).resolve()

    # Set up allowed directories
    if allowed_dirs is None:
        # Default to current working directory
        allowed_dirs = [Path.cwd()]
    else:
        # Convert all to resolved Path objects
        allowed_dirs = [Path(d).resolve() for d in allowed_dirs]

    # Check if path is within any allowed directory
    is_safe = any(
        _is_path_within(path, allowed_dir)
        for allowed_dir in allowed_dirs
    )

    if not is_safe:
        raise PathTraversalError(
            attempted_path=str(path),
            allowed_directories=[str(d) for d in allowed_dirs],
        )

    # Check existence if required
    if must_exist and not path.exists():
        raise ValidationError(
            field="path",
            message=f"Path does not exist: {path}",
            value=str(path),
        )

    return path


def _is_path_within(path: Path, parent: Path) -> bool:
    """Check if a path is within a parent directory.

    Uses Path.is_relative_to() which is safe against symlink attacks
    because we've already resolved both paths.

    Args:
        path: The path to check (must be resolved)
        parent: The parent directory (must be resolved)

    Returns:
        True if path is within parent, False otherwise
    """
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """Sanitize a filename to prevent path traversal and other attacks.

    This function:
    1. Removes path separators and traversal patterns
    2. Removes or replaces unsafe characters
    3. Limits length to prevent buffer overflows
    4. Handles edge cases (empty, only dots, etc.)

    Args:
        filename: The filename to sanitize
        max_length: Maximum allowed length (default: 255 for most filesystems)

    Returns:
        Safe filename string

    Raises:
        ValidationError: If filename is empty or would become empty after sanitization

    Example:
        >>> sanitize_filename("../../../etc/passwd")
        'etc_passwd'
        >>> sanitize_filename("report<2024>.pdf")
        'report_2024_.pdf'
    """
    if not filename:
        raise ValidationError(
            field="filename",
            message="Filename cannot be empty",
        )

    # Remove path separators and traversal patterns
    # This prevents ../../../etc/passwd type attacks
    name = filename.replace("/", "_").replace("\\", "_")
    name = name.replace("..", "_")

    # Remove null bytes (can truncate filenames in C-based systems)
    name = name.replace("\x00", "")

    # Remove or replace characters that are problematic on various filesystems
    # < > : " | ? * are forbidden on Windows
    # Control characters (0x00-0x1F) are problematic everywhere
    unsafe_pattern = r'[<>:"|?*\x00-\x1f]'
    name = re.sub(unsafe_pattern, "_", name)

    # Remove leading/trailing whitespace and dots (problematic on Windows)
    name = name.strip().strip(".")

    # Truncate to max length (preserving extension if possible)
    if len(name) > max_length:
        # Try to preserve extension
        parts = name.rsplit(".", 1)
        if len(parts) == 2 and len(parts[1]) < 10:  # Reasonable extension length
            ext = parts[1]
            base = parts[0][:max_length - len(ext) - 1]
            name = f"{base}.{ext}"
        else:
            name = name[:max_length]

    # Final check: name shouldn't be empty after sanitization
    if not name:
        raise ValidationError(
            field="filename",
            message="Filename is empty after sanitization",
            value=filename,
        )

    return name


def validate_query_input(query: str, max_length: int = 10000) -> str:
    """Validate and sanitize a query input.

    Args:
        query: The query string to validate
        max_length: Maximum allowed length

    Returns:
        Validated query string (trimmed)

    Raises:
        ValidationError: If query is empty, too long, or contains only whitespace
    """
    if not query:
        raise ValidationError(
            field="query",
            message="Query cannot be empty",
        )

    query = query.strip()

    if not query:
        raise ValidationError(
            field="query",
            message="Query cannot be only whitespace",
        )

    if len(query) > max_length:
        raise ValidationError(
            field="query",
            message=f"Query exceeds maximum length of {max_length} characters",
            value=f"(length: {len(query)})",
        )

    return query
