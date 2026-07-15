import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forecast_sync_services import (  # noqa: E402,F401
    ForecastImportError,
    ForecastStructuralDriftError,
    find_duplicate_source_identities,
    normalize_forecast_month,
    parse_forecast_quantity,
    parse_workbook,
    source_identity,
    sync_workbook,
)


DEFAULT_WORKBOOK = Path(
    os.environ.get(
        "FORECAST_SOURCE_PATH",
        ROOT / "forecast_source" / "1.FORCASE CENTOR.xlsx",
    )
)


def run_import(workbook_path, apply=False, connection_factory=None):
    options = {"apply": apply}
    if connection_factory is not None:
        options["connection_factory"] = connection_factory
    return sync_workbook(workbook_path, **options)


def print_report(report):
    print(f"Mode: {report['mode']}")
    print(f"Workbook SHA-256: {report['workbook_sha256']}")
    print(f"Worksheet: {report['selected_worksheet']}")
    print("Discovered months:")
    for month in report["discovered_months"]:
        print(f"  {month['column_letter']} -> {month['source_label']} -> {month['month']}")
    print(f"Total boundary: {report['total_column_letter']}3 -> Total")
    for key in (
        "source_rows",
        "monthly_quantity_values",
        "invalid_rows",
        "repeated_part_no_rows",
        "true_duplicate_source_identity_rows",
        "parent_inserts",
        "parent_updates",
        "parent_unchanged",
        "monthly_inserts",
        "monthly_updates",
        "monthly_unchanged",
        "stale_parents",
        "months_discovered",
        "months_active",
        "months_activated",
        "months_reactivated",
        "months_deactivated",
        "months_unchanged",
        "database_writes",
    ):
        print(f"{key}: {report[key]}")
    print("Structural drift:", json.dumps(report["structural_drift"], default=str, sort_keys=True))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Validate or synchronize monthly FORECAST data.")
    parser.add_argument("--workbook", default=str(DEFAULT_WORKBOOK))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Validate and report without writes (default).")
    mode.add_argument("--apply", action="store_true", help="Apply one transaction after separate approval.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        report = run_import(args.workbook, apply=args.apply)
        print_report(report)
        return 0
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
