#!/bin/bash
HEARTBEAT_FILE="/path/to/project/logs/heartbeat"
MAX_AGE=300

if [ -f "$HEARTBEAT_FILE" ]; then
    AGE=$(( $(date +%s) - $(date +%s -r "$HEARTBEAT_FILE") ))
    if [ $AGE -gt $MAX_AGE ]; then
        echo "Heartbeat старый ($AGE сек), перезапускаем..."
        sudo systemctl restart leadmonitor
    fi
else
    echo "Heartbeat не найден, перезапускаем..."
    sudo systemctl restart leadmonitor
fi
