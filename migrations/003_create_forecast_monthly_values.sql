-- Reviewed monthly FORECAST migration. Apply separately after approval.
-- This migration seeds July 2026 from legacy columns without overwriting any
-- already-migrated monthly row. Runtime code derives Q'ty/Lot; it is not stored.

CREATE TABLE IF NOT EXISTS forecast_monthly_values (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    forecast_entry_id INT NOT NULL,
    forecast_month DATE NOT NULL,
    source_label VARCHAR(20) NOT NULL,
    quantity DECIMAL(30, 10) NOT NULL,
    lot_count INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    lot_updated_at DATETIME NULL,
    lot_updated_by_user_id INT NULL,
    lot_updated_by_username VARCHAR(100) NULL,
    UNIQUE KEY uq_forecast_monthly_entry_month
        (forecast_entry_id, forecast_month),
    KEY idx_forecast_monthly_month (forecast_month, forecast_entry_id),
    CONSTRAINT fk_forecast_monthly_entry
        FOREIGN KEY (forecast_entry_id) REFERENCES forecast_entries(id)
        ON DELETE RESTRICT,
    CONSTRAINT chk_forecast_monthly_lot_count
        CHECK (lot_count IS NULL OR lot_count >= 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO forecast_monthly_values (
    forecast_entry_id,
    forecast_month,
    source_label,
    quantity,
    lot_count,
    created_at,
    updated_at,
    lot_updated_at,
    lot_updated_by_user_id,
    lot_updated_by_username
)
SELECT
    id,
    DATE('2026-07-01'),
    'Jul-69',
    forecast_quantity,
    lot_count,
    created_at,
    updated_at,
    lot_updated_at,
    lot_updated_by_user_id,
    lot_updated_by_username
FROM forecast_entries;

-- Legacy values remain as a rollback/audit snapshot. New parent rows may have
-- no legacy single-month quantity; monthly runtime data lives only in child rows.
ALTER TABLE forecast_entries
    MODIFY forecast_quantity DECIMAL(30, 10) NULL;

CREATE TABLE IF NOT EXISTS forecast_sync_state (
    id TINYINT NOT NULL PRIMARY KEY,
    source_path VARCHAR(1024) NOT NULL,
    last_seen_sha256 CHAR(64) NULL,
    last_successful_sha256 CHAR(64) NULL,
    last_success_at DATETIME NULL,
    last_attempt_at DATETIME NULL,
    last_status VARCHAR(40) NOT NULL,
    last_error TEXT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT chk_forecast_sync_singleton CHECK (id = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
