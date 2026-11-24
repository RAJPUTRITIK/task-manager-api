import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from task_manager.api import create_server
from task_manager.cli import main as cli_main


class ApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.tmp.name, "api.db")
        cls.server = create_server("127.0.0.1", 0, cls.db_path)
        cls.base = "http://127.0.0.1:%d" % cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def call(self, method, path, body=None, raw=None):
        data = raw if raw is not None else (
            json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(self.base + path, data=data,
                                     method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as resp:
                text = resp.read().decode()
                return resp.status, json.loads(text) if text else None
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode())

    def test_full_crud_flow(self):
        status, task = self.call("POST", "/tasks",
                                 {"title": "API task", "priority": "high"})
        self.assertEqual(status, 201)
        tid = task["id"]

        status, body = self.call("GET", "/tasks/%d" % tid)
        self.assertEqual((status, body["title"]), (200, "API task"))

        status, body = self.call("PATCH", "/tasks/%d" % tid,
                                 {"priority": "low"})
        self.assertEqual((status, body["priority"]), (200, "low"))

        status, body = self.call("PUT", "/tasks/%d" % tid, {"title": "New"})
        self.assertEqual((status, body["priority"]), (200, "medium"))

        status, body = self.call("POST", "/tasks/%d/complete" % tid)
        self.assertEqual(body["status"], "completed")
        status, body = self.call("POST", "/tasks/%d/incomplete" % tid)
        self.assertEqual(body["status"], "pending")

        status, body = self.call("GET", "/tasks?priority=medium")
        self.assertEqual(status, 200)
        self.assertTrue(any(t["id"] == tid for t in body["tasks"]))

        status, _ = self.call("DELETE", "/tasks/%d" % tid)
        self.assertEqual(status, 204)
        status, _ = self.call("GET", "/tasks/%d" % tid)
        self.assertEqual(status, 404)

    def test_error_responses(self):
        self.assertEqual(self.call("POST", "/tasks", {"title": ""})[0], 400)
        self.assertEqual(self.call("POST", "/tasks", raw=b"{bad json")[0], 400)
        self.assertEqual(self.call("POST", "/tasks", raw=b"[1]")[0], 400)
        self.assertEqual(self.call("POST", "/tasks")[0], 400)
        self.assertEqual(self.call("GET", "/tasks?status=zzz")[0], 400)
        self.assertEqual(self.call("GET", "/nope")[0], 404)
        self.assertEqual(self.call("GET", "/tasks/99999")[0], 404)
        self.assertEqual(self.call("PUT", "/tasks")[0], 405)
        self.assertEqual(self.call("DELETE", "/tasks/99999")[0], 404)

    def test_health(self):
        self.assertEqual(self.call("GET", "/health"), (200, {"status": "ok"}))


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "cli.db")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli_main(["--local", "--db", self.db] + list(args))
        return code, out.getvalue(), err.getvalue()

    def test_cli_flow(self):
        code, out, _ = self.run_cli("add", "Learn Python", "-p", "high")
        self.assertEqual(code, 0)
        self.assertIn("Task created", out)

        code, out, _ = self.run_cli("list")
        self.assertIn("Learn Python", out)
        self.assertIn("[ ]", out)

        self.run_cli("complete", "1")
        code, out, _ = self.run_cli("list", "--status", "completed")
        self.assertIn("[x]", out)

        code, out, _ = self.run_cli("update", "1", "--title", "Master Python")
        self.assertIn("Master Python", out)

        code, out, _ = self.run_cli("delete", "1", "-y")
        self.assertIn("deleted", out)
        code, out, _ = self.run_cli("list")
        self.assertIn("No tasks found", out)

    def test_cli_errors(self):
        code, _, err = self.run_cli("show", "42")
        self.assertEqual(code, 1)
        self.assertIn("not found", err)
        code, _, err = self.run_cli("add", "x", "--due", "2000-01-01")
        self.assertEqual(code, 1)
        self.assertIn("past", err)
        code, _, err = self.run_cli("update", "1")
        self.assertEqual(code, 1)

    def test_cli_cannot_reach_api(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = cli_main(["--api-url", "http://127.0.0.1:1", "list"])
        self.assertEqual(code, 1)
        self.assertIn("Cannot connect", err.getvalue())


if __name__ == "__main__":
    unittest.main()
