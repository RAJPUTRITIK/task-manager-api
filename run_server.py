"""Start the Task Management API server."""

import argparse
import logging

from task_manager.api import run
from task_manager.database import DEFAULT_DB_PATH


def main():
    parser = argparse.ArgumentParser(description="Task Management API server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default=DEFAULT_DB_PATH,
                        help="SQLite file (default: %(default)s)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    run(args.host, args.port, args.db)


if __name__ == "__main__":
    main()
