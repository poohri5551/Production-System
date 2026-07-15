import unittest
from datetime import datetime
from pathlib import Path

from production_start_services import (
    ProductionStartValidationError,
    production_start_confirmed,
    stamp_locked_production_start_time,
    validate_production_start_identity,
)


ROOT = Path(__file__).resolve().parents[1]


class TimestampCursor:
    def __init__(self):
        self.timestamp = None
        self.rowcount = 0
        self.write_count = 0

    def execute(self, sql, _params):
        normalized = " ".join(sql.split()).upper()
        if normalized.startswith("UPDATE"):
            if self.timestamp is None:
                self.timestamp = datetime(2026, 7, 15, 9, 53, 12)
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


class ProductionStartIdentityTests(unittest.TestCase):
    def setUp(self):
        self.start = {
            "id": 41,
            "plan_id": 17,
            "part_id": 9,
            "lot_no": "033218",
            "part_no": "15505",
        }
        self.plan = {"id": 17, "lot_no": "033218", "part_no": "15505"}
        self.part = {"id": 9, "part_no": "15505"}

    def test_authoritative_identity_accepts_matching_values(self):
        validate_production_start_identity(
            self.start,
            self.plan,
            self.part,
            requested_plan_id="17",
            requested_lot_no="033218",
            requested_part_id="9",
            requested_part_no="15505",
        )

    def test_crafted_plan_lot_and_part_changes_are_rejected(self):
        mutations = (
            {"requested_plan_id": "18"},
            {"requested_lot_no": "099999"},
            {"requested_part_id": "10"},
            {"requested_part_no": "DIFFERENT"},
        )
        for payload in mutations:
            with self.subTest(payload=payload), self.assertRaises(ProductionStartValidationError):
                validate_production_start_identity(self.start, self.plan, self.part, **payload)

    def test_record_must_still_match_authoritative_plan(self):
        changed = dict(self.start, lot_no="099999")
        with self.assertRaises(ProductionStartValidationError):
            validate_production_start_identity(changed, self.plan, self.part)

    def test_confirmed_state_is_exact_and_persistent_friendly(self):
        self.assertTrue(production_start_confirmed("confirmed"))
        self.assertTrue(production_start_confirmed(" Confirmed "))
        self.assertFalse(production_start_confirmed("waiting"))
        self.assertFalse(production_start_confirmed(None))


class ProductionStartTimestampTests(unittest.TestCase):
    def test_first_stamp_writes_server_time_and_repeats_preserve_original(self):
        cursor = TimestampCursor()
        first_written, first_timestamp = stamp_locked_production_start_time(cursor, 41)
        second_written, second_timestamp = stamp_locked_production_start_time(cursor, 41)

        self.assertTrue(first_written)
        self.assertFalse(second_written)
        self.assertEqual(first_timestamp, datetime(2026, 7, 15, 9, 53, 12))
        self.assertEqual(second_timestamp, first_timestamp)
        self.assertEqual(cursor.write_count, 1)


class ProductionStartBackendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        cls.service_source = (ROOT / "production_start_services.py").read_text(encoding="utf-8")

    def test_unconfirmed_update_is_rejected_before_mutation(self):
        block = self.app_source[
            self.app_source.index("def update_confirmed_production_start"):
            self.app_source.index("def save_production_start")
        ]
        guard = block.index("production_start_not_confirmed")
        mutation = block.index("UPDATE production_starts")
        self.assertLess(guard, mutation)
        self.assertIn("FOR UPDATE", block)

    def test_normal_save_does_not_accept_or_assign_time_start(self):
        block = self.app_source[
            self.app_source.index("def update_confirmed_production_start"):
            self.app_source.index("def get_production_finishes")
        ]
        self.assertNotIn("start-time-start", block)
        update_sql = block[block.index("UPDATE production_starts"):block.index("conn.commit()")]
        self.assertNotIn("time_start =", update_sql)
        self.assertNotIn("plan_id =", update_sql)
        self.assertNotIn("lot_no =", update_sql)
        self.assertNotIn("part_id =", update_sql)
        self.assertNotIn("part_no =", update_sql)

    def test_create_uses_authoritative_identity_and_null_timestamp(self):
        block = self.app_source[
            self.app_source.index("def save_production_start"):
            self.app_source.index("def get_production_finishes")
        ]
        self.assertIn("lot_no = plan.get('lot_no')", block)
        self.assertIn("part_no = plan.get('part_no')", block)
        self.assertIn("VALUES (%s, %s, %s, %s, %s, %s, NULL", block)

    def test_confirm_and_stamp_are_one_shot_and_locked(self):
        confirm = self.app_source[
            self.app_source.index("def confirm_production_start"):
            self.app_source.index("def stamp_production_start_timestamp")
        ]
        stamp = self.app_source[
            self.app_source.index("def stamp_production_start_timestamp"):
            self.app_source.index("def bulk_delete_production_start")
        ]
        self.assertIn("already_confirmed", confirm)
        self.assertIn("COALESCE(confirm_status, 'waiting') <> 'confirmed'", confirm)
        self.assertIn("for_update=True", stamp)
        self.assertIn("FOR UPDATE", stamp)
        self.assertIn("production_start_not_confirmed", stamp)
        self.assertIn("stamp_locked_production_start_time", stamp)
        self.assertIn("= NOW()", self.service_source)
        self.assertIn("time_start IS NULL", self.service_source)

    def test_stamp_keeps_existing_permission_contract(self):
        self.assertIn("'stamp_production_start_timestamp': 'production_start.manage'", self.app_source)


if __name__ == "__main__":
    unittest.main()
