-- Add-only migration: introduce parts as the master part table.
-- This intentionally keeps existing part_no and plan_no columns for compatibility.
-- TODO(second migration): after backend writes are verified, consider tightening
-- part_id/plan_id columns that are always required to NOT NULL.

CREATE TABLE IF NOT EXISTS parts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    part_no VARCHAR(100) NOT NULL,
    normalized_part_no VARCHAR(100)
        GENERATED ALWAYS AS (UPPER(TRIM(part_no))) STORED,
    description VARCHAR(255) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at DATETIME NULL,
    UNIQUE KEY uq_parts_normalized_part_no (normalized_part_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DELIMITER //

DROP PROCEDURE IF EXISTS add_column_if_missing//
CREATE PROCEDURE add_column_if_missing(
    IN p_table_name VARCHAR(64),
    IN p_column_name VARCHAR(64),
    IN p_column_definition TEXT
)
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = p_table_name
            AND COLUMN_NAME = p_column_name
    ) THEN
        SET @ddl = CONCAT('ALTER TABLE `', p_table_name, '` ADD COLUMN ', p_column_definition);
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END//

DROP PROCEDURE IF EXISTS add_index_if_missing//
CREATE PROCEDURE add_index_if_missing(
    IN p_table_name VARCHAR(64),
    IN p_index_name VARCHAR(64),
    IN p_columns_sql TEXT
)
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = p_table_name
            AND INDEX_NAME = p_index_name
    ) THEN
        SET @ddl = CONCAT('CREATE INDEX `', p_index_name, '` ON `', p_table_name, '` (', p_columns_sql, ')');
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END//

DROP PROCEDURE IF EXISTS add_fk_if_missing//
CREATE PROCEDURE add_fk_if_missing(
    IN p_table_name VARCHAR(64),
    IN p_constraint_name VARCHAR(64),
    IN p_column_name VARCHAR(64),
    IN p_reference_sql TEXT,
    IN p_on_delete VARCHAR(20)
)
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.TABLE_CONSTRAINTS
        WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = p_table_name
            AND CONSTRAINT_NAME = p_constraint_name
            AND CONSTRAINT_TYPE = 'FOREIGN KEY'
    ) THEN
        SET @ddl = CONCAT(
            'ALTER TABLE `', p_table_name, '` ADD CONSTRAINT `', p_constraint_name,
            '` FOREIGN KEY (`', p_column_name, '`) REFERENCES ', p_reference_sql,
            ' ON DELETE ', p_on_delete
        );
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END//

DELIMITER ;

CALL add_column_if_missing('production_plans', 'part_id', '`part_id` INT NULL COMMENT ''TODO: make NOT NULL after backend part_id writes are fully verified''');
CALL add_column_if_missing('setting_dies', 'part_id', '`part_id` INT NULL COMMENT ''TODO: make NOT NULL after backend part_id writes are fully verified''');
CALL add_column_if_missing('qc_inspections', 'part_id', '`part_id` INT NULL COMMENT ''TODO: make NOT NULL after backend part_id writes are fully verified''');
CALL add_column_if_missing('production_starts', 'part_id', '`part_id` INT NULL COMMENT ''TODO: make NOT NULL after backend part_id writes are fully verified''');
CALL add_column_if_missing('production_finishes', 'part_id', '`part_id` INT NULL COMMENT ''TODO: make NOT NULL after backend part_id writes are fully verified''');

CALL add_column_if_missing('qc_inspections', 'plan_id', '`plan_id` INT NULL COMMENT ''TODO: make NOT NULL where workflow always requires a production plan''');
CALL add_column_if_missing('production_starts', 'plan_id', '`plan_id` INT NULL COMMENT ''TODO: make NOT NULL where workflow always requires a production plan''');
CALL add_column_if_missing('production_finishes', 'plan_id', '`plan_id` INT NULL COMMENT ''TODO: make NOT NULL where workflow always requires a production plan''');

CALL add_column_if_missing('production_plans', 'deleted_at', '`deleted_at` DATETIME NULL');
CALL add_column_if_missing('setting_dies', 'deleted_at', '`deleted_at` DATETIME NULL');
CALL add_column_if_missing('qc_inspections', 'deleted_at', '`deleted_at` DATETIME NULL');
CALL add_column_if_missing('production_starts', 'deleted_at', '`deleted_at` DATETIME NULL');
CALL add_column_if_missing('production_finishes', 'deleted_at', '`deleted_at` DATETIME NULL');

INSERT INTO parts (part_no)
SELECT DISTINCT TRIM(part_no)
FROM production_plans
WHERE part_no IS NOT NULL AND TRIM(part_no) <> ''
ON DUPLICATE KEY UPDATE part_no = parts.part_no;

INSERT INTO parts (part_no)
SELECT DISTINCT TRIM(part_no)
FROM setting_dies
WHERE part_no IS NOT NULL AND TRIM(part_no) <> ''
ON DUPLICATE KEY UPDATE part_no = parts.part_no;

INSERT INTO parts (part_no)
SELECT DISTINCT TRIM(part_no)
FROM qc_inspections
WHERE part_no IS NOT NULL AND TRIM(part_no) <> ''
ON DUPLICATE KEY UPDATE part_no = parts.part_no;

INSERT INTO parts (part_no)
SELECT DISTINCT TRIM(part_no)
FROM production_starts
WHERE part_no IS NOT NULL AND TRIM(part_no) <> ''
ON DUPLICATE KEY UPDATE part_no = parts.part_no;

INSERT INTO parts (part_no)
SELECT DISTINCT TRIM(part_no)
FROM production_finishes
WHERE part_no IS NOT NULL AND TRIM(part_no) <> ''
ON DUPLICATE KEY UPDATE part_no = parts.part_no;

UPDATE production_plans t
JOIN parts p ON p.normalized_part_no = UPPER(TRIM(t.part_no))
SET t.part_id = p.id
WHERE t.part_id IS NULL AND t.part_no IS NOT NULL AND TRIM(t.part_no) <> '';

UPDATE setting_dies t
JOIN parts p ON p.normalized_part_no = UPPER(TRIM(t.part_no))
SET t.part_id = p.id
WHERE t.part_id IS NULL AND t.part_no IS NOT NULL AND TRIM(t.part_no) <> '';

UPDATE qc_inspections t
JOIN parts p ON p.normalized_part_no = UPPER(TRIM(t.part_no))
SET t.part_id = p.id
WHERE t.part_id IS NULL AND t.part_no IS NOT NULL AND TRIM(t.part_no) <> '';

UPDATE production_starts t
JOIN parts p ON p.normalized_part_no = UPPER(TRIM(t.part_no))
SET t.part_id = p.id
WHERE t.part_id IS NULL AND t.part_no IS NOT NULL AND TRIM(t.part_no) <> '';

UPDATE production_finishes t
JOIN parts p ON p.normalized_part_no = UPPER(TRIM(t.part_no))
SET t.part_id = p.id
WHERE t.part_id IS NULL AND t.part_no IS NOT NULL AND TRIM(t.part_no) <> '';

UPDATE qc_inspections q
JOIN (
    SELECT plan_no, MAX(plan_id) AS plan_id
    FROM setting_dies
    WHERE plan_no IS NOT NULL AND TRIM(plan_no) <> ''
    GROUP BY plan_no
) s ON s.plan_no = q.plan_no
SET q.plan_id = s.plan_id
WHERE q.plan_id IS NULL;

UPDATE production_starts ps
JOIN (
    SELECT plan_no, MAX(plan_id) AS plan_id
    FROM setting_dies
    WHERE plan_no IS NOT NULL AND TRIM(plan_no) <> ''
    GROUP BY plan_no
) s ON s.plan_no = ps.plan_no
SET ps.plan_id = s.plan_id
WHERE ps.plan_id IS NULL;

UPDATE production_finishes pf
JOIN (
    SELECT plan_no, MAX(plan_id) AS plan_id
    FROM setting_dies
    WHERE plan_no IS NOT NULL AND TRIM(plan_no) <> ''
    GROUP BY plan_no
) s ON s.plan_no = pf.plan_no
SET pf.plan_id = s.plan_id
WHERE pf.plan_id IS NULL;

UPDATE setting_dies t
JOIN production_plans p ON p.id = t.plan_id
SET t.part_id = p.part_id
WHERE t.part_id IS NULL AND p.part_id IS NOT NULL;

UPDATE qc_inspections t
JOIN production_plans p ON p.id = t.plan_id
SET t.part_id = p.part_id
WHERE t.part_id IS NULL AND p.part_id IS NOT NULL;

UPDATE production_starts t
JOIN production_plans p ON p.id = t.plan_id
SET t.part_id = p.part_id
WHERE t.part_id IS NULL AND p.part_id IS NOT NULL;

UPDATE production_finishes t
JOIN production_plans p ON p.id = t.plan_id
SET t.part_id = p.part_id
WHERE t.part_id IS NULL AND p.part_id IS NOT NULL;

CALL add_index_if_missing('production_plans', 'idx_production_plans_part_id', '`part_id`');
CALL add_index_if_missing('setting_dies', 'idx_setting_dies_part_id', '`part_id`');
CALL add_index_if_missing('qc_inspections', 'idx_qc_inspections_part_id', '`part_id`');
CALL add_index_if_missing('production_starts', 'idx_production_starts_part_id', '`part_id`');
CALL add_index_if_missing('production_finishes', 'idx_production_finishes_part_id', '`part_id`');

CALL add_index_if_missing('qc_inspections', 'idx_qc_inspections_plan_id', '`plan_id`');
CALL add_index_if_missing('production_starts', 'idx_production_starts_plan_id', '`plan_id`');
CALL add_index_if_missing('production_finishes', 'idx_production_finishes_plan_id', '`plan_id`');
CALL add_index_if_missing('qc_inspections', 'idx_qc_inspections_plan_no', '`plan_no`');
CALL add_index_if_missing('production_starts', 'idx_production_starts_plan_no', '`plan_no`');
CALL add_index_if_missing('production_finishes', 'idx_production_finishes_plan_no', '`plan_no`');

CALL add_index_if_missing('production_plans', 'idx_production_plans_deleted_at', '`deleted_at`');
CALL add_index_if_missing('setting_dies', 'idx_setting_dies_deleted_at', '`deleted_at`');
CALL add_index_if_missing('qc_inspections', 'idx_qc_inspections_deleted_at', '`deleted_at`');
CALL add_index_if_missing('production_starts', 'idx_production_starts_deleted_at', '`deleted_at`');
CALL add_index_if_missing('production_finishes', 'idx_production_finishes_deleted_at', '`deleted_at`');

CALL add_fk_if_missing('production_plans', 'fk_production_plans_part', 'part_id', '`parts` (`id`)', 'RESTRICT');
CALL add_fk_if_missing('setting_dies', 'fk_setting_dies_part', 'part_id', '`parts` (`id`)', 'RESTRICT');
CALL add_fk_if_missing('qc_inspections', 'fk_qc_inspections_part', 'part_id', '`parts` (`id`)', 'RESTRICT');
CALL add_fk_if_missing('production_starts', 'fk_production_starts_part', 'part_id', '`parts` (`id`)', 'RESTRICT');
CALL add_fk_if_missing('production_finishes', 'fk_production_finishes_part', 'part_id', '`parts` (`id`)', 'RESTRICT');

CALL add_fk_if_missing('qc_inspections', 'fk_qc_inspections_plan', 'plan_id', '`production_plans` (`id`)', 'RESTRICT');
CALL add_fk_if_missing('production_starts', 'fk_production_starts_plan', 'plan_id', '`production_plans` (`id`)', 'RESTRICT');
-- production_finishes.plan_id uses ON DELETE SET NULL to preserve finish history if a plan is removed later.
CALL add_fk_if_missing('production_finishes', 'fk_production_finishes_plan', 'plan_id', '`production_plans` (`id`)', 'SET NULL');

DROP PROCEDURE IF EXISTS add_fk_if_missing;
DROP PROCEDURE IF EXISTS add_index_if_missing;
DROP PROCEDURE IF EXISTS add_column_if_missing;
