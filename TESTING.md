# Testing Guide

## Compile Backend

```powershell
python -m py_compile app.py
```

Codex bundled Python:

```powershell
C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m py_compile .\app.py
```

## Build Vue

```powershell
npm.cmd --prefix .\frontend run build
```

## Phase 8 Flask/Vue Production Smoke

Run this after `npm.cmd --prefix .\frontend run build`:

```powershell
python .\scripts\phase8_http_smoke.py
```

Codex bundled Python:

```powershell
C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe .\scripts\phase8_http_smoke.py
```

The smoke test covers:

- default `/` redirect to Vue `/app`
- legacy `/legacy-login`
- legacy `/mainpage`
- Vue production `/app`
- Vue build assets under `/app/assets/...`
- `/api/login`
- `/static/uploads/...` when an uploaded file exists

## Home Dashboard Smoke Test

The Home Dashboard is read-only and uses only:

- `GET /api/dashboard/parts-status`
- `GET /api/dashboard/parts-status/<plan_id>`

Light API check with Codex bundled Python:

```powershell
@'
from app import app

with app.test_client() as client:
    list_response = client.get('/api/dashboard/parts-status')
    print(list_response.status_code, list_response.get_json(silent=True))

    data = list_response.get_json(silent=True) or {}
    items = data.get('items') or []
    if items:
        plan_id = items[0].get('plan_id')
        detail_response = client.get(f'/api/dashboard/parts-status/{plan_id}')
        print(detail_response.status_code, detail_response.get_json(silent=True))

    missing_response = client.get('/api/dashboard/parts-status/999999999')
    print(missing_response.status_code, missing_response.get_json(silent=True))
'@ | C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -
```

Manual UI check:

1. Open Vue at `http://127.0.0.1:5000/app` after build, or `http://127.0.0.1:5173/` during dev.
2. Login as Admin, Sup, or Manager.
3. Open Home and confirm summary cards, Part/Plan table, View modal, and timeline render.
4. Confirm API error or detail 404 displays an error state instead of crashing.

## Full DB E2E Workflow

Use this only when the database contains mock/test data. The command clears app data, keeps schema intact, and seeds `admin / 1234 / Admin`.

```powershell
python .\scripts\e2e_db_workflow_test.py --all --i-understand-this-clears-mock-db
```

Codex bundled Python:

```powershell
C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe .\scripts\e2e_db_workflow_test.py --all --i-understand-this-clears-mock-db
```

## Users API Smoke Test

Requires an existing `admin` user with password `1234`.

```powershell
python .\scripts\users_smoke_test.py
```

Codex bundled Python:

```powershell
C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe .\scripts\users_smoke_test.py
```

The smoke test covers:

- list users
- create user
- reject wrong admin password
- change role
- delete user
- protect the main `admin` user

## Reset Password Smoke Test

Checks Admin password reset behavior and verifies that reset passwords are stored as hashes, not plaintext.

```powershell
python .\scripts\reset_password_smoke_test.py
```

Codex bundled Python:

```powershell
C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe .\scripts\reset_password_smoke_test.py
```

The smoke test covers:

- Admin can reset another user's password
- stored password starts with `scrypt:` and is not plaintext
- old password login fails and new password login succeeds
- non-admin reset is rejected with `403`
- missing user, mismatched confirmation, and short password are rejected
- Admin resetting their own password is logged out immediately

Current limitation: resetting another user's password does not invalidate that user's already-open browser session across another browser/process because the current schema has no session version or password-changed timestamp. The new password is required on the next login.

## Session Security Smoke Test

Checks that deleted users cannot keep using an old browser session.

```powershell
python .\scripts\session_security_smoke_test.py
```

Codex bundled Python:

```powershell
C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe .\scripts\session_security_smoke_test.py
```

The smoke test covers:

- logged-in user deleted by another admin gets `401` on the next protected API call
- deleted user session is cleared server-side
- user deleting their own account gets `logged_out: true`
- self-deleted user gets `401` on the next protected API call

## Admin Safety Smoke Test

Checks that normal web/API flows cannot leave the system with zero Admin accounts and that the emergency bootstrap script can create a server-only Admin.

```powershell
python .\scripts\admin_safety_smoke_test.py
```

Codex bundled Python:

```powershell
C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe .\scripts\admin_safety_smoke_test.py
```

The smoke test covers:

- deleting one Admin succeeds only when another Admin remains
- demoting one Admin succeeds only when another Admin remains
- deleting the last Admin is rejected
- demoting the last Admin is rejected
- self-delete works only when another Admin remains and then logs out the session
- `scripts/bootstrap_admin.py` can create an Admin from the server shell

Emergency bootstrap command:

```powershell
python .\scripts\bootstrap_admin.py --username admin --password Admin@123
```

Do not expose `bootstrap_admin.py` through a public route, API endpoint, or browser page.

## Manual Browser Regression

1. Start Flask backend: `python app.py`
2. Start Vue frontend: `npm.cmd --prefix .\frontend run dev`
3. Open Vue at `http://127.0.0.1:5173/`
4. Login as Admin.
5. Check menus: Home, Production, QC, Production Start, Production Finish, Users.
6. Run one workflow: Production Plan -> Setting Die -> QC -> Notify Operator -> Confirm Production Start -> Production Finish -> Confirm Finish.
7. Check Users: Add User, Change Role, Delete User, wrong admin password, main admin delete guard.
8. Logout and login as Sup or Manager; Users should not appear.
9. Open legacy routes: `http://127.0.0.1:5000/legacy-login` and `http://127.0.0.1:5000/mainpage`.
10. Confirm browser console has no important errors.

## Manual Production Browser Regression

1. Build Vue: `npm.cmd --prefix .\frontend run build`
2. Start Flask backend: `python app.py`
3. Open default Vue landing: `http://127.0.0.1:5000/`
4. Open legacy main page: `http://127.0.0.1:5000/mainpage`
5. Open Vue production app: `http://127.0.0.1:5000/app`
6. Login through Vue production app.
7. Check menus: Production, QC, Production Start, Production Finish, Users.
8. Confirm JS/CSS assets load from `/app/assets/...` without 404.
9. Confirm uploaded images still load from `/static/uploads/...`.
10. Confirm browser console has no important errors.

## Workflow Assertions

- QC dropdown still shows a plan after Notify Operator until Finish is confirmed.
- Production Start dropdown excludes a plan that already has an active start.
- Production Finish dropdown shows only confirmed Production Start records.
- Confirm Finish marks active workflow records finished.
- Finished plans disappear from the QC dropdown.
- Bulk delete actions hide records from list APIs while preserving `deleted_at` soft-delete data.
