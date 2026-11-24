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

## 7a. M-Pesa Paybill and QR code (optional)

The system never asks the customer to pay. Every bill it prints shows the business's **Paybill number**, the
**bill number as the account number**, the amount, and (with Daraja keys) an **M-Pesa QR code** the customer
can scan. The customer pays by themselves. Safaricom then tells the system about each payment into the Paybill,
and the cashier sees it under **M-Pesa payments received** at checkout (or on the car wash). The cashier picks
the payment (or types the receipt number from the customer's message) and records the bill as paid. Cash is
recorded as before.

What the system checks when a receipt is used:
- the receipt has not paid another bill already,
- the amount matches the bill (otherwise staff are told the difference),
- the payment belongs to this branch's bill.

A receipt Safaricom has not reported yet is saved as **waiting**, as before. It is confirmed by itself when
Safaricom's notice for it arrives with the same amount.

Setting it up:

1. **Paybill only, no keys:** set `MPESA_SHORTCODE` to the Paybill number. Bills then show the Paybill and
   account number. Staff check receipts by hand. There is no QR code and no automatic monitoring.
2. **With Daraja keys:** create an account and an app on Safaricom's developer portal
   ([developer.safaricom.co.ke](https://developer.safaricom.co.ke)). It gives a **consumer key** and
   **consumer secret**. Test in the sandbox first with `MPESA_ENVIRONMENT=sandbox` and the sandbox
   test shortcode the portal shows.
3. In `.env`, fill in `MPESA_CONSUMER_KEY`, `MPESA_CONSUMER_SECRET`, `MPESA_SHORTCODE`, `MPESA_BUSINESS_NAME`
   and `MPESA_CALLBACK_TOKEN` (make it with `openssl rand -hex 32`). Apply with `sudo docker compose up -d`.
4. **Tell Safaricom where to send payments:** on the server, run
   ```bash
   cd ~/Biashara24/deploy
   sudo docker compose exec backend python -c "from app.services import mpesa; print(mpesa.register_urls())"
   ```
   (a signed-in director can do the same with `POST /api/paybill/register`; it is also recorded in the audit log).
   The system registers these two addresses with Safaricom's C2B v2 API:
   `https://<your domain>/api/c2b/<MPESA_CALLBACK_TOKEN>/confirmation` and `.../validation`.
   Safaricom's rules: the addresses must be public HTTPS and must not contain words such as "mpesa",
   "safaricom", "exe", "cmd", "sql" or "query". In production the addresses are registered **once**; to change
   them later, ask Safaricom (M-Pesa business support) to remove the old ones first.
5. **Going live:** apply for go-live on the portal for the business's Paybill. Then set
   `MPESA_ENVIRONMENT=production`, change the key, secret and shortcode to the live ones, run
   `sudo docker compose up -d`, and register the addresses (step 4) once more for production.
6. **Before trusting the QR code with customers:** scan a printed bill's QR code with the M-PESA app and
   check that it fills in the right Paybill, account number and amount. The system sends the bill number as
   the QR code's reference (`RefNo`). The Daraja documentation copies we used do not state how the app
   shows that reference for a Paybill, so check it on a real phone before going live.

Only someone who knows `MPESA_CALLBACK_TOKEN` can post payments to the system. Keep it secret. If it leaks,
change it and register the addresses again (in production, Safaricom must remove the old ones first).

What managers see: **M-Pesa Paybill payments** on the Live Orders page lists every payment into the
Paybill, those not yet confirmed by staff first. A payment with **No match** usually means the customer typed
the account number wrongly; the cashier can still use it by its receipt number.

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
