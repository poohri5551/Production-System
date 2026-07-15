import unittest
from pathlib import Path

from workflow_services import (
    can_approve_correction,
    correction_requires_approval,
    downstream_stage,
    qc_revision_current,
)


ROOT = Path(__file__).resolve().parents[1]


class WorkflowStateTests(unittest.TestCase):
    def test_qc_lifecycle_classification(self):
        self.assertEqual(downstream_stage({"status": "Waiting"}), "qc_not_started")
        self.assertEqual(downstream_stage({"status": "Waiting", "time_start": "2026-01-01"}), "qc_in_progress")
        self.assertEqual(downstream_stage({"status": "Pass"}), "qc_passed")
        self.assertEqual(downstream_stage({"status": "Pass"}, {"id": 2}), "production_start")
        self.assertEqual(downstream_stage({"status": "Pass"}, {"id": 2}, {"id": 3}), "production_finish")

    def test_late_stages_require_actual_approver(self):
        self.assertFalse(correction_requires_approval("qc_not_started"))
        self.assertFalse(correction_requires_approval("qc_in_progress"))
        self.assertTrue(correction_requires_approval("qc_passed"))
        self.assertTrue(correction_requires_approval("production_start"))
        self.assertTrue(correction_requires_approval("production_finish"))
        self.assertTrue(can_approve_correction("Admin"))
        self.assertTrue(can_approve_correction("Sup"))
        self.assertFalse(can_approve_correction("Technician"))
        self.assertFalse(can_approve_correction("Supervisor"))

    def test_qc_revision_must_match_current_setting_die_revision(self):
        self.assertTrue(qc_revision_current({"setting_die_revision": 2}, 2))
        self.assertFalse(qc_revision_current({"setting_die_revision": 1}, 2))
        self.assertFalse(qc_revision_current(None, 2))


class WorkflowImplementationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = (ROOT / "app.py").read_text(encoding="utf-8")
        cls.migration = (ROOT / "migrations" / "006_one_shot_handoffs_and_setting_die_corrections.sql").read_text(encoding="utf-8")

    def test_migration_has_durable_handoffs_revisions_and_single_active_correction(self):
        self.assertIn("setting_die_sent_at DATETIME NULL", self.migration)
        self.assertIn("operator_notified_at DATETIME NULL", self.migration)
        self.assertIn("setting_die_revision INT NOT NULL DEFAULT 1", self.migration)
        self.assertIn("idx_finish_plan_setting_revision", self.migration)
        self.assertIn("setting_die_corrections", self.migration)
        self.assertIn("uq_setting_die_correction_active_plan", self.migration)
        self.assertIn("status IN ('pending_approval', 'open')", self.migration)
        self.assertIn("uq_notifications_event_key", self.migration)

    def test_initial_handoffs_lock_plan_before_authoritative_marker_check(self):
        self.assertIn("fetch_workflow_plan(cursor, plan_id=plan_id, lot_no=lot_no, for_update=True)", self.app)
        self.assertIn("if plan.get('setting_die_sent_at'):", self.app)
        self.assertIn('"already_sent": True', self.app)
        self.assertIn("if plan.get('operator_notified_at'):", self.app)
        self.assertIn("event_key=f\"setting-die-qc-initial:{plan['id']}\"", self.app)
        self.assertIn("event_key=f\"qc-operator-initial:{plan_id}\"", self.app)

    def test_notification_read_state_is_not_handoff_state(self):
        send_block = self.app[self.app.index("def create_qc_from_setting_die"):self.app.index("def request_value")]
        operator_block = self.app[self.app.index("def create_production_start_from_qc"):self.app.index("def add_qc")]
        self.assertNotIn("is_read", send_block)
        self.assertNotIn("is_read", operator_block)

    def test_setting_die_edit_lock_and_revisioned_qc_history(self):
        self.assertIn("Setting Die is locked after the initial QC handoff", self.app)
        self.assertIn("UPDATE qc_inspections\n                SET is_finished = 1", self.app)
        self.assertIn("setting_die_revision < %s", self.app)
        self.assertIn("qc_setting_die_updated", self.app)
        self.assertIn("setting-die-qc-update:", self.app)

    def test_downstream_progress_requires_current_revision_qc_pass(self):
        self.assertIn("def current_revision_qc_pass", self.app)
        self.assertIn("q.setting_die_revision = p.setting_die_revision", self.app)
        self.assertIn("Current Setting Die revision requires a current QC Pass", self.app)
        self.assertIn("Production Finish is blocked by a newer Setting Die revision", self.app)
        self.assertIn("Production Finish is based on an obsolete Setting Die revision", self.app)


if __name__ == "__main__":
    unittest.main()
