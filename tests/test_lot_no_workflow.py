import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OLD_IDENTIFIER = re.compile(r"plan_no|planNo|Plan No\.?|PLAN No\.?|PLAN NO\.?")


class LotNoWorkflowContractTests(unittest.TestCase):
    def read(self, relative_path):
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_current_application_contract_has_no_old_business_identifier(self):
        roots = [ROOT / "app.py", ROOT / "part_services.py", ROOT / "frontend" / "src", ROOT / "templates"]
        offenders = []
        for root in roots:
            files = [root] if root.is_file() else [path for path in root.rglob("*") if path.is_file()]
            for path in files:
                text = path.read_text(encoding="utf-8")
                if OLD_IDENTIFIER.search(text):
                    offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])

    def test_internal_plan_relationship_and_entity_names_remain(self):
        source = self.read("app.py")
        self.assertIn("'plan_id': plan_id", source)
        self.assertIn("FROM production_plans", source)
        self.assertIn("Production Plan", source)

    def test_production_creation_uses_text_lot_no_contract(self):
        backend = self.read("app.py")
        frontend = self.read("frontend/src/components/ProductionFormModal.vue")
        self.assertIn("request.form.get('prod-lot-no')", backend)
        self.assertIn("INSERT INTO production_plans", backend)
        self.assertIn("(lot_no, process_die_count", backend)
        self.assertIn("formData.append('prod-lot-no', form.lotNo.trim())", frontend)
        self.assertIn('type="text"', frontend)

    def test_setting_die_has_one_read_only_canonical_lot_no(self):
        component = self.read("frontend/src/components/SettingDieModal.vue")
        self.assertEqual(component.count(">Lot No.<"), 1)
        self.assertEqual(component.count("formData.append('set-lot-no'"), 1)
        self.assertIn('v-model="form.lotNo" type="text" required readonly', component)
        self.assertIn("form.lotNo = setting.lot_no || props.job?.lot_no || ''", component)

    def test_workflow_forms_and_api_use_one_lot_no_field(self):
        expectations = {
            "frontend/src/components/QCFormModal.vue": "qc-lot-no",
            "frontend/src/components/ProductionStartFormModal.vue": "start-lot-no",
            "frontend/src/components/ProductionFinishFormModal.vue": "finish-lot-no",
        }
        for path, field in expectations.items():
            with self.subTest(path=path):
                source = self.read(path)
                self.assertEqual(source.count(f"formData.append('{field}'"), 1)

        client = self.read("frontend/src/api/client.js")
        self.assertIn("?lot_no=", client)
        self.assertNotIn("?plan_no=", client)

    def test_notifications_use_structured_lot_no_and_new_lot_text(self):
        source = self.read("app.py")
        self.assertIn("target_role, type, lot_no, is_read", source)
        self.assertIn('message=f"Lot No. {', source)

    def test_migration_guards_conflicts_and_preserves_string_values(self):
        migration = self.read("migrations/005_replace_plan_no_with_canonical_lot_no.sql")
        self.assertIn("migration 005 aborted before consolidation", migration)
        self.assertIn("BINARY TRIM(lot_no) <> BINARY TRIM(plan_no)", migration)
        for table in ("setting_dies", "qc_inspections", "production_starts", "production_finishes"):
            self.assertIn(f"UPDATE {table} SET lot_no = plan_no;", migration)
        self.assertIn("CHANGE COLUMN plan_no lot_no VARCHAR(100)", migration)
        self.assertIn("DROP COLUMN plan_no", migration)
        self.assertNotRegex(migration, r"lot_no\s+(?:INT|BIGINT)\b")


if __name__ == "__main__":
    unittest.main()
