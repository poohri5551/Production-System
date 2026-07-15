-- Migration 006: durable one-shot handoffs and revisioned Setting Die corrections.
-- Existing workflow data is treated as revision 1. Existing QC/Production Start
-- rows infer that their corresponding initial handoff already occurred.

ALTER TABLE production_plans
    ADD COLUMN setting_die_revision INT NOT NULL DEFAULT 1,
    ADD COLUMN setting_die_sent_at DATETIME NULL,
    ADD COLUMN setting_die_sent_by_user_id INT NULL,
    ADD COLUMN setting_die_sent_by_username VARCHAR(80) NULL,
    ADD COLUMN operator_notified_at DATETIME NULL,
    ADD COLUMN operator_notified_by_user_id INT NULL,
    ADD COLUMN operator_notified_by_username VARCHAR(80) NULL,
    ADD INDEX idx_production_plans_setting_die_sent (setting_die_sent_at),
    ADD INDEX idx_production_plans_operator_notified (operator_notified_at);

ALTER TABLE qc_inspections
    ADD COLUMN setting_die_revision INT NOT NULL DEFAULT 1,
    ADD INDEX idx_qc_plan_setting_revision (plan_id, setting_die_revision);

ALTER TABLE production_starts
    ADD COLUMN setting_die_revision INT NOT NULL DEFAULT 1,
    ADD COLUMN qc_inspection_id INT NULL,
    ADD INDEX idx_start_plan_setting_revision (plan_id, setting_die_revision),
    ADD INDEX idx_start_qc_inspection (qc_inspection_id);

ALTER TABLE production_finishes
    ADD COLUMN setting_die_revision INT NOT NULL DEFAULT 1,
    ADD INDEX idx_finish_plan_setting_revision (plan_id, setting_die_revision);

ALTER TABLE notifications
    ADD COLUMN event_key VARCHAR(191) NULL,
    ADD UNIQUE INDEX uq_notifications_event_key (event_key);

CREATE TABLE setting_die_corrections (
    id INT NOT NULL AUTO_INCREMENT,
    plan_id INT NOT NULL,
    base_revision INT NOT NULL,
    target_revision INT NOT NULL,
    reason TEXT NOT NULL,
    status ENUM('pending_approval', 'open', 'completed', 'rejected') NOT NULL,
    downstream_stage VARCHAR(40) NOT NULL,
    approval_required TINYINT NOT NULL DEFAULT 0,
    requested_by_user_id INT NULL,
    requested_by_username VARCHAR(80) NULL,
    requested_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    approved_by_user_id INT NULL,
    approved_by_username VARCHAR(80) NULL,
    approved_at DATETIME NULL,
    rejected_by_user_id INT NULL,
    rejected_by_username VARCHAR(80) NULL,
    rejected_at DATETIME NULL,
    rejection_reason TEXT NULL,
    completed_by_user_id INT NULL,
    completed_by_username VARCHAR(80) NULL,
    completed_at DATETIME NULL,
    active_plan_id INT AS (
        CASE WHEN status IN ('pending_approval', 'open') THEN plan_id ELSE NULL END
    ) STORED,
    PRIMARY KEY (id),
    UNIQUE KEY uq_setting_die_correction_active_plan (active_plan_id),
    KEY idx_setting_die_corrections_plan_created (plan_id, requested_at),
    CONSTRAINT fk_setting_die_corrections_plan
        FOREIGN KEY (plan_id) REFERENCES production_plans (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE workflow_events (
    id INT NOT NULL AUTO_INCREMENT,
    plan_id INT NOT NULL,
    event_key VARCHAR(191) NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    setting_die_revision INT NULL,
    actor_user_id INT NULL,
    actor_username VARCHAR(80) NULL,
    reason TEXT NULL,
    metadata_text TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_workflow_events_event_key (event_key),
    KEY idx_workflow_events_plan_created (plan_id, created_at),
    CONSTRAINT fk_workflow_events_plan
        FOREIGN KEY (plan_id) REFERENCES production_plans (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

UPDATE production_plans
SET setting_die_revision = 1
WHERE setting_die_revision IS NULL OR setting_die_revision < 1;

UPDATE qc_inspections
SET setting_die_revision = 1
WHERE setting_die_revision IS NULL OR setting_die_revision < 1;

UPDATE production_starts
SET setting_die_revision = 1
WHERE setting_die_revision IS NULL OR setting_die_revision < 1;

UPDATE production_finishes
SET setting_die_revision = 1
WHERE setting_die_revision IS NULL OR setting_die_revision < 1;

UPDATE production_plans p
JOIN (
    SELECT plan_id, MIN(created_at) AS sent_at
    FROM qc_inspections
    WHERE plan_id IS NOT NULL
    GROUP BY plan_id
) q ON q.plan_id = p.id
SET p.setting_die_sent_at = COALESCE(p.setting_die_sent_at, q.sent_at);

UPDATE production_plans p
JOIN (
    SELECT plan_id, MIN(created_at) AS notified_at
    FROM production_starts
    WHERE plan_id IS NOT NULL
    GROUP BY plan_id
) s ON s.plan_id = p.id
SET p.operator_notified_at = COALESCE(p.operator_notified_at, s.notified_at);
