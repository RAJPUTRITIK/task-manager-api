# Task Management API with CLI

A RESTful task manager plus a command-line client, written in **core Python
only** (standard library: `http.server`, `sqlite3`, `argparse`, `urllib`,
`unittest`). Python 3.8+.

## Project structure

```
task-manager-api/
├── task_manager/
│   ├── models.py        # Task dataclass + constants (statuses, priorities)
│   ├── validators.py    # Input validation (task payloads, list filters)
│   ├── database.py      # SQLite repository (all SQL lives here)
│   ├── service.py       # Business logic (use-cases)
│   ├── api.py           # REST API (http.server) - routing + JSON handling
│   ├── client.py        # ApiClient (HTTP) and LocalClient (direct) for CLI
│   └── cli.py           # argparse commands + table formatting
├── tests/               # unittest suite (service, API, CLI)
├── run_server.py        # start the API server
├── tasks.py             # CLI entry point
├── requirements.txt     # (no third-party dependencies)
└── PROJECT_EXPLANATION.md
```

Layers: `API / CLI -> Service -> Repository -> SQLite`.

## Setup

```bash
python --version            # 3.8 or newer
# optional virtual environment
python -m venv venv   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
# Terminal 1 - start the API (creates tasks.db on first run)
python run_server.py                  # http://127.0.0.1:8000
python run_server.py --port 9000 --db my_tasks.db

# Terminal 2 - use the CLI
python tasks.py add "Write report" -p high --due 2030-12-31
python tasks.py list
```

Run the tests: `python -m unittest discover -s tests -t .`

## Task fields

| Field         | Type   | Rules                                              |
|---------------|--------|----------------------------------------------------|
| `id`          | int    | auto-generated                                     |
| `title`       | string | required, 1-100 chars (trimmed)                    |
| `description` | string | optional, up to 1000 chars, default `""`           |
| `status`      | string | `pending` (default) or `completed`                 |
| `priority`    | string | `low`, `medium` (default), `high`                  |
| `created_at`  | string | auto-generated, ISO datetime                       |
| `due_date`    | string | optional `YYYY-MM-DD`; not in the past on creation |

## API documentation

All bodies are JSON. Errors look like `{"error": "message", "details": [...]}`.

| Method | Endpoint                  | Description                         | Success |
|--------|---------------------------|-------------------------------------|---------|
| GET    | `/health`                 | Health check                        | 200     |
| POST   | `/tasks`                  | Create a task                       | 201     |
| GET    | `/tasks`                  | List tasks (filters below)          | 200     |
| GET    | `/tasks/{id}`             | Get one task                        | 200     |
| PUT    | `/tasks/{id}`             | Replace task (`title` required; omitted fields reset to defaults) | 200 |
| PATCH  | `/tasks/{id}`             | Partially update (only sent fields) | 200     |
| DELETE | `/tasks/{id}`             | Delete a task                       | 204     |
| POST   | `/tasks/{id}/complete`    | Mark completed                      | 200     |
| POST   | `/tasks/{id}/incomplete`  | Mark pending again                  | 200     |

Priority is assigned via the `priority` field on create / PUT / PATCH.

**Status codes:** 400 validation/invalid JSON, 404 unknown task or route,
405 wrong method, 413 body over 1 MB, 500 unexpected error.

### List filters (query string)

| Param        | Example                | Meaning                                       |
|--------------|------------------------|-----------------------------------------------|
| `status`     | `status=pending`       | exact status                                  |
| `priority`   | `priority=high`        | exact priority                                |
| `search`     | `search=report`        | text in title or description                  |
| `overdue`    | `overdue=true`         | pending tasks past their due date             |
| `due_before` | `due_before=2030-12-31`| due date on or before                         |
| `due_after`  | `due_after=2030-01-01` | due date on or after                          |
| `sort_by`    | `sort_by=priority`     | `id`, `created_at`, `due_date`, `priority`, `title` |
| `order`      | `order=desc`           | `asc` (default) or `desc`                     |
| `limit`      | `limit=10`             | 1-100, default 50                             |
| `offset`     | `offset=20`            | pagination offset, default 0                  |

### curl examples

```bash
curl -X POST localhost:8000/tasks -H "Content-Type: application/json" \
     -d '{"title":"Write report","priority":"high","due_date":"2030-12-31"}'
curl "localhost:8000/tasks?status=pending&priority=high&sort_by=due_date"
curl -X PATCH localhost:8000/tasks/1 -d '{"priority":"low"}'
curl -X POST  localhost:8000/tasks/1/complete
curl -X DELETE localhost:8000/tasks/1
```

## CLI usage

The CLI calls the API (set `--api-url` or env `TASKS_API_URL`, default
`http://127.0.0.1:8000`). Add `--local` to skip the server and use the
database file directly (`--db`, or env `TASKS_DB`).

```bash
python tasks.py add "Write report" -d "Q4 numbers" -p high --due 2030-12-31
python tasks.py list
python tasks.py list --status pending --priority high --sort-by due_date
python tasks.py list --overdue
python tasks.py list --search report --limit 5
python tasks.py show 1
python tasks.py update 1 --title "Final report" -p medium --due 2031-01-10
python tasks.py update 1 --clear-due
python tasks.py complete 1
python tasks.py incomplete 1
python tasks.py delete 1            # asks for confirmation; use -y to skip
python tasks.py --local list        # no server needed
python tasks.py --help
```


Exit code is `0` on success and `1` on error (message printed to stderr).

