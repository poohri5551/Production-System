# Inventory Production System

Flask + MySQL backend with a Vue 3 + Vite + Tailwind CSS frontend migration.

## Current Entry Points

- Default Vue landing page: `http://127.0.0.1:5000/` redirects to `/app`
- Legacy Flask login rollback: `http://127.0.0.1:5000/legacy-login`
- Legacy Flask main page: `http://127.0.0.1:5000/mainpage`
- Vue production build served by Flask: `http://127.0.0.1:5000/app`
- Vue dev server: `http://127.0.0.1:5173/`
- Flask API base: `/api`

The Vue frontend uses the existing Vite proxy. Do not hardcode a backend host in Vue components.

## Home Dashboard

The Vue Home page now includes a read-only dashboard for Sup, Manager, and Admin users to track Part/Plan workflow status. It shows summary cards, the active Part/Plan table, and a timeline detail modal using these new endpoints:

- `GET /api/dashboard/parts-status`
- `GET /api/dashboard/parts-status/<plan_id>`

The dashboard does not change the existing production workflow, permissions, database schema, or legacy Flask pages.

## Run Backend

Set database credentials with environment variables before running locally when your MySQL/MariaDB password is not blank:

```powershell
$env:DB_HOST = "localhost"
$env:DB_PORT = "3306"
$env:DB_USER = "root"
$env:DB_PASSWORD = "<your-local-db-password>"
$env:DB_NAME = "inventory_db"
$env:FLASK_SECRET_KEY = "local-dev-secret-change-me"
```

```powershell
python app.py
```

If `python` is not on PATH in Codex, use the bundled runtime:

```powershell
C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe app.py
```

## Run Vue Frontend

```powershell
npm.cmd --prefix .\frontend run dev
```

## Build Vue Frontend

```powershell
npm.cmd --prefix .\frontend run build
```

After building, start Flask and open:

```text
http://127.0.0.1:5000/app
```

Vue production assets are served under `/app/assets/...`. API calls continue to use `/api/*`, and uploaded images continue to use `/static/uploads/...`.

## Legacy Rollback URLs

The Vue app is now the default landing page, while legacy Flask pages are still available:

- Login rollback: `http://127.0.0.1:5000/legacy-login`
- Main page rollback: `http://127.0.0.1:5000/mainpage`

## Regression Tests

See `TESTING.md` for the full checklist and commands.

## NAS Docker Deploy

See `README_DEPLOY_NAS.md` for Docker Compose deployment on Synology, QNAP, or Linux NAS.

## Safety Notes

- Configure database credentials through environment variables; do not hardcode real passwords in source code.
- Do not commit a real `.env` file.
- Do not drop, alter, or truncate database tables during normal regression.
- Keep `templates/login.html`, `templates/mainpage.html`, `/`, and `/mainpage` available until production cutover is approved.
- The full DB E2E test can reset mock data only when run with its explicit safety flag.
- The app blocks deleting or demoting the last Admin account through normal web/API flows.
- If the database is edited directly and no Admin remains, recover on the server with `scripts/bootstrap_admin.py`; do not expose this script through web/API.

## Emergency Admin Bootstrap

Run this only from the server shell when the `users` table is empty or no Admin account remains:

```powershell
python .\scripts\bootstrap_admin.py --username admin --password Admin@123
```

Codex bundled Python:

```powershell
C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe .\scripts\bootstrap_admin.py --username admin --password Admin@123
```

The script stores the password using the same password helper as the Flask login/create-user flow and never prints the password. After login succeeds, change the emergency password through the normal admin process.
