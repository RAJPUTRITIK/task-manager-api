"""Business logic. Sits between the interfaces (API/CLI) and the database."""

from .models import (DEFAULT_PRIORITY, STATUS_COMPLETED, STATUS_PENDING)
from .validators import ValidationError, validate_filters, validate_task_data

_DEFAULTS = {
    "description": "",
    "status": STATUS_PENDING,
    "priority": DEFAULT_PRIORITY,
    "due_date": None,
}


class NotFoundError(Exception):
    """Raised when a task id does not exist."""


class TaskService:
    """Use-cases of the application. Knows nothing about HTTP or terminals."""

    def __init__(self, repository):
        self.repository = repository

    def create_task(self, data):
        cleaned = validate_task_data(data, creating=True)
        return self.repository.create({**_DEFAULTS, **cleaned})

    def get_task(self, task_id):
        task = self.repository.get(task_id)
        if task is None:
            raise NotFoundError("Task %s not found" % task_id)
        return task

    def list_tasks(self, params=None):
        return self.repository.list(validate_filters(params or {}))

    def update_task(self, task_id, data, partial=True):
        """partial=True -> PATCH (only given fields).
        partial=False -> PUT (full replace; omitted fields reset to defaults).
        """
        cleaned = validate_task_data(data, partial=partial)
        if partial and not cleaned:
            raise ValidationError("No fields to update")
        fields = cleaned if partial else {**_DEFAULTS, **cleaned}
        task = self.repository.update(task_id, fields)
        if task is None:
            raise NotFoundError("Task %s not found" % task_id)
        return task

    def delete_task(self, task_id):
        if not self.repository.delete(task_id):
            raise NotFoundError("Task %s not found" % task_id)

    def set_completed(self, task_id, completed):
        """Mark complete/incomplete. Safe to call repeatedly (idempotent)."""
        status = STATUS_COMPLETED if completed else STATUS_PENDING
        return self.update_task(task_id, {"status": status}, partial=True)
