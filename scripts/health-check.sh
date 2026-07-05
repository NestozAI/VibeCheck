#!/bin/bash
# VibeCheck Agent Health Check
# Add to crontab: */2 * * * * /path/to/health-check.sh
#
# Checks if the agent process is running. If not, restarts it.
# Requires passwordless sudo for systemctl (see README).

SERVICE="vibecheck-agent.service"

if ! systemctl is-active --quiet "$SERVICE"; then
    echo "[$(date)] Agent is down. Restarting..."
    sudo systemctl restart "$SERVICE"
    echo "[$(date)] Restart triggered."
fi
