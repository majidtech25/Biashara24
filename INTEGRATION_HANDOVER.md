# Integration handover

Implemented and verified locally on 24 September 2026.

## Working workflows

- Six director sidebar destinations remain unchanged.
- Director overview, orders, payments, stock, car wash and reports fetch database data.
- Waiters can sign in at /login/waiter after a manager/director creates their account.
- Orders accept multiple menu items; the server computes prices and totals.
- Cash payments complete immediately. M-Pesa records are pending until an authorized staff member confirms the external receipt. Confirmation is manual bookkeeping, not payment-provider verification or money movement.
- Payment and stock endpoint mismatches are fixed. Forms await successful responses and reload records; failed submissions retain entered values.
- Ingredients support opening stock, additions, corrections, deductions and before/after history.
- Car-wash bays and service prices can be configured. Transactions use the service price, support receipt confirmation and filtered history.
- Menu items, categories, departments, staff accounts, bays, services and printer configuration persist.
- Daily, weekly and monthly reports use confirmed receipts. CSV and multi-page PDF exports include revenue, payment-method breakdowns, top items and current stock alerts.
- Historical revenue is based on confirmation time. Stock alerts are explicitly current, not reconstructed historical balances.
- Authorization remains on server endpoints. Existing store-manager and car-wash-manager access is preserved in addition to the roles listed in the specification.
- Existing API aliases remain where useful; canonical stock creation/listing is /api/stock/ingredients.
- SQLite upgrades add fields without dropping business data and create a pre-upgrade backup beside the database.
- Fresh PostgreSQL schemas can be created. Upgrading an existing PostgreSQL schema requires a reviewed migration; the SQLite upgrade is not silently applied to it.

## Verification

Latest local results: 31 backend tests passed with 93.58% statement coverage; 49 frontend tests passed; the production frontend build succeeded; pip reported no broken requirements. Startup against the configured business database returned a healthy response after creating its pre-migration backup.

Run from backend:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q --cov=app --cov-report=term-missing --cov-fail-under=80
```

Run from frontend:

```powershell
npm.cmd test
npm.cmd run build
```

The backend suite uses a temporary database and tests independent sessions, the waiter/cashier/director workflow, manual payment verification, stock and wash persistence, role boundaries, concurrent duplicate-payment attempts, additive migrations, PDF parsing, and backup/restore integrity. Frontend tests exercise API-backed forms with mocked HTTP responses, including remount/reload and failed saves. These are not a substitute for an on-site browser and hardware acceptance test.

## First use

1. Restart backend and frontend after updating.
2. In the director Overview administration links, create categories, departments and menu items. Create waiter/staff accounts with their actual email addresses.
3. Configure wash bays and services before recording car washes.
4. Enter a restaurant order. Record money received through the cashier checkout. Confirm cashless receipts from Payments.
5. Check the director Overview and Reports, then refresh to verify the saved records remain.
6. Existing starter credentials are for development only. Change or disable them before operational use.

## Printers

The printer adapter sends plain ESC/POS tickets over raw TCP to the configured department LAN IP and port (default 9100). It groups order items by department. ESC/POS commands follow the [Epson command reference](https://download4.epson.biz/sec_pubs/pos/reference_en/).

Missing printers and connection failures are reported without deleting the saved order. There is no automatic retry after a failed/partial send, to avoid duplicate tickets. A successful socket send means bytes were delivered, not proof that paper printed. Confirm the actual printer model supports raw TCP ESC/POS and test each kitchen station before use. No physical printer was available for verification.

## Backup and restore

From backend, choose new destination paths; the commands refuse to overwrite an existing file:

```powershell
.\.venv\Scripts\python.exe -m app.ops backup biashara360.db backups\biashara360-backup.db
.\.venv\Scripts\python.exe -m app.ops restore backups\biashara360-backup.db restored\biashara360.db
```

The backup uses SQLite's online backup API and checks database integrity. Stop the server before switching DATABASE_URL to a restored file. Keep daily backups on a separate device, with retention appropriate for the business. Automated tests verify a small fixture restores correctly in under an hour; recovery time for the real business database and hardware must be measured on site.

## Production preparation

Set ENVIRONMENT=production, a unique SECRET_KEY of at least 32 random characters, the production DATABASE_URL, and exact frontend origins in ALLOWED_ORIGINS. Production startup rejects the sample secret and does not create demonstration accounts. For a fresh production database, provision the first director with:

```powershell
.\.venv\Scripts\python.exe -m app.ops create-admin
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Use a supervised service and an HTTPS reverse proxy for hosted access; serve frontend/dist with index.html fallback for SPA routes. Do not expose Vite's development server as a production server. Configure backups and restrict database file permissions.

## Remaining operational work and boundaries

- No production deployment, physical printer test, staff training or realistic multi-user load test has been performed.
- Suppliers, recipe-based stock deduction, purchase orders, multi-branch management, staff scheduling, notifications and reconciliation are outside the implemented core workflows. Their old placeholder pages now explicitly say they are unavailable instead of pretending to save data.
- Money columns are exact NUMERIC(14, 2) since Alembic revision 0002_exact_money (see backend/README.md). Ingredient quantities and unit costs remain floating point.
- Timestamps remain UTC in storage; business-day reporting converts BUSINESS_TIMEZONE (Africa/Nairobi by default) to UTC boundaries. Set this to the business location.
- Daily summary storage is available, but live reports are authoritative; scheduled historical stock snapshots are not implemented.
- Printer byte delivery and failure paths are tested with a mocked socket. No automatic cashless provider verification exists, as requested.
