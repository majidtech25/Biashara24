#!/bin/sh
# Replace the live database with a backup. This overwrites everything recorded
# since that backup, so it asks for confirmation. A fresh backup of the current
# data is taken first, so this step can itself be undone.
# Usage, from deploy/:  ./restore.sh backups/biashara-YYYYMMDD-HHMMSS.dump
set -eu
cd "$(dirname "$0")"
file="${1:?Give the backup file, e.g. backups/biashara-20261124-030000.dump}"
[ -f "$file" ] || { echo "Not found: $file"; exit 1; }
name=$(basename "$file")
printf 'This replaces ALL live data with %s. Type RESTORE to continue: ' "$name"
read -r answer
[ "$answer" = "RESTORE" ] || { echo "Cancelled."; exit 1; }

echo "Backing up the current data first..."
docker compose exec -T backup backup.sh
echo "Stopping the app..."
docker compose stop backend
docker compose exec -T backup sh -c "pg_restore --clean --if-exists --no-owner --exit-on-error -d \$PGDATABASE /backups/$name"
echo "Starting the app (it upgrades the restored database if needed)..."
docker compose start backend
echo "Restored $name."
