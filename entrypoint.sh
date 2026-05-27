#!/bin/sh
set -e

# If no args supplied, run a small offline run by default
if [ "$#" -eq 0 ]; then
  exec python download_all.py --offline --limit 1
fi

# Otherwise run the command as-is (useful to pass flags)
exec python download_all.py "$@"
