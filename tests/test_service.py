import os
import tempfile
import unittest
from datetime import date, timedelta

from task_manager.database import TaskRepository
from task_manager.service import NotFoundError, TaskService
from task_manager.validators import ValidationError


class ServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "test.db")
        self.service = TaskService(TaskRepository(self.db_path))

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_applies_defaults(self):
        task = self.service.create_task({"title": "  Write tests  "})
        self.assertEqual(task.title, "Write tests")
        self.assertEqual(task.status, "pending")
        self.assertEqual(task.priority, "medium")
        self.assertIsNone(task.due_date)

    def test_validation_errors(self):
        bad_inputs = [
            {},
            {"title": ""},
            {"title": "x" * 101},
            {"title": "ok", "priority": "urgent"},
            {"title": "ok", "status": "done"},
            {"title": "ok", "due_date": "31-12-2030"},
            {"title": "ok", "due_date": "2030-02-31"},
            {"title": "ok", "unknown": 1},
            {"title": 123},
        ]
        for data in bad_inputs:
            with self.subTest(data=data):
                with self.assertRaises(ValidationError):
                    self.service.create_task(data)

    def test_past_due_date_rejected_on_create(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        with self.assertRaises(ValidationError):
            self.service.create_task({"title": "t", "due_date": yesterday})

    def test_non_dict_body_rejected(self):
        with self.assertRaises(ValidationError):
            self.service.create_task(["title"])

    def test_persistence_between_restarts(self):
        self.service.create_task({"title": "persist me"})
        new_service = TaskService(TaskRepository(self.db_path))
        self.assertEqual(new_service.get_task(1).title, "persist me")

    def test_get_missing_raises(self):
        with self.assertRaises(NotFoundError):
            self.service.get_task(999)

    def test_patch_and_put(self):
        task = self.service.create_task(
            {"title": "a", "priority": "high", "description": "d"})
        patched = self.service.update_task(task.id, {"title": "b"})
        self.assertEqual((patched.title, patched.priority), ("b", "high"))
        replaced = self.service.update_task(
            task.id, {"title": "c"}, partial=False)
        self.assertEqual((replaced.priority, replaced.description),
                         ("medium", ""))
        with self.assertRaises(ValidationError):  # PUT needs a title
            self.service.update_task(task.id, {"priority": "low"},
                                     partial=False)
        with self.assertRaises(ValidationError):  # empty PATCH
            self.service.update_task(task.id, {})

    def test_clear_due_date(self):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        task = self.service.create_task({"title": "a", "due_date": tomorrow})
        updated = self.service.update_task(task.id, {"due_date": None})
        self.assertIsNone(updated.due_date)

    def test_complete_incomplete_idempotent(self):
        task = self.service.create_task({"title": "a"})
        self.assertEqual(self.service.set_completed(task.id, True).status,
                         "completed")
        self.assertEqual(self.service.set_completed(task.id, True).status,
                         "completed")
        self.assertEqual(self.service.set_completed(task.id, False).status,
                         "pending")

    def test_delete(self):
        task = self.service.create_task({"title": "a"})
        self.service.delete_task(task.id)
        with self.assertRaises(NotFoundError):
            self.service.delete_task(task.id)

    def test_filters_and_sorting(self):
        t1 = self.service.create_task({"title": "Buy milk", "priority": "low"})
        self.service.create_task({"title": "Write report", "priority": "high",
                                  "description": "quarterly"})
        self.service.create_task({"title": "Call bank", "priority": "medium"})
        self.service.set_completed(t1.id, True)

        titles = lambda params: [t.title for t in
                                 self.service.list_tasks(params)]
        self.assertEqual(titles({"status": "completed"}), ["Buy milk"])
        self.assertEqual(titles({"priority": "high"}), ["Write report"])
        self.assertEqual(titles({"search": "quarter"}), ["Write report"])
        self.assertEqual(
            titles({"sort_by": "priority", "order": "desc"}),
            ["Write report", "Call bank", "Buy milk"])
        self.assertEqual(titles({"limit": "1", "offset": "1"}),
                         ["Write report"])

    def test_overdue_filter(self):
        task = self.service.create_task({"title": "old"})
        self.service.repository.update(task.id, {"due_date": "2000-01-01"})
        self.service.create_task({"title": "no date"})
        self.assertEqual(
            [t.title for t in self.service.list_tasks({"overdue": "true"})],
            ["old"])
        self.service.set_completed(task.id, True)
        self.assertEqual(self.service.list_tasks({"overdue": "true"}), [])

    def test_invalid_filters(self):
        for params in ({"status": "x"}, {"limit": "0"}, {"limit": "abc"},
                       {"due_before": "bad"}, {"bogus": "1"},
                       {"overdue": "maybe"}, {"offset": "-1"}):
            with self.subTest(params=params):
                with self.assertRaises(ValidationError):
                    self.service.list_tasks(params)

    def test_sql_injection_is_harmless(self):
        self.service.create_task({"title": "safe"})
        self.assertEqual(
            self.service.list_tasks({"search": "'; DROP TABLE tasks; --"}), [])
        self.assertEqual(len(self.service.list_tasks()), 1)


if __name__ == "__main__":
    unittest.main()
