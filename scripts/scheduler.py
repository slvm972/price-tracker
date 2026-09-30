#!/usr/bin/env python3
"""
Simple scheduler to run `download_all.py` periodically.

Usage:
  python scripts/scheduler.py --interval 6    # run every 6 hours (default)
  python scripts/scheduler.py --once          # run once and exit

Runs the project's `.venv` Python if available, otherwise uses the current interpreter.
Logs output to `logs/scheduler.log`.
"""

import argparse
import os
import subprocess
import sys
import time
import logging

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
VENV_PY = os.path.join(BASE_DIR, ".venv", "bin", "python")
DOWNLOAD_SCRIPT = os.path.join(BASE_DIR, "download_all.py")
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "scheduler.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)


def find_python():
    if os.path.exists(VENV_PY):
        return VENV_PY
    return sys.executable


def run_once(python):
    cmd = [python, DOWNLOAD_SCRIPT]
    logging.info("Running: %s", " ".join(cmd))
    try:
        res = subprocess.run(cmd, cwd=BASE_DIR)
        logging.info("Return code: %s", res.returncode)
    except Exception as e:
        logging.exception("Failed to run download_all.py: %s", e)


def main():
    parser = argparse.ArgumentParser(description="Scheduler for download_all.py")
    parser.add_argument(
        "--interval",
        type=float,
        default=6.0,
        help="Interval in hours between runs (default: 6)",
    )
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    args = parser.parse_args()

    python = find_python()
    logging.info("Using Python: %s", python)

    if args.once:
        run_once(python)
        return

    interval_seconds = int(args.interval * 3600)
    logging.info("Starting scheduler with interval %s hours", args.interval)
    try:
        while True:
            run_once(python)
            logging.info("Sleeping for %s seconds", interval_seconds)
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        logging.info("Scheduler stopped by user")


if __name__ == "__main__":
    main()
