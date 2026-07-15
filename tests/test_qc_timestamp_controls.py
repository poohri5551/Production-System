import unittest
from datetime import datetime
from pathlib import Path

from qc_services import (
    QCTimestampValidationError,
    stamp_locked_qc_timestamp,
    validate_qc_identity_request,
    validate_qc_timestamp_field,
)


ROOT = Path(__file__).resolve().parents[1]


class TimestampCursor:
    def __init__(self):
        self.timestamp = None
        self.rowcount = 0
        self.write_count = 0

    def execute(self, sql, params):
        normalized = " ".join(sql.split()).upper()
        if normalized.startswith("UPDATE QC_INSPECTIONS SET"):
            if self.timestamp is None:
                self.timestamp = datetime(2026, 7, 15, 9, 11, 12)
                self.rowcount = 1
                self.write_count += 1
            else:
                self.rowcount = 0
        elif normalized.startswith("SELECT"):
            self.rowcount = 1
        else:
            raise AssertionError(f"Unexpected SQL: {sql}")

    def fetchone(self):
        return {"timestamp": self.timestamp}


class QCIdentityTests(unittest.TestCase):
    def setUp(self):
        self.plan = {"id": 17, "lot_no": "033218", "part_no": "15505"}

    def test_authoritative_identity_accepts_matching_business_values(self):
        validate_qc_identity_request(self.plan, "17", "033218", "15505")
        validate_qc_identity_request(self.plan, requested_part_no=" 15505 ")

    def test_mismatched_client_identity_is_rejected(self):
        for kwargs in (
            {"requested_plan_id": "18"},
            {"requested_lot_no": "OTHER-LOT"},
            {"requested_part_no": "OTHER-PART"},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(QCTimestampValidationError):
                    validate_qc_identity_request(self.plan, **kwargs)


class QCOneShotTimestampTests(unittest.TestCase):
    def test_only_known_qc_timestamp_fields_are_allowed(self):
        self.assertEqual(validate_qc_timestamp_field("time_start"), "time_start")
        self.assertEqual(validate_qc_timestamp_field("time_end"), "time_end")
        with self.assertRaises(QCTimestampValidationError):
            validate_qc_timestamp_field("created_at")

    def test_first_stamp_writes_server_time_and_second_preserves_original(self):
        cursor = TimestampCursor()
        first_written, first_timestamp = stamp_locked_qc_timestamp(cursor, 41, "time_start")
        second_written, second_timestamp = stamp_locked_qc_timestamp(cursor, 41, "time_start")

        self.assertTrue(first_written)
        self.assertFalse(second_written)
        self.assertEqual(first_timestamp, datetime(2026, 7, 15, 9, 11, 12))
        self.assertEqual(second_timestamp, first_timestamp)
        self.assertEqual(cursor.write_count, 1)

    def test_start_and_end_have_independent_one_shot_guards(self):
        start = TimestampCursor()
        end = TimestampCursor()
        self.assertTrue(stamp_locked_qc_timestamp(start, 41, "time_start")[0])
        self.assertTrue(stamp_locked_qc_timestamp(end, 41, "time_end")[0])
        self.assertFalse(stamp_locked_qc_timestamp(start, 41, "time_start")[0])
        self.assertFalse(stamp_locked_qc_timestamp(end, 41, "time_end")[0])


class QCBackendImplementationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "app.py").read_text(encoding="utf-8")

    def test_stamp_route_uses_plan_lock_row_lock_and_atomic_null_predicate(self):
        endpoint = self.source[self.source.index("def stamp_qc_timestamp"):self.source.index("def delete_qc")]
        self.assertGreaterEqual(endpoint.count("FOR UPDATE"), 2)
        self.assertIn("stamp_locked_qc_timestamp(cursor, qc_id, field_name)", endpoint)
        service = (ROOT / "qc_services.py").read_text(encoding="utf-8")
        self.assertIn("= NOW()", service)
        self.assertIn("IS NULL", service)

    def test_stamp_route_keeps_existing_qc_permission_contract(self):
        self.assertIn("'stamp_qc_timestamp': 'qc.manage'", self.source)

    def test_normal_create_and_update_never_read_client_timestamps(self):
        add_block = self.source[self.source.index("def add_qc"):self.source.index("def update_qc")]
        update_block = self.source[self.source.index("def update_qc"):self.source.index("def stamp_qc_timestamp")]
        for block in (add_block, update_block):
            self.assertNotIn("qc-time-start", block)
            self.assertNotIn("qc-time-end", block)
        self.assertIn("time_start, time_end", add_block)
        self.assertIn("NULL, NULL", add_block)

    def test_part_and_lot_snapshots_come_from_authoritative_plan(self):
        add_block = self.source[self.source.index("def add_qc"):self.source.index("def update_qc")]
        update_block = self.source[self.source.index("def update_qc"):self.source.index("def stamp_qc_timestamp")]
        for block in (add_block, update_block):
            self.assertIn("validate_qc_identity_request", block)
            self.assertIn("validate_plan_part_consistency(cursor, plan_id, plan.get('part_no'))", block)
            self.assertIn("plan.get('lot_no')", block)


if __name__ == "__main__":
    unittest.main()
