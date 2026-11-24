# Biashara360 Backend

FastAPI backend for restaurant POS, payments, stock, car wash, dashboards and reports.

## Start on Windows (PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe run.py
```

These commands use the virtual environment directly; activation and Pipenv are not required.

## Start on Linux or WSL

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

Open `http://127.0.0.1:8000/docs`. The initial director login is `director@gmail.com` / `director123`. Startup also creates Manager, Cashier, Store Manager and Car Wash Manager accounts; see [the account list](../frontend/README.md).
Account passwords can be updated through `PUT /api/admin/users/{id}`. Existing accounts and changed passwords are preserved on restart.

## Important behavior

- JWT access and refresh tokens with role-based authorization.
- Roles: waiter, cashier, manager, director.
- Server calculates order totals using stored menu prices; clients cannot set totals.
- Payments must exactly match the order total and duplicate payments are rejected.
- CORS permits the Vite and Live Server origins configured in `.env`.
- SQLite works by default. Set `DATABASE_URL=postgresql+psycopg://user:pass@host/db` for PostgreSQL.

Run tests with `pytest -q`. To run the same suite on PostgreSQL, point it at a disposable
database (every table in it is dropped first):

```bash
TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost/biashara_test pytest -q
```

## Money

Amounts (prices, totals, payments, shifts, refunds, daily summaries) are stored as exact
`NUMERIC(14, 2)` values and handled as Python `Decimal`, rounded half-up to cents
(`app.database.Money`). API responses still return plain JSON numbers. Request amounts with
more than two decimal places are rejected with 422. Ingredient quantities and unit costs
remain floating point.

## Database upgrades

Startup brings the database up to date automatically (`app/migrations.py`):

- an empty database is created from the models and marked current;
- a database from before Alembic runs the frozen legacy steps (`app/legacy_migrations.py`),
  then the Alembic revisions;
- SQLite files get a backup next to the database before any change.

New schema changes are Alembic revisions in `alembic_migrations/versions`, written with
`alembic revision -m "describe the change"` from `backend/`. Check `alembic current` to see a
database's revision. `/ready` returns 503 until the schema is at the newest revision.

## Branches

Every operational record (tables, bills, payments, kitchen lines, cashier shifts, refunds,
stock, recipes, car-wash bays and washes, daily summaries) belongs to a branch.
`app/branching.py` does this automatically for every request:

- Staff work in their own branch (`users.branch_id`). A director without a branch can see
  all branches, or work in one by sending the `X-Branch-Id` header (the app's branch picker
  does this).
- Reads only return the request's branch; new records are stamped with it. When a
  director views all branches and more than one is open, creating a record asks them to
  pick a branch first.
- The menu, categories, departments, car-wash service prices and suppliers are shared.
  Each branch can switch menu items off (`PUT /api/branches/{id}/menu/{item}`).
- Upgrading puts all existing records and non-director staff in "Main branch".
- Staff of a closed branch cannot work until it is reopened or they are moved.

Known limit: department printer addresses are still shared, so two branches cannot yet
print to different kitchen printers for the same department.

## Sign-in protection

- Five failed sign-ins for one email from one address within 15 minutes block further
  attempts for that pair until the window passes (HTTP 429). The counter is kept in server
  memory, so it is per process and resets on restart.
- With `ENVIRONMENT=production`, startup deactivates any initial account (director@gmail.com
  and the others below) that still has its default password. Create a real director with
  `python -m app.ops create-admin` before going live.

See [integration and operations handover](../INTEGRATION_HANDOVER.md) for migrations, manual cashless confirmation, printer setup, backups and production configuration.
