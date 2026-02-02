"""Logging configuration using loguru."""

import sys
from datetime import datetime
from pathlib import Path

from loguru import logger

from src.utils.config import get_settings

# Track if logger has been initialized to avoid multiple setups
_logger_initialized = False


def setup_logger(force: bool = False) -> None:
    """Configure application logger.
    
    Args:
        force: If True, reinitialize even if already initialized (default: False)
    """
    global _logger_initialized
    
    # Skip if already initialized (unless forced)
    if _logger_initialized and not force:
        return
    
    settings = get_settings()

    # Remove default handler and any existing handlers
    logger.remove()

    # Get log level from settings (default to INFO if not set)
    log_level = getattr(settings, 'log_level', 'INFO')
    if hasattr(settings, 'logging') and hasattr(settings.logging, 'level'):
        log_level = settings.logging.level

    # Console handler (INFO level for cleaner terminal output)
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=log_level,
        colorize=True,
    )

    # File handler (DEBUG level to capture all logs including debug logs)
    log_dir = settings.project_root / "logs"
    log_dir.mkdir(exist_ok=True)

    # Use dynamic filename with date pattern (loguru will create files like esa_iagen_2026-01-05.log)
    log_file_pattern = str(log_dir / "esa_iagen_{time:YYYY-MM-DD}.log")
    logger.add(
        log_file_pattern,
        rotation="00:00",
        retention="30 days",
        level="DEBUG",  # Always write DEBUG level to file, regardless of console level
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        enqueue=True,  # Thread-safe logging
        serialize=False,  # Write as text, not JSON
        backtrace=True,  # Include stack trace in exceptions
        diagnose=True,  # Include variable values in exceptions
    )

    # Get actual log file name for today (for the message)
    today_log_file = log_dir / f"esa_iagen_{datetime.now().strftime('%Y-%m-%d')}.log"
    
    _logger_initialized = True
    logger.info(f"✅ Logger initialized - Console level: {log_level}, File level: DEBUG")
    logger.info(f"📁 Log file: {today_log_file} (pattern: esa_iagen_YYYY-MM-DD.log)")
    logger.info(f"📁 Log directory: {log_dir.absolute()}")


def setup_logging(log_dir: Path = None, name: str = "") -> None:
    """
    Configure logging to console and file.
    
    This function is used by CLI scripts and components that need their own log files.
    It does NOT remove existing handlers, so it can be used alongside setup_logger().
    
    Args:
        log_dir: Directory for log files (default: logs/)
        name: Name prefix for the log file (e.g., "chunker" -> "chunker_2026-01-05.log")
    """
    log_dir = log_dir or Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # DON'T remove existing handlers - just add new ones for this component
    # This allows multiple log files (main app + component-specific)
    
    # Add console handler (colorful, concise) - only if not already added
    # Check if we already have a stderr handler
    has_stderr = any(
        getattr(h, 'sink', None) == sys.stderr 
        for h in logger._core.handlers.values()
    )
    if not has_stderr:
        logger.add(
            sys.stderr,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
            level="INFO",
            colorize=True,
        )
    
    # Add file handler (detailed, with rotation) for this component
    log_file = log_dir / f"{name}_{datetime.now().strftime('%Y-%m-%d')}.log"

    # For LLM cost tracking, keep this file focused ONLY on cost-related records
    if name == "llm_costs":
        def _llm_cost_filter(record):
            # Only include records explicitly tagged as LLM cost logs
            return bool(record["extra"].get("llm_cost"))

        logger.add(
            log_file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            level="DEBUG",
            rotation="10 MB",
            retention="30 days",
            compression="zip",
            enqueue=True,
            filter=_llm_cost_filter,
        )
    else:
        logger.add(
            log_file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            level="DEBUG",
            rotation="10 MB",
            retention="30 days",
            compression="zip",
            enqueue=True,  # Thread-safe logging
        )
    
    logger.info(f"Component logging initialized - Log file: {log_file}")



# Initialize logger on import
setup_logger()

