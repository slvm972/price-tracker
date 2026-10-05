#!/usr/bin/env python3
"""
Simple scheduler for the local Price Tracker update cycle.

Each run:
  1. download_all.py — collect/process supermarket data
  2. make_viewer.py   — regenerate local data.js for the frontend

Usage:
  python scripts/scheduler.py --interval 6
  python scripts/scheduler.py --once
"""

import argparse
import logging
import os
import subprocess
import sys
import time

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
VENV_PY = os.path.join(BASE_DIR, ".venv", "bin", "python")
DOWNLOAD_SCRIPT = os.path.join(BASE_DIR, "download_all.py")
MAKE_VIEWER_SCRIPT = os.path.join(BASE_DIR, "make_viewer.py")
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


def run_command(python, script):
    cmd = [python, script]
    logging.info("Running: %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, cwd=BASE_DIR)
        logging.info("Return code: %s", result.returncode)
        return result.returncode
    except Exception as exc:
        logging.exception("Failed to run %s: %s", script, exc)
        return 1


def run_once(python):
    download_rc = run_command(python, DOWNLOAD_SCRIPT)
    if download_rc != 0:
        logging.error("Download failed; data.js was not regenerated.")
        return download_rc

    return run_command(python, MAKE_VIEWER_SCRIPT)


def main():
    parser = argparse.ArgumentParser(description="Scheduler for Price Tracker")
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
        raise SystemExit(run_once(python))

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
