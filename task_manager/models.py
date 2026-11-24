"""Domain model and shared constants for tasks."""

from dataclasses import asdict, dataclass
from typing import Optional

STATUS_PENDING = "pending"
STATUS_COMPLETED = "completed"
STATUSES = (STATUS_PENDING, STATUS_COMPLETED)

PRIORITIES = ("low", "medium", "high")
DEFAULT_PRIORITY = "medium"

DATE_FORMAT = "%Y-%m-%d"


@dataclass
class Task:
    """A single task as stored in the database."""

    id: int
    title: str
    description: str
    status: str
    priority: str
    created_at: str
    due_date: Optional[str]

    def to_dict(self):
        """Return a JSON-serialisable dictionary."""
        return asdict(self)
