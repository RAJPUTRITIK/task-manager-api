"""REST API built on ``http.server`` (standard library only)."""

import json
import logging
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .database import DEFAULT_DB_PATH, TaskRepository
from .service import NotFoundError, TaskService
from .validators import ValidationError

logger = logging.getLogger(__name__)

MAX_BODY_BYTES = 1024 * 1024  # 1 MB

# (compiled path pattern, {HTTP method: handler suffix})
ROUTES = [
    (re.compile(r"^/health$"), {"GET": "health"}),
    (re.compile(r"^/tasks$"), {"GET": "list_tasks", "POST": "create_task"}),
    (re.compile(r"^/tasks/(\d+)$"), {
        "GET": "get_task", "PUT": "replace_task",
        "PATCH": "update_task", "DELETE": "delete_task"}),
    (re.compile(r"^/tasks/(\d+)/complete$"), {"POST": "complete_task"}),
    (re.compile(r"^/tasks/(\d+)/incomplete$"), {"POST": "incomplete_task"}),
]


class ApiError(Exception):
    """An error that maps directly to an HTTP status code."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


class TaskRequestHandler(BaseHTTPRequestHandler):
    """Routes requests to handler methods and renders JSON responses."""

    server_version = "TaskAPI/1.0"

    #  HTTP verbs
    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._handle("PUT")

    def do_PATCH(self):
        self._handle("PATCH")

    def do_DELETE(self):
        self._handle("DELETE")

    #  core dispatch
    def _handle(self, method):
        try:
            parsed = urlparse(self.path)
            handler, args = self._resolve(method, parsed.path)
            query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            status, payload = handler(query, *args)
        except ApiError as exc:
            status, payload = exc.status, {"error": exc.message}
        except ValidationError as exc:
            status, payload = 400, {"error": str(exc), "details": exc.errors}
        except NotFoundError as exc:
            status, payload = 404, {"error": str(exc)}
        except Exception:  # never leak internals to the client
            logger.exception("Unhandled error")
            status, payload = 500, {"error": "Internal server error"}
        self._send_json(status, payload)

    def _resolve(self, method, path):
        path = path.rstrip("/") or "/"
        for pattern, methods in ROUTES:
            match = pattern.match(path)
            if not match:
                continue
            name = methods.get(method)
            if name is None:
                raise ApiError(405, "Method %s not allowed on %s"
                               % (method, path))
            return getattr(self, "handle_" + name), \
                tuple(int(g) for g in match.groups())
        raise ApiError(404, "Route %s not found" % path)

    @property
    def service(self):
        return self.server.service

    #  helpers 
    def _read_json_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ApiError(400, "Invalid Content-Length header")
        if length <= 0:
            raise ApiError(400, "Request body is required")
        if length > MAX_BODY_BYTES:
            raise ApiError(413, "Request body too large")
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ApiError(400, "Request body must be valid JSON")

    def _send_json(self, status, payload):
        body = b"" if payload is None else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        if body:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def log_message(self, fmt, *args):  # route access logs via logging
        logger.info("%s - %s", self.address_string(), fmt % args)

    #  endpoint handlers: (query, *path_ids) -> (status, payload)
    def handle_health(self, query):
        return 200, {"status": "ok"}

    def handle_list_tasks(self, query):
        tasks = self.service.list_tasks(query)
        return 200, {"count": len(tasks),
                     "tasks": [t.to_dict() for t in tasks]}

    def handle_create_task(self, query):
        task = self.service.create_task(self._read_json_body())
        return 201, task.to_dict()

    def handle_get_task(self, query, task_id):
        return 200, self.service.get_task(task_id).to_dict()

    def handle_replace_task(self, query, task_id):
        task = self.service.update_task(
            task_id, self._read_json_body(), partial=False)
        return 200, task.to_dict()

    def handle_update_task(self, query, task_id):
        task = self.service.update_task(
            task_id, self._read_json_body(), partial=True)
        return 200, task.to_dict()

    def handle_delete_task(self, query, task_id):
        self.service.delete_task(task_id)
        return 204, None

    def handle_complete_task(self, query, task_id):
        return 200, self.service.set_completed(task_id, True).to_dict()

    def handle_incomplete_task(self, query, task_id):
        return 200, self.service.set_completed(task_id, False).to_dict()


def create_server(host="127.0.0.1", port=8000, db_path=DEFAULT_DB_PATH):
    """Build (but do not start) the HTTP server."""
    server = ThreadingHTTPServer((host, port), TaskRequestHandler)
    server.service = TaskService(TaskRepository(db_path))
    return server


def run(host="127.0.0.1", port=8000, db_path=DEFAULT_DB_PATH):
    """Start the server and block until Ctrl+C."""
    server = create_server(host, port, db_path)
    logger.info("Serving on http://%s:%s (db: %s)", host, port, db_path)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down")
    finally:
        server.server_close()
