INSERT INTO parts (id, part_no) VALUES (9001, 'LOT-MIGRATION-PART');

INSERT INTO production_plans
    (id, prod_date, zone, part_no, part_id, die_no, qty, status, plan_no, process_die_count)
VALUES
    (9101, '2026-07-14', 'A', 'LOT-MIGRATION-PART', 9001, 'DIE-01', 100, 'accepted', '0718301', 3);

-- Safe Setting Die classifications: NULL, empty, and equal legacy lot_no.
INSERT INTO setting_dies
    (id, plan_id, part_id, part_no, lot_no, die_no, plan_no, process_die_no, time_start)
VALUES
    (9201, 9101, 9001, 'LOT-MIGRATION-PART', NULL, 'DIE-01', '0718301', 1, '2026-07-14 08:00:00'),
    (9202, 9101, 9001, 'LOT-MIGRATION-PART', '', 'DIE-01', '0718301', 2, '2026-07-14 08:10:00'),
    (9203, 9101, 9001, 'LOT-MIGRATION-PART', '0718301', 'DIE-01', '0718301', 3, '2026-07-14 08:20:00');

INSERT INTO qc_inspections
    (id, plan_id, part_id, lot_no, plan_no, part_no, status)
VALUES
    (9301, 9101, 9001, NULL, '0718301', 'LOT-MIGRATION-PART', 'Pass');

INSERT INTO production_starts
    (id, plan_id, part_id, plan_no, lot_no, part_no, die_no, qty, confirm_status)
VALUES
    (9401, 9101, 9001, '0718301', '', 'LOT-MIGRATION-PART', 'DIE-01', '100', 'confirmed');

INSERT INTO production_finishes
    (id, plan_id, part_id, plan_no, lot_no, part_no, die_no, planned_qty, actual_qty)
VALUES
    (9501, 9101, 9001, '0718301', '0718301', 'LOT-MIGRATION-PART', 'DIE-01', '100', '99');

INSERT INTO notifications
    (id, target_role, type, title, message, plan_id, plan_no, part_no, is_read)
VALUES
    (9601, 'Operator', 'lot_migration_test', 'Fixture', 'Historical neutral fixture', 9101, '0718301', 'LOT-MIGRATION-PART', 0);
