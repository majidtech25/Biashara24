#!/bin/sh
# Run backup.sh once a day at BACKUP_TIME (HH:MM, in TZ). A failed backup is
# logged and retried at the next day's time; the container keeps running.
set -u
AT="${BACKUP_TIME:-03:00}"
echo "Daily backups at $AT ($TZ)"
last=""
while true; do
	today=$(date +%F)
	if [ "$(date +%H:%M)" = "$AT" ] && [ "$last" != "$today" ]; then
		last="$today"
		/usr/local/bin/backup.sh || echo "$(date -Iseconds) BACKUP FAILED"
	fi
	sleep 20
done
