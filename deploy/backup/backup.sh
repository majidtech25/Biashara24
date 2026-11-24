#!/bin/sh
# Take one backup now: dump, check the file can be read back, prune old copies,
# and copy it off the server when BACKUP_REMOTE is set.
set -eu
: "${PGHOST:=db}" "${PGUSER:?}" "${PGDATABASE:?}" "${PGPASSWORD:?}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
DIR=/backups
mkdir -p "$DIR"

stamp=$(date +%Y%m%d-%H%M%S)
file="$DIR/biashara-$stamp.dump"
pg_dump --format=custom --no-owner --file="$file.partial"
# A dump that pg_restore cannot list is not a backup.
pg_restore --list "$file.partial" > /dev/null
mv "$file.partial" "$file"
echo "$(date -Iseconds) backup ok: $file ($(du -h "$file" | cut -f1))"

find "$DIR" -name 'biashara-*.dump' -mtime +"$KEEP_DAYS" -print -delete

if [ -n "${BACKUP_REMOTE:-}" ]; then
	rclone copy "$file" "$BACKUP_REMOTE"
	rclone delete --min-age "${KEEP_DAYS}d" --include 'biashara-*.dump' "$BACKUP_REMOTE"
	echo "$(date -Iseconds) copied off-site to $BACKUP_REMOTE"
else
	echo "$(date -Iseconds) WARNING: BACKUP_REMOTE is not set, so backups stay on this server only"
fi
date -Iseconds > "$DIR/.last-success"
