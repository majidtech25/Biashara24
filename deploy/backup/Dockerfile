# pg_dump from the same PostgreSQL major version as the database, plus rclone
# for copying backups off the server.
FROM postgres:16-alpine
RUN apk add --no-cache rclone
COPY backup.sh /usr/local/bin/backup.sh
COPY schedule.sh /usr/local/bin/schedule.sh
RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/schedule.sh
CMD ["/usr/local/bin/schedule.sh"]
