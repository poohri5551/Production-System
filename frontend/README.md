# Vue Frontend Migration

This folder contains the Vue 3 + Vite + Tailwind CSS frontend for the existing Flask + MySQL inventory/production system.

The legacy Flask pages are intentionally preserved:

- `templates/login.html`
- `templates/mainpage.html`
- `/`
- `/mainpage`

No database schema, backend credentials, or existing API endpoints are changed.

## Current Scope

- Vue 3 Composition API app
- Vite dev server
- Tailwind CSS setup
- Login page that posts `FormData` to `/api/login`
- Dashboard shell after login
- Sidebar/topbar layout
- Role-aware Users menu visibility
- Simple localStorage auth guard
- Production & Job list migrated in Vue
- QC, Production Start, Production Finish, and Users remain placeholders

## Production Phase 2

The Production & Job list menu now uses Vue components and existing Flask APIs:

- `GET /api/jobs`
- `GET /api/jobs/<id>`
- `POST /api/production`
- `POST /api/jobs/<id>/accept`
- `POST /api/jobs/bulk_delete`

The add form preserves backend field names:

- `prod-date`
- `prod-zone`
- `prod-part-no`
- `prod-image`
- `prod-die-no`
- `prod-qty`

Setting Die is intentionally still a placeholder because that workflow belongs to a later migration phase.

## Run Flask Backend

From the project root:

```powershell
python app.py
```

If `python` is not in PATH, run with the Python executable you normally use for this Flask project.

Backend URL:

```text
http://localhost:5000
```

Legacy pages:

```text
http://localhost:5000/
http://localhost:5000/mainpage
```

## Run Vue Frontend

Install Node.js first if `node` and `npm` are not available.

From `frontend/`:

```powershell
npm install
npm run dev
```

Frontend URL:

```text
http://localhost:5173
```

Vite proxies these paths to Flask:

- `/api` to `http://localhost:5000`
- `/static` to `http://localhost:5000`

## Test Login and Production

1. Start Flask backend on port `5000`.
2. Start Vue frontend with `npm run dev`.
3. Open `http://localhost:5173`.
4. Login with an existing user from MySQL `inventory_db.users`.
5. Confirm localStorage has `currentUser` and `currentUserRole`.
6. Open `Production & Job list`.
7. Confirm the table loads from MySQL through Flask.
8. Test zone, part no, and die no filters.
9. Add a Production plan, including image upload if needed.
10. Accept a pending job.
11. Open job detail.
12. Bulk delete selected jobs with admin password.

## Not Migrated Yet

- QC forms/tables
- Production Start forms/tables
- Production Finish forms/tables
- Users management forms/tables
- Setting Die workflow

These remain available in the existing Flask templates until future phases.

## Suggested Phase 3 Prompt

Migrate only the QC module from `templates/mainpage.html` into Vue. Keep Flask APIs unchanged, preserve field names, use `src/api/client.js`, and leave Production Start/Finish/Users as placeholders.
