-- Add-only FORECAST month visibility registry migration.
-- Existing monthly values seed active registry rows. First successful shared
-- sync reconciles this initial state against validated Excel headers.

CREATE TABLE IF NOT EXISTS forecast_months (
    forecast_month DATE NOT NULL PRIMARY KEY,
    source_label VARCHAR(20) NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    first_seen_at DATETIME NOT NULL,
    last_seen_at DATETIME NOT NULL,
    deactivated_at DATETIME NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_forecast_months_active_month (is_active, forecast_month),
    CONSTRAINT chk_forecast_months_is_active CHECK (is_active IN (0, 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO forecast_months (
    forecast_month,
    source_label,
    is_active,
    first_seen_at,
    last_seen_at,
    deactivated_at
)
SELECT
    forecast_month,
    MIN(source_label),
    1,
    COALESCE(MIN(created_at), NOW()),
    COALESCE(MAX(updated_at), NOW()),
    NULL
FROM forecast_monthly_values
GROUP BY forecast_month;
