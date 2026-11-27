# Biashara360 Frontend

React/Vite interface with one sign-in page and role-based workspaces.

```powershell
npm.cmd install
npm.cmd run dev
```

Start the backend on port 8000 first. The frontend defaults to `http://127.0.0.1:8000`; set `VITE_API_URL` to change this.

## Entry flow

1. `/` is the public landing page. Sign in opens the one sign-in page at `/login`.
2. Everyone signs in on that page with their email address and password. There is no role to choose.
3. `POST /auth/login` checks the credentials. `GET /auth/me` returns the account and its role.
4. The app opens the workspace for that role. Route guards block every other role's pages, and the server checks the role on every request. An authorized deep link is restored after login.
5. Old links such as `/login/cashier` open the same sign-in page.

| Role | Opens at | Initial email | Initial password |
| --- | --- | --- | --- |
| Director | `/director` | director@gmail.com | director123 |
| Manager | `/manager` | manager@gmail.com | manager123 |
| Cashier | `/cashier` | cashier@gmail.com | cashier123 |
| Waiter | `/waiter` | waiter@gmail.com | waiter123 |
| Store Manager | `/store_manager` | store@gmail.com | store123 |
| Car Wash Manager | `/carwash_manager` | carwash@gmail.com | carwash123 |

In development mode, the backend creates missing initial accounts at startup and stores hashed passwords. Existing accounts and later password changes are preserved. These credentials are not bundled into the frontend or displayed on the public pages. The login request uses the existing `username` API field to submit the employee's email address.

Selecting a role does not grant permission. The backend account must match the selected role. Signed-in users cannot switch to another account's workspace through navigation. Waiters have a workspace at /waiter/orders; create their accounts through staff administration.

The app verifies stored access tokens on reload, clears expired/rejected sessions, and signs out through `POST /auth/logout`. Server logout revokes existing access and refresh sessions. If the server cannot be reached, local access still closes. A server connection failure during verification shows a retry screen without exposing the workspace.

Core dashboards and operational forms now use persisted API data. Cashless entries require manual receipt confirmation. Production hosting must serve `index.html` for frontend routes so direct links work.

```powershell
npm.cmd test
npm.cmd run build
```

See [integration handover](../INTEGRATION_HANDOVER.md) for setup and workflow verification.
