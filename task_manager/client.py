"""Two interchangeable back-ends for the CLI: HTTP API or direct (local)."""

import json
import urllib.error
import urllib.parse
import urllib.request

from .database import TaskRepository
from .service import NotFoundError, TaskService
from .validators import ValidationError


class ClientError(Exception):
    """Any error the CLI should show to the user as a plain message."""


class ApiClient:
    """Talks to the running REST API using ``urllib``."""

    def __init__(self, base_url, timeout=10):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, method, path, body=None, params=None):
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raise ClientError(self._error_message(exc))
        except (urllib.error.URLError, OSError):
            raise ClientError(
                "Cannot connect to API at %s. Is the server running? "
                "(start it with 'python run_server.py' or use --local)"
                % self.base_url)
        return json.loads(raw.decode("utf-8")) if raw else None

    @staticmethod
    def _error_message(exc):
        try:
            return json.loads(exc.read().decode("utf-8"))["error"]
        except (ValueError, KeyError, UnicodeDecodeError):
            return "Server returned HTTP %s" % exc.code

    def create_task(self, payload):
        return self._request("POST", "/tasks", body=payload)

    def list_tasks(self, params):
        return self._request("GET", "/tasks", params=params)["tasks"]

    def get_task(self, task_id):
        return self._request("GET", "/tasks/%d" % task_id)

    def update_task(self, task_id, payload):
        return self._request("PATCH", "/tasks/%d" % task_id, body=payload)

    def delete_task(self, task_id):
        self._request("DELETE", "/tasks/%d" % task_id)

    def set_completed(self, task_id, completed):
        action = "complete" if completed else "incomplete"
        return self._request("POST", "/tasks/%d/%s" % (task_id, action))


class LocalClient:
    """Uses the service layer directly - no server needed."""

    def __init__(self, db_path):
        self.service = TaskService(TaskRepository(db_path))

    @staticmethod
    def _call(func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (ValidationError, NotFoundError) as exc:
            raise ClientError(str(exc))

    def create_task(self, payload):
        return self._call(self.service.create_task, payload).to_dict()

    def list_tasks(self, params):
        return [t.to_dict() for t in self._call(
            self.service.list_tasks, params)]

    def get_task(self, task_id):
        return self._call(self.service.get_task, task_id).to_dict()

    def update_task(self, task_id, payload):
        return self._call(self.service.update_task, task_id, payload).to_dict()

    def delete_task(self, task_id):
        self._call(self.service.delete_task, task_id)

    def set_completed(self, task_id, completed):
        return self._call(
            self.service.set_completed, task_id, completed).to_dict()
