"""Command-line interface (argparse)."""

import argparse
import os
import sys

from .client import ApiClient, ClientError, LocalClient
from .database import DEFAULT_DB_PATH
from .models import PRIORITIES, STATUSES
from .validators import SORT_FIELDS

DEFAULT_API_URL = os.environ.get("TASKS_API_URL", "http://127.0.0.1:8000")



# Output formatting

def _truncate(text, width):
    return text if len(text) <= width else text[:width - 3] + "..."


def format_table(tasks):
    """Render a list of task dicts as an aligned text table."""
    if not tasks:
        return "No tasks found."
    headers = ["ID", "DONE", "PRIORITY", "DUE", "TITLE"]
    rows = [[
        str(t["id"]),
        "[x]" if t["status"] == "completed" else "[ ]",
        t["priority"],
        t["due_date"] or "-",
        _truncate(t["title"], 40),
    ] for t in tasks]
    widths = [max(len(h), *(len(r[i]) for r in rows))
              for i, h in enumerate(headers)]
    line = "  ".join("{:<%d}" % w for w in widths)
    out = [line.format(*headers).rstrip(), "  ".join("-" * w for w in widths)]
    out.extend(line.format(*row).rstrip() for row in rows)
    out.append("\n%d task(s)" % len(tasks))
    return "\n".join(out)


def format_task(task):
    """Render one task dict as key: value lines."""
    return "\n".join([
        "ID          : %s" % task["id"],
        "Title       : %s" % task["title"],
        "Description : %s" % (task["description"] or "-"),
        "Status      : %s" % task["status"],
        "Priority    : %s" % task["priority"],
        "Created at  : %s" % task["created_at"],
        "Due date    : %s" % (task["due_date"] or "-"),
    ])


# Command handlers: (client, args) -> None

def cmd_add(client, args):
    payload = {"title": args.title}
    if args.description is not None:
        payload["description"] = args.description
    if args.priority:
        payload["priority"] = args.priority
    if args.due:
        payload["due_date"] = args.due
    task = client.create_task(payload)
    print("Task created.\n")
    print(format_task(task))


def cmd_list(client, args):
    params = {}
    for key in ("status", "priority", "search", "sort_by", "order", "limit",
                "due_before", "due_after"):
        value = getattr(args, key)
        if value is not None:
            params[key] = value
    if args.overdue:
        params["overdue"] = "true"
    print(format_table(client.list_tasks(params)))


def cmd_show(client, args):
    print(format_task(client.get_task(args.id)))


def cmd_update(client, args):
    payload = {}
    if args.title is not None:
        payload["title"] = args.title
    if args.description is not None:
        payload["description"] = args.description
    if args.priority:
        payload["priority"] = args.priority
    if args.status:
        payload["status"] = args.status
    if args.due:
        payload["due_date"] = args.due
    if args.clear_due:
        payload["due_date"] = None
    if not payload:
        raise ClientError("Nothing to update. Pass at least one option "
                          "(see 'update --help').")
    task = client.update_task(args.id, payload)
    print("Task updated.\n")
    print(format_task(task))


def cmd_delete(client, args):
    if not args.yes:
        answer = input("Delete task %d? [y/N] " % args.id)
        if answer.strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return
    client.delete_task(args.id)
    print("Task %d deleted." % args.id)


def cmd_complete(client, args):
    task = client.set_completed(args.id, True)
    print("Task %d marked as completed: %s" % (task["id"], task["title"]))


def cmd_incomplete(client, args):
    task = client.set_completed(args.id, False)
    print("Task %d marked as pending: %s" % (task["id"], task["title"]))


# Parser

def build_parser():
    parser = argparse.ArgumentParser(
        prog="tasks", description="Task manager command-line client.")
    parser.add_argument("--api-url", default=DEFAULT_API_URL,
                        help="API base URL (default: %(default)s)")
    parser.add_argument("--local", action="store_true",
                        help="skip the API and use the database directly")
    parser.add_argument("--db", default=DEFAULT_DB_PATH,
                        help="database file for --local "
                             "(default: %(default)s)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("add", help="create a task")
    p.add_argument("title")
    p.add_argument("-d", "--description")
    p.add_argument("-p", "--priority", choices=PRIORITIES)
    p.add_argument("--due", metavar="YYYY-MM-DD")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list", help="list tasks (with optional filters)")
    p.add_argument("--status", choices=STATUSES)
    p.add_argument("-p", "--priority", choices=PRIORITIES)
    p.add_argument("-s", "--search", help="text in title or description")
    p.add_argument("--overdue", action="store_true",
                   help="only pending tasks past their due date")
    p.add_argument("--due-before", metavar="YYYY-MM-DD")
    p.add_argument("--due-after", metavar="YYYY-MM-DD")
    p.add_argument("--sort-by", choices=SORT_FIELDS)
    p.add_argument("--order", choices=("asc", "desc"))
    p.add_argument("--limit", type=int)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("show", help="show one task")
    p.add_argument("id", type=int)
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("update", help="update fields of a task")
    p.add_argument("id", type=int)
    p.add_argument("--title")
    p.add_argument("-d", "--description")
    p.add_argument("-p", "--priority", choices=PRIORITIES)
    p.add_argument("--status", choices=STATUSES)
    due = p.add_mutually_exclusive_group()
    due.add_argument("--due", metavar="YYYY-MM-DD")
    due.add_argument("--clear-due", action="store_true",
                     help="remove the due date")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("delete", help="delete a task")
    p.add_argument("id", type=int)
    p.add_argument("-y", "--yes", action="store_true",
                   help="do not ask for confirmation")
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser("complete", help="mark a task as completed")
    p.add_argument("id", type=int)
    p.set_defaults(func=cmd_complete)

    p = sub.add_parser("incomplete", help="mark a task as pending again")
    p.add_argument("id", type=int)
    p.set_defaults(func=cmd_incomplete)

    return parser


def main(argv=None):
    """Entry point. Returns a process exit code."""
    args = build_parser().parse_args(argv)
    client = LocalClient(args.db) if args.local else ApiClient(args.api_url)
    try:
        args.func(client, args)
    except ClientError as exc:
        print("Error: %s" % exc, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
    return 0
