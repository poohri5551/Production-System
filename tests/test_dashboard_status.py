import unittest

from dashboard_services import (
    dashboard_bucket_for_item,
    dashboard_setting_die_progress,
    dashboard_summary,
)


class DashboardStatusTests(unittest.TestCase):
    def test_stage_drives_exactly_one_dashboard_bucket(self):
        cases = [
            ({"current_step": "Not Started", "status": "accepted"}, "waiting"),
            ({"current_step": "Setting Die", "status": "in_progress"}, "in_progress"),
            ({"current_step": "Production Start", "status": "waiting"}, "in_progress"),
            ({"current_step": "Production Start", "status": "pending"}, "in_progress"),
            ({"current_step": "Production Finish", "status": "pending"}, "in_progress"),
            ({"current_step": "QC", "status": "waiting"}, "qc"),
            ({"current_step": "Completed", "status": "completed"}, "completed"),
        ]
        for values, expected in cases:
            with self.subTest(values=values):
                self.assertEqual(
                    dashboard_bucket_for_item({**values, "is_finished": expected == "completed"}),
                    expected,
                )

    def test_summary_is_mutually_exclusive_and_balanced(self):
        items = [
            {"dashboard_bucket": "waiting"},
            {"dashboard_bucket": "in_progress"},
            {"dashboard_bucket": "in_progress"},
            {"dashboard_bucket": "qc"},
            {"dashboard_bucket": "completed"},
        ]
        summary = dashboard_summary(items)
        non_total = [summary[key] for key in ("waiting", "in_progress", "qc", "completed")]
        self.assertEqual(sum(non_total), summary["total"])
        self.assertEqual(summary["in_progress"], 2)

    def test_multi_process_setting_die_progress(self):
        self.assertEqual(dashboard_setting_die_progress(3, [1, 2]), {"completed": 2, "total": 3})

    def test_duplicate_setting_die_records_do_not_inflate_progress(self):
        self.assertEqual(dashboard_setting_die_progress(3, [1, 1, 2]), {"completed": 2, "total": 3})


if __name__ == "__main__":
    unittest.main()
