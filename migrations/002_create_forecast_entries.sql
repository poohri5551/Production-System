-- Add-only migration for PC-managed FORECAST data imported from Excel.
-- Apply separately after review. Runtime Flask startup does not create this table.
-- Workbook has no complete stable business key. Source row is the documented
-- fallback; inserting or reordering worksheet rows can break Lot preservation.

CREATE TABLE IF NOT EXISTS forecast_entries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    part_id INT NULL,
    part_no VARCHAR(100) NOT NULL,
    normalized_part_no VARCHAR(100) NOT NULL,
    forecast_quantity DECIMAL(30, 10) NOT NULL,
    lot_count INT NULL,
    source_workbook VARCHAR(255) NOT NULL,
    source_sheet VARCHAR(100) NOT NULL,
    source_row INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    lot_updated_at DATETIME NULL,
    lot_updated_by_user_id INT NULL,
    lot_updated_by_username VARCHAR(100) NULL,
    UNIQUE KEY uq_forecast_entries_source_identity
        (source_sheet, source_row, normalized_part_no),
    KEY idx_forecast_entries_normalized_part_no (normalized_part_no),
    KEY idx_forecast_entries_source_order (source_sheet, source_row, id),
    KEY idx_forecast_entries_part_id (part_id),
    CONSTRAINT fk_forecast_entries_part
        FOREIGN KEY (part_id) REFERENCES parts(id) ON DELETE SET NULL,
    CONSTRAINT chk_forecast_entries_lot_count
        CHECK (lot_count IS NULL OR lot_count >= 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
