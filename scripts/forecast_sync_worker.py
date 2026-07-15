import logging
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forecast_sync_services import (  # noqa: E402
    ForecastImportError,
    ForecastSourceUnavailableError,
    ForecastStructuralDriftError,
    apply_sync,
    classify_sync,
    connect_database,
    load_database_state,
    load_month_registry,
    month_report,
    parse_workbook,
    planned_database_writes,
    stable_snapshot,
    workbook_sha256,
)


LOGGER = logging.getLogger("forecast-sync")
DEFAULT_SOURCE_PATH = "/forecast_source/1.FORCASE CENTOR.xlsx"
DEFAULT_INTERVAL_SECONDS = 900


def configured_interval():
    raw_value = os.environ.get("FORECAST_SYNC_INTERVAL_SECONDS", str(DEFAULT_INTERVAL_SECONDS))
    try:
        interval = int(raw_value)
    except ValueError as error:
        raise ForecastImportError("FORECAST_SYNC_INTERVAL_SECONDS must be an integer.") from error
    if interval < 5:
        raise ForecastImportError("FORECAST_SYNC_INTERVAL_SECONDS must be at least 5.")
    return interval


def read_last_successful_hash(cursor):
    cursor.execute("SELECT last_successful_sha256 FROM forecast_sync_state WHERE id=1")
    row = cursor.fetchone()
    return row.get("last_successful_sha256") if row else None


def record_sync_state(cursor, source_path, status, seen_hash=None, successful_hash=None, error=None):
    cursor.execute(
        """
        INSERT INTO forecast_sync_state
            (id, source_path, last_seen_sha256, last_successful_sha256,
             last_success_at, last_attempt_at, last_status, last_error)
        VALUES
            (1, %s, %s, %s,
             IF(%s IS NULL, NULL, NOW()), NOW(), %s, %s)
        ON DUPLICATE KEY UPDATE
            source_path=VALUES(source_path),
            last_seen_sha256=COALESCE(VALUES(last_seen_sha256), last_seen_sha256),
            last_successful_sha256=COALESCE(VALUES(last_successful_sha256), last_successful_sha256),
            last_success_at=IF(VALUES(last_successful_sha256) IS NULL,
                last_success_at, NOW()),
            last_attempt_at=NOW(),
            last_status=VALUES(last_status),
            last_error=VALUES(last_error)
        """,
        (source_path, seen_hash, successful_hash, successful_hash, status, error),
    )


def run_once(
    source_path=None,
    connection_factory=connect_database,
    stability_seconds=3.0,
):
    source_path = str(source_path or os.environ.get("FORECAST_SOURCE_PATH", DEFAULT_SOURCE_PATH))
    snapshot = None
    digest = None
    try:
        snapshot = stable_snapshot(source_path, stability_seconds=stability_seconds)
        digest = workbook_sha256(snapshot)
        connection = connection_factory()
        try:
            with connection.cursor() as cursor:
                previous = read_last_successful_hash(cursor)
                if previous == digest:
                    return {"status": "unchanged", "sha256": digest, "database_writes": 0}
                records, report = parse_workbook(
                    snapshot,
                    source_workbook_name=Path(source_path).name,
                )
                if report["invalid_rows"]:
                    raise ForecastImportError(
                        f"Workbook contains {report['invalid_rows']} invalid Part/month cells."
                    )
                parts, parents, monthly = load_database_state(cursor)
                existing_months = load_month_registry(cursor, required=True)
                plan = classify_sync(
                    records,
                    parts,
                    parents,
                    monthly,
                    existing_months=existing_months,
                    discovered_months=report.get("discovered_months"),
                )
                apply_sync(cursor, plan)
                record_sync_state(
                    cursor,
                    source_path,
                    "success",
                    seen_hash=digest,
                    successful_hash=digest,
                )
            connection.commit()
            result = {
                "status": "success",
                "sha256": digest,
                "source_rows": report["source_rows"],
                "monthly_quantity_values": report["monthly_quantity_values"],
                "database_writes": planned_database_writes(plan),
            }
            result.update(month_report(plan))
            return result
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
    except OSError as error:
        raise ForecastSourceUnavailableError(
            f"Source file is temporarily unavailable: {source_path}: {error}"
        ) from error
    finally:
        if snapshot is not None:
            snapshot.unlink(missing_ok=True)


def record_failure(source_path, status, error, digest=None, connection_factory=connect_database):
    connection = connection_factory()
    try:
        with connection.cursor() as cursor:
            record_sync_state(
                cursor,
                str(source_path),
                status,
                seen_hash=digest,
                error=str(error)[:4000],
            )
        connection.commit()
    except Exception:
        connection.rollback()
        LOGGER.exception("Could not persist FORECAST sync failure state")
    finally:
        connection.close()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    interval = configured_interval()
    source_path = os.environ.get("FORECAST_SOURCE_PATH", DEFAULT_SOURCE_PATH)
    LOGGER.info("FORECAST sync worker started; interval=%ss", interval)
    while True:
        try:
            result = run_once(source_path)
            if result["status"] == "unchanged":
                LOGGER.info("Unchanged workbook; skipped")
            else:
                LOGGER.info(
                    "FORECAST sync applied successfully; parents=%s monthly_values=%s "
                    "months_active=%s months_deactivated=%s writes=%s",
                    result["source_rows"],
                    result["monthly_quantity_values"],
                    result["months_active"],
                    result["months_deactivated"],
                    result["database_writes"],
                )
        except ForecastStructuralDriftError as error:
            LOGGER.error("Structural drift blocked: %s", error)
            record_failure(source_path, "structural_drift_blocked", error)
        except ForecastSourceUnavailableError as error:
            LOGGER.warning("FORECAST source file temporarily unavailable: %s", error)
            record_failure(source_path, "file_unavailable", error)
        except ForecastImportError as error:
            LOGGER.warning("FORECAST workbook unavailable or invalid: %s", error)
            record_failure(source_path, "validation_failure", error)
        except Exception as error:
            LOGGER.exception("FORECAST synchronization failed and rolled back")
            record_failure(source_path, "failed", error)
        time.sleep(interval)


if __name__ == "__main__":
    main()
