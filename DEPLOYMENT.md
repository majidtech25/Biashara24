# Putting Biashara24 on a server

This guide sets up the app on one cloud server (a VPS). The same steps work for staging and,
later, for the live system. Everything runs in Docker containers:

| Container | What it does |
| --- | --- |
| `web` | Serves the app and gets HTTPS certificates automatically (Caddy) |
| `backend` | The API. Upgrades the database by itself when it starts |
| `db` | PostgreSQL 16. Data lives in a Docker volume that survives restarts and updates |
| `backup` | Backs up the database every day and can copy it off the server |

All commands below run on the server unless stated otherwise.

## What you need

- A Linux server with a public IP address. These steps were written for Ubuntu 24.04 LTS.
- A domain or subdomain for it, for example `staging.yourbusiness.co.ke`.
- About 30 minutes.

## 1. Point the domain at the server

At your domain provider, add a DNS **A record** for the subdomain with the server's IP address.
Wait until it works: `ping staging.yourbusiness.co.ke` should show the server's IP.
HTTPS will not work until this is done.

## 2. Install Docker and open the firewall

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443
sudo ufw enable
```

Ports 80 and 443 are for the app. The database is not reachable from outside the server.

## 3. Get the code and fill in the settings

```bash
git clone https://github.com/majidtech25/Biashara24.git
cd Biashara24/deploy
cp .env.example .env
nano .env
```

In `.env`:

- `DOMAIN`: your subdomain, without `https://`.
- `POSTGRES_PASSWORD` and `SECRET_KEY`: paste a different value into each, made with `openssl rand -hex 32`.
  Keep a copy somewhere safe, such as a password manager. Changing `SECRET_KEY` later signs everyone out.
- Leave `ENVIRONMENT=production`. This turns off the development logins such as `director@gmail.com`.

## 4. Start it

```bash
sudo docker compose up -d --build
sudo docker compose ps
```

The first build takes a few minutes. When `backend` shows `healthy`, open `https://<your domain>/ready`.
It should show `"status":"ready"`.

## 5. Create the first director account

```bash
sudo docker compose exec backend python -m app.ops create-admin
```

It asks for an email and a password of at least 12 characters. Sign in at `https://<your domain>/login`
as **Director**, then create branches and staff accounts from the app.

## 6. Off-site backups

Backups run every day at `BACKUP_TIME` (03:00 Nairobi time by default) and are kept for
`BACKUP_KEEP_DAYS` days in `deploy/backups/`. A copy that only lives on the same server is lost with the
server, so also send it somewhere else. The `backup` container includes [rclone](https://rclone.org/),
which can copy to many storage services (Backblaze B2, Amazon S3, Google Drive and others).

1. Create a storage bucket or folder with the provider you choose.
2. Set up rclone. It asks questions; pick your provider and paste its keys:
   ```bash
   sudo docker compose run --rm backup rclone config
   ```
   Note the name you give the remote, for example `offsite`. The settings are saved in `deploy/rclone/`.
3. In `.env`, set `BACKUP_REMOTE=offsite:biashara-backups` (remote name, colon, bucket or folder).
4. Apply it and test it:
   ```bash
   sudo docker compose up -d
   sudo docker compose exec backup backup.sh
   ```
   The last line should say `copied off-site`.

Backups are also taken automatically before every update (step 8).

## 7. Monitoring

- **Is it up?** Point an uptime monitor (for example UptimeRobot or Better Stack) at
  `https://<your domain>/ready`. It returns 200 when the app and database are working, and 503 when the
  database is unreachable or not upgraded. Have the monitor send an SMS or email when it fails.
- **Errors:** to be alerted about server errors, create a project at [Sentry](https://sentry.io/),
  put its DSN in `SENTRY_DSN` in `.env`, and run `sudo docker compose up -d`. Request bodies, cookies,
  user details and local variables are not sent.
- **Logs:** `sudo docker compose logs -f backend` (or `web`, `db`, `backup`). Logs are rotated
  automatically, so they do not fill the disk.
- **Backups:** `sudo docker compose logs backup` shows each night's result. `deploy/backups/.last-success`
  holds the time of the last good backup.

The containers restart by themselves after a crash or a server reboot.

## 7a. M-Pesa prompts (optional)

With this set up, the cashier types the customer's number and the customer gets a prompt on their phone to
enter their M-Pesa PIN. The bill or car wash is marked paid by itself when Safaricom confirms it. Without it,
staff keep entering the receipt number from the customer's M-Pesa message by hand, as now.

1. Create an account and an app on Safaricom's developer portal ([developer.safaricom.co.ke](https://developer.safaricom.co.ke))
   with the M-Pesa Express API. It gives a **consumer key** and **consumer secret**.
2. **Testing first (sandbox):** the portal's simulator shows test credentials, including a test shortcode and
   passkey. Put them in `.env` with `MPESA_ENVIRONMENT=sandbox`.
3. In `.env`, fill in `MPESA_CONSUMER_KEY`, `MPESA_CONSUMER_SECRET`, `MPESA_SHORTCODE`, `MPESA_PASSKEY`, and
   `MPESA_CALLBACK_TOKEN` (make it with `openssl rand -hex 32`). For a **Till**, also set `MPESA_TILL_NUMBER` to
   the Till number, and set `MPESA_SHORTCODE` to the store number Safaricom gives for it. For a **Paybill**,
   leave `MPESA_TILL_NUMBER` empty.
4. Apply it: `sudo docker compose up -d`. The M-Pesa option at checkout now shows **Send M-Pesa prompt**.
5. **Going live:** apply for go-live on the portal for the business's Paybill or Till. Safaricom sends the
   live passkey by email. Then set `MPESA_ENVIRONMENT=production`, change the key, secret, shortcode and
   passkey to the live ones, and run `sudo docker compose up -d` again.

Safaricom sends payment results to `https://<your domain>/api/mpesa/callback/<MPESA_CALLBACK_TOKEN>`. Only
someone who knows the token can post results there. Keep it secret, and change it if it leaks.

What staff see:
- If the customer cancels, has too little money, enters a wrong PIN or does not answer, the screen says so.
  Staff can send the prompt again, or take cash instead.
- If a result never arrives, the app asks Safaricom for it after about 20 seconds.
- If money arrives for a bill that was already paid another way, nothing is applied twice. The payment is
  listed under **M-Pesa payments needing attention** on the managers' Payments page, so it can be refunded.

## 8. Updating to a new version

```bash
cd ~/Biashara24/deploy
sudo ./update.sh
```

It takes a backup, pulls the latest code, rebuilds, restarts, and waits until the app is ready.

## 9. Restoring

**Restore drill.** Run this once now and then monthly. It restores the newest backup into a scratch
database, compares it with live data, and deletes the scratch copy. Live data is not touched.

```bash
sudo ./restore-drill.sh
```

**Real restore.** This replaces all live data with a backup. It backs up the current data first, so the
restore itself can be undone.

```bash
ls backups/
sudo ./restore.sh backups/biashara-20261124-030000.dump
```

To restore onto a new server, follow steps 1 to 4 with the same `.env`, copy the backup file into
`deploy/backups/` (with `rclone copy offsite:biashara-backups/<file> backups/` if needed), then run `restore.sh`.

## Troubleshooting

| Problem | Check |
| --- | --- |
| Browser says the site is not secure | The DNS A record must point at this server, and ports 80 and 443 must be open. Then see `sudo docker compose logs web`. |
| `/ready` returns 503 | `sudo docker compose logs backend db` |
| Cannot sign in with `director@gmail.com` | Expected: development logins are off in production. Use step 5. |
| Backup says `BACKUP_REMOTE is not set` | Backups are on this server only. Do step 6. |
