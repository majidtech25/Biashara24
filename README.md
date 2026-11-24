# Biashara360

Full-stack restaurant and car-wash management platform.

See [Phase 2 waiter workspace setup and verification](PHASE2_HANDOVER.md) for table configuration, bill additions, approvals and migration behavior.

- `backend/` — FastAPI, SQLAlchemy, JWT and SQLite/PostgreSQL
- `frontend/` — React, Vite, responsive role-based interface

## Run locally

Use two terminals:

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/WSL: source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Select your designation, then sign in with the matching email and password. Initial accounts are listed in [frontend/README.md](frontend/README.md).

## Car wash workflow

1. **Bay Configuration** and **Service Types**: add bays and wash services. Both can be edited or switched off; a bay with a car on it cannot be switched off.
2. **Staff & Attendants**: add the people who wash cars. They do not need a login.
3. **New Transaction**: log the car and its payment on a free bay. A bay that already has a car waiting or being washed is refused.
4. **Active Bays** (the bay board): pick an attendant and press *Start wash*, then *Finish wash* when the car leaves. The board refreshes every 15 seconds.

Washes recorded before this workflow existed are marked as done when the database is upgraded.
