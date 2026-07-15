INSERT INTO parts (id, part_no) VALUES (9002, 'LOT-CONFLICT-PART');

INSERT INTO production_plans
    (id, prod_date, zone, part_no, part_id, die_no, qty, status, plan_no, process_die_count)
VALUES
    (9102, '2026-07-14', 'A', 'LOT-CONFLICT-PART', 9002, 'DIE-02', 100, 'accepted', '0718301', 1);

INSERT INTO setting_dies
    (id, plan_id, part_id, part_no, lot_no, die_no, plan_no, process_die_no, time_start)
VALUES
    (9204, 9102, 9002, 'LOT-CONFLICT-PART', 'ABC123', 'DIE-02', '0718301', 1, '2026-07-14 09:00:00');
