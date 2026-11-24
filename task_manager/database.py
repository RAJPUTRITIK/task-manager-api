"""SQLite persistence layer (standard-library ``sqlite3``)."""

import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime

from .models import Task

DEFAULT_DB_PATH = os.environ.get("TASKS_DB", "tasks.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'completed')),
    priority    TEXT NOT NULL DEFAULT 'medium'
                CHECK (priority IN ('low', 'medium', 'high')),
    created_at  TEXT NOT NULL,
    due_date    TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks (status);
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks (due_date);
"""

_PRIORITY_RANK = ("CASE priority WHEN 'high' THEN 3 "
                  "WHEN 'medium' THEN 2 ELSE 1 END")

# {d} is replaced by ASC / DESC. Column names are never taken from user input.
_SORT_SQL = {
    "id": "id {d}",
    "created_at": "created_at {d}",
    "title": "title COLLATE NOCASE {d}",
    "priority": _PRIORITY_RANK + " {d}",
    "due_date": "due_date IS NULL, due_date {d}",  # tasks without date last
}

_UPDATABLE_COLUMNS = ("title", "description", "status", "priority", "due_date")


class TaskRepository:
    """All SQL lives here. Returns ``Task`` objects, never raw rows."""

    def __init__(self, db_path=DEFAULT_DB_PATH):
        self.db_path = db_path
        self._init_schema()

    @contextmanager
    def _connection(self):
        # A new connection per operation keeps us safe with the threaded
        # HTTP server (sqlite3 connections must not be shared across threads).
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self):
        with self._connection() as conn:
            conn.executescript(_SCHEMA)

    @staticmethod
    def _to_task(row):
        return Task(**dict(row))

    def create(self, fields):
        created_at = datetime.now().replace(microsecond=0).isoformat()
        with self._connection() as conn:
            cursor = conn.execute(
                "INSERT INTO tasks (title, description, status, priority, "
                "created_at, due_date) VALUES (?, ?, ?, ?, ?, ?)",
                (fields["title"], fields["description"], fields["status"],
                 fields["priority"], created_at, fields["due_date"]))
            task_id = cursor.lastrowid
        return self.get(task_id)

    def get(self, task_id):
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return self._to_task(row) if row else None

    def list(self, filters):
        clauses, params = [], []
        today = date.today().isoformat()

        if "status" in filters:
            clauses.append("status = ?")
            params.append(filters["status"])
        if "priority" in filters:
            clauses.append("priority = ?")
            params.append(filters["priority"])
        if "search" in filters:
            clauses.append("(title LIKE ? OR description LIKE ?)")
            like = "%" + filters["search"] + "%"
            params.extend([like, like])
        if "overdue" in filters:
            overdue_sql = ("(status = 'pending' AND due_date IS NOT NULL "
                           "AND due_date < ?)")
            clauses.append(overdue_sql if filters["overdue"]
                           else "NOT " + overdue_sql)
            params.append(today)
        if "due_before" in filters:
            clauses.append("(due_date IS NOT NULL AND due_date <= ?)")
            params.append(filters["due_before"])
        if "due_after" in filters:
            clauses.append("(due_date IS NOT NULL AND due_date >= ?)")
            params.append(filters["due_after"])

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        direction = "DESC" if filters["order"] == "desc" else "ASC"
        order_by = _SORT_SQL[filters["sort_by"]].format(d=direction)
        sql = ("SELECT * FROM tasks%s ORDER BY %s, id ASC LIMIT ? OFFSET ?"
               % (where, order_by))
        params.extend([filters["limit"], filters["offset"]])

        with self._connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._to_task(row) for row in rows]

    def update(self, task_id, fields):
        """Update given columns. Returns the new Task, or None if missing."""
        columns = [name for name in fields if name in _UPDATABLE_COLUMNS]
        if columns:
            assignments = ", ".join("%s = ?" % name for name in columns)
            values = [fields[name] for name in columns] + [task_id]
            with self._connection() as conn:
                conn.execute(
                    "UPDATE tasks SET %s WHERE id = ?" % assignments, values)
        return self.get(task_id)

    def delete(self, task_id):
        with self._connection() as conn:
            cursor = conn.execute(
                "DELETE FROM tasks WHERE id = ?", (task_id,))
            return cursor.rowcount > 0
