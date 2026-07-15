-- Canonical production workflow business identifier migration.
-- Internal production_plans, plan_id, and production_plans.id concepts remain unchanged.
-- Run the rollout preflight immediately before this migration. This guard repeats
-- collision detection so legacy Lot No. data can never be silently discarded.

SET @workflow_lot_conflicts :=
    (SELECT COUNT(*)
     FROM setting_dies
     WHERE lot_no IS NOT NULL
       AND TRIM(lot_no) <> ''
       AND (plan_no IS NULL OR BINARY TRIM(lot_no) <> BINARY TRIM(plan_no)))
  + (SELECT COUNT(*)
     FROM qc_inspections
     WHERE lot_no IS NOT NULL
       AND TRIM(lot_no) <> ''
       AND (plan_no IS NULL OR BINARY TRIM(lot_no) <> BINARY TRIM(plan_no)))
  + (SELECT COUNT(*)
     FROM production_starts
     WHERE lot_no IS NOT NULL
       AND TRIM(lot_no) <> ''
       AND (plan_no IS NULL OR BINARY TRIM(lot_no) <> BINARY TRIM(plan_no)))
  + (SELECT COUNT(*)
     FROM production_finishes
     WHERE lot_no IS NOT NULL
       AND TRIM(lot_no) <> ''
       AND (plan_no IS NULL OR BINARY TRIM(lot_no) <> BINARY TRIM(plan_no)));

SET @workflow_lot_guard_sql := IF(
    @workflow_lot_conflicts = 0,
    'DO 0',
    'SIGNAL SQLSTATE ''45000'' SET MESSAGE_TEXT = ''Conflicting legacy Lot No. data; migration 005 aborted before consolidation'''
);
PREPARE workflow_lot_guard FROM @workflow_lot_guard_sql;
EXECUTE workflow_lot_guard;
DEALLOCATE PREPARE workflow_lot_guard;

-- Canonical value always comes from the former plan_no column. VARCHAR(100)
-- assignment preserves leading zeros and the existing maximum length.
UPDATE setting_dies SET lot_no = plan_no;
UPDATE qc_inspections SET lot_no = plan_no;
UPDATE production_starts SET lot_no = plan_no;
UPDATE production_finishes SET lot_no = plan_no;

ALTER TABLE production_plans
    DROP INDEX idx_production_plans_plan_no,
    CHANGE COLUMN plan_no lot_no VARCHAR(100) NULL,
    ADD INDEX idx_production_plans_lot_no (lot_no);

ALTER TABLE setting_dies
    DROP COLUMN plan_no,
    ADD INDEX idx_setting_dies_lot_no (lot_no);

ALTER TABLE qc_inspections
    DROP INDEX idx_qc_inspections_plan_no,
    DROP COLUMN plan_no,
    ADD INDEX idx_qc_inspections_lot_no (lot_no);

ALTER TABLE production_starts
    DROP INDEX idx_plan_no,
    DROP INDEX idx_production_starts_plan_no,
    DROP COLUMN plan_no,
    MODIFY COLUMN lot_no VARCHAR(100) NOT NULL,
    ADD INDEX idx_production_starts_lot_no (lot_no);

ALTER TABLE production_finishes
    DROP INDEX idx_plan_no,
    DROP INDEX idx_production_finishes_plan_no,
    DROP COLUMN plan_no,
    MODIFY COLUMN lot_no VARCHAR(100) NOT NULL,
    ADD INDEX idx_production_finishes_lot_no (lot_no);

ALTER TABLE notifications
    DROP INDEX idx_notifications_dedupe,
    CHANGE COLUMN plan_no lot_no VARCHAR(100) NULL,
    ADD INDEX idx_notifications_dedupe (target_role, type, lot_no, is_read);

SET @workflow_lot_conflicts := NULL;
SET @workflow_lot_guard_sql := NULL;
