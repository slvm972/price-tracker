Scheduler for Price Tracker
=========================

The scheduler runs the local data update cycle:

1. download_all.py collects/processes supermarket data into SQLite.
2. make_viewer.py regenerates data.js from the SQLite database.

The frontend interface itself lives in the separate repository:
`slvm972/pricetracker-interface-found`.

## Quick start

Run one update:

```bash
./.venv/bin/python scripts/scheduler.py --once
```

Run continuously every 6 hours:

```bash
./.venv/bin/python scripts/scheduler.py
```

Change the interval:

```bash
./.venv/bin/python scripts/scheduler.py --interval 12
```

The scheduler uses `.venv/bin/python` when it exists; otherwise it uses the current Python interpreter.

## What is generated

After a successful run:

- `prices.db` contains the collected data.
- `data.js` contains the compact catalog consumed by the frontend.
- `logs/scheduler.log` contains scheduler output.

`prices.db`, `data.js`, logs, dumps and other local data are intentionally excluded from Git.

## Cron

For a Linux server, cron can call the one-shot mode:

```cron
0 */6 * * * /home/user/projects/price-tracker/.venv/bin/python /home/user/projects/price-tracker/scripts/scheduler.py --once >> /home/user/projects/price-tracker/logs/scheduler_cron.log 2>&1
```

The old systemd service/timer references were removed from this documentation because those example files are not part of the repository.