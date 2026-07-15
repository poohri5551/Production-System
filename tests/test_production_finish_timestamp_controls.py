import unittest
from datetime import datetime
from pathlib import Path

from production_finish_services import (
    ProductionFinishValidationError,
    stamp_locked_production_finish_timestamp,
    validate_production_finish_identity,
    validate_production_finish_timestamp_field,
)


ROOT = Path(__file__).resolve().parents[1]


class TimestampCursor:
    def __init__(self):
        self.timestamps = {"time_finish": None, "hold_time": None}
        self.selected_field = None
        self.rowcount = 0
        self.write_count = 0

    def execute(self, sql, _params):
        normalized = " ".join(sql.split()).lower()
        field = "time_finish" if "time_finish" in normalized else "hold_time"
        self.selected_field = field
        if normalized.startswith("update"):
            if self.timestamps[field] is None:
                self.timestamps[field] = datetime(2026, 7, 15, 10, 29 if field == "time_finish" else 35)
                self.rowcount = 1
                self.write_count += 1
            else:
                self.rowcount = 0
        elif normalized.startswith("select"):
            self.rowcount = 1
        else:
            raise AssertionError(f"Unexpected SQL: {sql}")

    def fetchone(self):
        return {"timestamp": self.timestamps[self.selected_field]}


class ProductionFinishTimestampTests(unittest.TestCase):
    def test_both_fields_use_allowlist(self):
        self.assertEqual(validate_production_finish_timestamp_field("time_finish"), "time_finish")
        self.assertEqual(validate_production_finish_timestamp_field("hold_time"), "hold_time")
        with self.assertRaises(ProductionFinishValidationError):
            validate_production_finish_timestamp_field("note")

    def test_each_timestamp_writes_once_and_preserves_original(self):
        cursor = TimestampCursor()
        for field in ("time_finish", "hold_time"):
            first_written, first_value = stamp_locked_production_finish_timestamp(cursor, 52, field)
            second_written, second_value = stamp_locked_production_finish_timestamp(cursor, 52, field)
            self.assertTrue(first_written)
            self.assertFalse(second_written)
            self.assertEqual(second_value, first_value)
        self.assertEqual(cursor.write_count, 2)

    def test_identity_must_match_authoritative_plan_and_part(self):
        finish = {"plan_id": 17, "part_id": 9, "lot_no": "033218", "part_no": "15505"}
        plan = {"id": 17, "lot_no": "033218", "part_no": "15505"}
        part = {"id": 9, "part_no": "15505"}
        validate_production_finish_identity(finish, plan, part)
        with self.assertRaises(ProductionFinishValidationError):
            validate_production_finish_identity(dict(finish, lot_no="OTHER"), plan, part)


class ProductionFinishBackendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        cls.service_source = (ROOT / "production_finish_services.py").read_text(encoding="utf-8")

    def test_normal_save_ignores_timestamp_replacement_values(self):
        block = self.app_source[
            self.app_source.index("def save_production_finish"):
            self.app_source.index("def confirm_production_finish")
        ]
        self.assertNotIn("finish-time-finish", block)
        self.assertNotIn("finish-hold-time", block)
        self.assertIn("NULL, NULL, 'pending'", block)

    def test_stamp_route_locks_identity_and_uses_null_guarded_server_time(self):
        block = self.app_source[
            self.app_source.index("def stamp_production_finish_timestamp"):
            self.app_source.index("def bulk_delete_production_finish")
        ]
        self.assertIn("for_update=True", block)
        self.assertIn("FOR UPDATE", block)
        self.assertIn("validate_production_finish_identity", block)
        self.assertIn("already_stamped", block)
        self.assertIn("stamp_locked_production_finish_timestamp", block)
        self.assertIn("= NOW()", self.service_source)
        self.assertIn("IS NULL", self.service_source)

    def test_stamp_route_keeps_manage_permission(self):
        self.assertIn("'stamp_production_finish_timestamp': 'production_finish.manage'", self.app_source)


if __name__ == "__main__":
    unittest.main()
