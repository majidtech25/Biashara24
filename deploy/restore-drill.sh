#!/bin/sh
# Restore drill: prove a backup can be restored, without touching live data.
# Restores the newest backup (or the file given) into a scratch database, compares
# row counts of key tables with the live database, then drops the scratch database.
# Usage, from deploy/:  ./restore-drill.sh [backups/biashara-YYYYMMDD-HHMMSS.dump]
set -eu
cd "$(dirname "$0")"
file="${1:-$(ls -1t backups/biashara-*.dump 2>/dev/null | head -n 1)}"
[ -n "$file" ] && [ -f "$file" ] || { echo "No backup file found. Run: docker compose exec backup backup.sh"; exit 1; }
name=$(basename "$file")
scratch=restore_drill

echo "Restoring $name into a scratch database..."
docker compose exec -T backup sh -c "dropdb --if-exists $scratch && createdb $scratch && pg_restore --no-owner --exit-on-error -d $scratch /backups/$name"

status=0
for table in users orders payments carwash_transactions branches; do
	live=$(docker compose exec -T backup psql -tAc "select count(*) from $table")
	restored=$(docker compose exec -T backup psql -d $scratch -tAc "select count(*) from $table")
	echo "$table: live $live, restored $restored"
	# New rows may arrive after the backup, so the restored copy can only be equal or smaller.
	[ "$restored" -le "$live" ] || status=1
done
docker compose exec -T backup dropdb $scratch
[ $status -eq 0 ] && echo "Restore drill passed: $name can be restored." || echo "Restore drill FAILED"
exit $status
