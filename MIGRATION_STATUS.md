# Vue Migration Status

## Completed

- Phase 1: Vue 3 + Vite + Tailwind shell, login flow, localStorage auth handoff.
- Phase 2: Production & Job list migrated to Vue.
- Phase 2.5: Production actions, Setting Die, and soft delete behavior fixed.
- Phase 2.6: Production detail modal scrolling and optional Setting Die time fields.
- Phase 3: QC Inspection migrated to Vue.
- Phase 4: Production Start migrated to Vue.
- Phase 4.5: QC Plan dropdown behavior corrected.
- Phase 5: Production Finish migrated to Vue.
- Phase 5.1: Production Finish dropdown/backend guard restricted to confirmed starts.
- Phase 6: Users Management migrated to Vue.
- Phase 7: Final regression, UI polish, users smoke test, and documentation.
- Phase 8: Flask serves Vue production build safely at `/app` with legacy rollback routes preserved.
- Phase 8.1: Default `/` route redirects to Vue `/app`; legacy login remains available at `/legacy-login`.
- Home Dashboard Phase 1-5: Flow/schema review, read-only dashboard API, Vue Home Dashboard, polish, smoke checks, and documentation.
- Admin safety hardening: Last Admin delete/demote protection, session-backed password checks, and server-only emergency Admin bootstrap script.
- Users Management password reset: Admin-only password reset endpoint and Vue modal; password hashes are never returned to the frontend.

## Active Modules In Vue

- Home Dashboard for Part/Plan status tracking
- Production & Job list
- Setting Die
- QC Inspection
- Production Start
- Production Finish
- Users Management

## Legacy Kept Intact

- `templates/login.html`
- `templates/mainpage.html`
- Flask route `/`
- Flask route `/mainpage`
- Existing Flask API endpoints under `/api`

## Production Integration

- Default landing URL: `/` redirects to `/app`
- Vue production URL: `/app`
- Vue production assets: `/app/assets/...`
- API base remains `/api/*`
- Uploaded images remain `/static/uploads/...`
- Legacy rollback remains `/legacy-login` and `/mainpage`

## Backend And Database Notes

- MySQL remains the source of truth.
- Home Dashboard APIs are read-only: `/api/dashboard/parts-status` and `/api/dashboard/parts-status/<plan_id>`.
- Home Dashboard added no migration or schema change.
- Home Dashboard does not change the existing workflow or route behavior.
- Sup, Manager, and Admin users can view the dashboard through the existing Home page.
- No Phase 7 schema changes were made.
- No Phase 8 schema changes were made.
- `db_config` remains unchanged.
- Existing soft-delete behavior is preserved for production/QC/start/finish records.
- Users delete behavior remains the existing backend behavior, including the main `admin` guard.
- User management now also blocks deleting or demoting the last Admin account.
- Admin users can reset user passwords without changing user id, username, role, or created_at.
- Emergency Admin recovery is available only through `scripts/bootstrap_admin.py`; no public bootstrap route/API was added.

## Suggested Next Step

If future rollback control is needed, add an explicit environment flag to switch the default `/` route between Vue and the legacy login without editing code.
