#!/bin/sh
# Deploy the latest code: back up, rebuild, restart, and wait until the app is ready.
# Usage, from deploy/:  ./update.sh
set -eu
cd "$(dirname "$0")"
git pull --ff-only
if docker compose ps --status running --services | grep -qx backup; then
	echo "Backing up before the update..."
	docker compose exec -T backup backup.sh
fi
docker compose up -d --build
echo "Waiting for the app to be ready..."
for _ in $(seq 1 60); do
	if docker compose exec -T backend python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/ready',timeout=5).status==200 else 1)" 2>/dev/null; then
		echo "Ready."; exit 0
	fi
	sleep 5
done
echo "The app did not become ready. Check: docker compose logs backend"
exit 1
