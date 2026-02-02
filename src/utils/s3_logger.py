"""S3 Logger for RAG queries and responses."""
import gzip
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from threading import Lock

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    ClientError = None

from loguru import logger


class S3QueryLogger:
    """Async logger for RAG queries to S3.
    
    Buffers queries in memory and flushes to S3 periodically.
    Uses gzip compression to reduce storage costs.
    """
    
    def __init__(
        self,
        bucket_name: Optional[str] = None,
        region: str = "eu-north-1",
        buffer_size: int = 10,
        enabled: bool = True,
    ):
        """Initialize S3 logger.
        
        Args:
            bucket_name: S3 bucket name (defaults to env var or None)
            region: AWS region
            buffer_size: Number of queries to buffer before flushing
            enabled: Whether logging is enabled
        """
        self.enabled = enabled and boto3 is not None
        
        if not self.enabled:
            if not boto3:
                logger.warning("boto3 not installed, S3 logging disabled")
            return
        
        # Get bucket name from env or parameter
        self.bucket_name = bucket_name or os.getenv("S3_BUCKET_NAME")
        if not self.bucket_name:
            logger.warning("S3_BUCKET_NAME not set, S3 logging disabled")
            self.enabled = False
            return
        
        self.region = region
        self.buffer_size = buffer_size
        self.buffer: List[Dict[str, Any]] = []
        self.lock = Lock()
        
        try:
            self.s3_client = boto3.client("s3", region_name=region)
            logger.info(f"✅ S3 logger initialized: s3://{self.bucket_name}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize S3 client: {e}")
            self.enabled = False
    
    def log_query(
        self,
        query_id: str,
        query: str,
        route: str,
        response: Dict[str, Any],
        metadata: Dict[str, Any],
        agent_state: Optional[Dict[str, Any]] = None,
    ):
        """Log a query/response to buffer.
        
        Args:
            query_id: Unique query identifier
            query: User query text
            route: Route decision (RAG, DIRECT, etc.)
            response: Response data (answer, sources, etc.)
            metadata: Query metadata (duration, tokens, cost, etc.)
            agent_state: Agent state (rewritten queries, grade scores, etc.)
        """
        if not self.enabled:
            return
        
        entry = {
            "query_id": query_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "query": query,
            "route": route,
            "response": response,
            "metadata": metadata,
            "agent_state": agent_state or {},
        }
        
        with self.lock:
            self.buffer.append(entry)
            
            if len(self.buffer) >= self.buffer_size:
                # Flush in background (non-blocking)
                try:
                    self._flush_sync()
                except Exception as e:
                    logger.error(f"❌ Failed to flush queries to S3: {e}")
    
    def _flush_sync(self):
        """Flush buffer to S3 synchronously."""
        if not self.buffer:
            return
        
        try:
            # Get current date for partitioning
            now = datetime.utcnow()
            date_path = f"year={now.year}/month={now.month:02d}/day={now.day:02d}"
            
            # Create JSONL content
            jsonl_content = "\n".join(json.dumps(entry) for entry in self.buffer)
            
            # Compress with gzip
            compressed = gzip.compress(jsonl_content.encode("utf-8"))
            
            # Upload to S3 (include timestamp with microseconds to avoid overwrites)
            unique_id = now.strftime('%Y-%m-%d_%H%M%S') + f"_{now.microsecond:06d}"
            key = f"query-history/{date_path}/queries_{unique_id}.jsonl.gz"
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=compressed,
                ContentType="application/gzip",
                ServerSideEncryption="AES256",
            )
            
            count = len(self.buffer)
            logger.info(f"📤 Flushed {count} queries to S3: s3://{self.bucket_name}/{key}")
            
            # Clear buffer
            self.buffer.clear()
            
        except ClientError as e:
            logger.error(f"❌ S3 upload failed: {e}")
            # Keep buffer for retry (in production, add retry logic)
        except Exception as e:
            logger.error(f"❌ Unexpected error flushing to S3: {e}")
    
    def flush(self):
        """Manually flush buffer to S3."""
        if not self.enabled:
            return
        
        with self.lock:
            self._flush_sync()
    
    def __del__(self):
        """Flush remaining buffer on destruction."""
        if self.enabled and self.buffer:
            try:
                self.flush()
            except Exception:
                pass  # Ignore errors during cleanup


# Global instance (singleton pattern)
_s3_logger_instance: Optional[S3QueryLogger] = None


def get_s3_logger() -> Optional[S3QueryLogger]:
    """Get or create global S3 logger instance."""
    global _s3_logger_instance
    
    if _s3_logger_instance is None:
        bucket_name = os.getenv("S3_BUCKET_NAME")
        region = os.getenv("AWS_REGION", "eu-north-1")
        enabled = os.getenv("S3_LOGGING_ENABLED", "true").lower() == "true"
        
        _s3_logger_instance = S3QueryLogger(
            bucket_name=bucket_name,
            region=region,
            buffer_size=int(os.getenv("S3_LOG_BUFFER_SIZE", "1")),  # Default to 1 for immediate writes
            enabled=enabled,
        )
    
    return _s3_logger_instance if _s3_logger_instance.enabled else None

