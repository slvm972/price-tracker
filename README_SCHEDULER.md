Scheduler for download_all.py
=============================

This project includes a small scheduler script to run `download_all.py` periodically.

Quick start (recommended):

1. Run once to verify:

```bash
./.venv/bin/python scripts/scheduler.py --once
```

2. Run as a long-lived process (every 6 hours by default):

```bash
./.venv/bin/python scripts/scheduler.py
```

3. To run as a background service, create a systemd service using the project's python and the `--once` option in a timer unit, or use your system's cron to invoke the `--once` command at desired intervals.

Log file: `logs/scheduler.log`

If you prefer cron, add a line like this (runs every 6 hours):

```cron
0 */6 * * * /home/user/projects/price-tracker/.venv/bin/python /home/user/projects/price-tracker/scripts/scheduler.py --once >> /home/user/projects/price-tracker/logs/scheduler_cron.log 2>&1
```

## Systemd timer example

Use the example service and timer files in `scripts/price-tracker.service` and `scripts/price-tracker.timer`.

> Note: on this local machine `systemd` is not available for user timers, so cron is the compatible option here. The service/timer examples are intended for deployment on a normal Linux server with systemd.

To install for the current user:

```bash
cp scripts/price-tracker.service ~/.config/systemd/user/
cp scripts/price-tracker.timer  ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now price-tracker.timer
```

To install system-wide:

```bash
sudo cp scripts/price-tracker.service /etc/systemd/system/
sudo cp scripts/price-tracker.timer  /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now price-tracker.timer
```

Check status with:

```bash
systemctl --user status price-tracker.timer
systemctl --user list-timers | grep price-tracker
```
