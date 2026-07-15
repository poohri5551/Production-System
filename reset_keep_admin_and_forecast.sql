-- PHASE DATABASE-CLEAN-FORECAST-01
-- Reviewed DELETE order for inventory_db.
--
-- Do not run this file directly. The executable entry point is:
--   python scripts/reset_keep_admin_and_forecast.py --execute \
--     --confirm DELETE_NON_FORECAST_LIVE_DATA_KEEP_ADMIN_AND_FORECAST
--
-- The helper supplies the safety controls SQL alone cannot express reliably:
--   * deterministic Admin selection and full-row preservation check
--   * full-column, ordered SHA-256 snapshot of forecast_entries
--   * foreign-key mutation-risk check
--   * transaction rollback on any mismatch
--
-- Transactional SQL core used by the helper after all gates pass:
START TRANSACTION;

DELETE FROM `notifications`;
DELETE FROM `production_finishes`;
DELETE FROM `production_starts`;
DELETE FROM `qc_inspections`;
DELETE FROM `setting_dies`;
DELETE FROM `production_plans`;
DELETE FROM `parts`;

-- The helper binds :preserved_admin_id; never substitute a username here.
DELETE FROM `users` WHERE `id` <> :preserved_admin_id;

-- The helper re-counts every cleared table, compares the complete Admin row,
-- and recomputes the forecast_entries snapshot before issuing COMMIT.
COMMIT;
