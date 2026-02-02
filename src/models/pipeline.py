"""Pipeline-related models."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.models.enums import PipelineStep


class PipelineStatus(BaseModel):
    """Status of a data processing pipeline job."""
    job_id: str = Field(..., description="Unique job identifier")
    status: str = Field(default="queued", description="Current pipeline status")
    current_step: Optional[PipelineStep] = Field(None, description="Current processing step")
    progress: float = Field(default=0.0, ge=0.0, le=100.0, description="Progress percentage")
    started_at: Optional[datetime] = Field(None, description="Job start time")
    completed_at: Optional[datetime] = Field(None, description="Job completion time")
    error: Optional[str] = Field(None, description="Error message if failed")
    steps_completed: List[str] = Field(default_factory=list, description="Completed steps")
    stats: Dict[str, Any] = Field(default_factory=dict, description="Pipeline statistics")
    logs: List[str] = Field(default_factory=list, description="Processing logs")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with formatted output."""
        return {
            "job_id": self.job_id,
            "status": self.status,
            "current_step": self.current_step.value if self.current_step else None,
            "progress": f"{self.progress:.1f}%",
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": (
                (self.completed_at or datetime.now()) - self.started_at
            ).total_seconds() if self.started_at else None,
            "error": self.error,
            "steps_completed": self.steps_completed,
            "stats": self.stats,
        }

    def add_log(self, message: str) -> None:
        """Add a log message."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.logs.append(f"[{timestamp}] {message}")
