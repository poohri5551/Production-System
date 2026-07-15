import unittest
from pathlib import Path

from setting_die_services import setting_die_process_eligible, setting_die_record_complete


ROOT = Path(__file__).resolve().parents[1]


class SettingDieSequenceTests(unittest.TestCase):
    def test_process_one_is_always_eligible(self):
        self.assertTrue(setting_die_process_eligible(1))

    def test_later_process_requires_previous_valid_saved_record(self):
        self.assertFalse(setting_die_process_eligible(2, None))
        self.assertFalse(setting_die_process_eligible(2, {"id": 10, "time_start": None}))
        self.assertTrue(setting_die_process_eligible(2, {"id": 10, "time_start": "2026-07-14 08:00:00"}))

    def test_valid_saved_record_requires_id_and_required_start_time(self):
        self.assertFalse(setting_die_record_complete({"id": 10}))
        self.assertFalse(setting_die_record_complete({"time_start": "2026-07-14 08:00:00"}))
        self.assertTrue(setting_die_record_complete({"id": 10, "time_start": "2026-07-14 08:00:00"}))

    def test_submit_endpoint_uses_defensive_sequence_guard_before_insert(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        endpoint = source[source.index("def add_setting_die():"):source.index("def get_production_start_plans():")]
        guard = endpoint.index("if not setting_die_process_eligible(process_die_no, previous_process):")
        insert = endpoint.index("INSERT INTO setting_dies")
        self.assertLess(guard, insert)
        self.assertIn("AND deleted_at IS NULL", endpoint)
        self.assertIn("SELECT id, time_start", endpoint)
        self.assertIn("Complete Process Die {process_die_no - 1} first", endpoint)


if __name__ == "__main__":
    unittest.main()
