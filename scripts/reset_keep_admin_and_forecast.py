import argparse
import base64
import hashlib
import json
import os
import sys
from datetime import date, datetime, time
from decimal import Decimal

import pymysql


FORECAST_TABLE = "forecast_entries"
USERS_TABLE = "users"
CLEAR_TABLES = (
    "notifications",
    "production_finishes",
    "production_starts",
    "qc_inspections",
    "setting_dies",
    "production_plans",
    "parts",
)
CONFIRMATION = "DELETE_NON_FORECAST_LIVE_DATA_KEEP_ADMIN_AND_FORECAST"


class ResetSafetyError(RuntimeError):
    pass


def db_config():
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", "3306")),
        "user": os.environ.get("DB_USER", "root"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "database": os.environ.get("DB_NAME", "inventory_db"),
        "cursorclass": pymysql.cursors.DictCursor,
        "autocommit": False,
    }


def connect_database():
    return pymysql.connect(**db_config())


def quote_identifier(value):
    return f"`{value.replace('`', '``')}`"


def list_tables(cursor):
    cursor.execute(
        """
        SELECT TABLE_NAME
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_NAME
        """
    )
    return [row["TABLE_NAME"] for row in cursor.fetchall()]


def table_columns(cursor, table_name):
    cursor.execute(
        """
        SELECT COLUMN_NAME, ORDINAL_POSITION, DATA_TYPE, COLUMN_TYPE,
               IS_NULLABLE, COLUMN_KEY, EXTRA
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
        ORDER BY ORDINAL_POSITION
        """,
        (table_name,),
    )
    return cursor.fetchall()


def table_indexes(cursor, table_name):
    cursor.execute(
        """
        SELECT INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
        ORDER BY INDEX_NAME, SEQ_IN_INDEX
        """,
        (table_name,),
    )
    return cursor.fetchall()


def foreign_keys(cursor):
    cursor.execute(
        """
        SELECT
            kcu.CONSTRAINT_NAME,
            kcu.TABLE_NAME AS child_table,
            kcu.COLUMN_NAME AS child_column,
            kcu.REFERENCED_TABLE_NAME AS parent_table,
            kcu.REFERENCED_COLUMN_NAME AS parent_column,
            rc.DELETE_RULE,
            rc.UPDATE_RULE
        FROM information_schema.KEY_COLUMN_USAGE AS kcu
        JOIN information_schema.REFERENTIAL_CONSTRAINTS AS rc
          ON rc.CONSTRAINT_SCHEMA = kcu.CONSTRAINT_SCHEMA
         AND rc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
         AND rc.TABLE_NAME = kcu.TABLE_NAME
        WHERE kcu.CONSTRAINT_SCHEMA = DATABASE()
          AND kcu.REFERENCED_TABLE_NAME IS NOT NULL
        ORDER BY kcu.TABLE_NAME, kcu.CONSTRAINT_NAME, kcu.ORDINAL_POSITION
        """
    )
    return cursor.fetchall()


def table_counts(cursor, tables):
    counts = {}
    for table_name in tables:
        cursor.execute(
            f"SELECT COUNT(*) AS row_count FROM {quote_identifier(table_name)}"
        )
        counts[table_name] = int(cursor.fetchone()["row_count"])
    return counts


def select_admin(cursor, for_update=False):
    suffix = " FOR UPDATE" if for_update else ""
    cursor.execute(f"SELECT * FROM {quote_identifier(USERS_TABLE)} ORDER BY id{suffix}")
    users = cursor.fetchall()
    admins = [
        row for row in users
        if str(row.get("role") or "").strip().casefold() == "admin"
    ]
    if not admins:
        raise ResetSafetyError("No Admin user exists.")
    if len(admins) == 1:
        return users, admins, admins[0], "only normalized Admin role"

    exact_admins = [
        row for row in admins
        if str(row.get("username") or "").casefold() == "admin"
    ]
    if len(exact_admins) != 1:
        raise ResetSafetyError(
            "Multiple Admin users exist and username 'admin' is not unique."
        )
    return users, admins, exact_admins[0], "unique case-insensitive username admin"


def canonical_value(value):
    if value is None:
        return ["null", None]
    if isinstance(value, bytes):
        return ["bytes", base64.b64encode(value).decode("ascii")]
    if isinstance(value, Decimal):
        return ["decimal", format(value, "f")]
    if isinstance(value, datetime):
        return ["datetime", value.isoformat(sep=" ", timespec="microseconds")]
    if isinstance(value, date):
        return ["date", value.isoformat()]
    if isinstance(value, time):
        return ["time", value.isoformat(timespec="microseconds")]
    if isinstance(value, bool):
        return ["bool", value]
    if isinstance(value, int):
        return ["int", str(value)]
    if isinstance(value, float):
        return ["float", repr(value)]
    return ["text", str(value)]


def forecast_snapshot(cursor, lock=False):
    columns = table_columns(cursor, FORECAST_TABLE)
    if not columns:
        raise ResetSafetyError("forecast_entries table does not exist.")
    column_names = [column["COLUMN_NAME"] for column in columns]
    primary_columns = [
        column["COLUMN_NAME"] for column in columns if column["COLUMN_KEY"] == "PRI"
    ]
    order_columns = primary_columns or column_names
    select_columns = ", ".join(quote_identifier(name) for name in column_names)
    order_by = ", ".join(quote_identifier(name) for name in order_columns)
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        f"SELECT {select_columns} FROM {quote_identifier(FORECAST_TABLE)} "
        f"ORDER BY {order_by}{suffix}"
    )

    digest = hashlib.sha256()
    row_count = 0
    for row in cursor.fetchall():
        serialized = json.dumps(
            [canonical_value(row[name]) for name in column_names],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        digest.update(serialized.encode("utf-8"))
        digest.update(b"\n")
        row_count += 1
    return {
        "row_count": row_count,
        "sha256": digest.hexdigest(),
        "columns": column_names,
        "order_by": order_columns,
    }


def deletion_order(existing_clear_tables, constraints):
    nodes = set(existing_clear_tables)
    edges = {table_name: set() for table_name in nodes}
    indegree = {table_name: 0 for table_name in nodes}
    for constraint in constraints:
        child = constraint["child_table"]
        parent = constraint["parent_table"]
        if child in nodes and parent in nodes and parent not in edges[child]:
            edges[child].add(parent)
            indegree[parent] += 1

    ready = sorted(table_name for table_name, degree in indegree.items() if degree == 0)
    ordered = []
    while ready:
        table_name = ready.pop(0)
        ordered.append(table_name)
        for parent in sorted(edges[table_name]):
            indegree[parent] -= 1
            if indegree[parent] == 0:
                ready.append(parent)
                ready.sort()
    if len(ordered) != len(nodes):
        raise ResetSafetyError("Foreign-key cycle prevents safe DELETE order.")
    return ordered


def forecast_parent_delete_risks(cursor, constraints, selected_admin_id):
    risks = []
    targets = set(CLEAR_TABLES) | {USERS_TABLE}
    for constraint in constraints:
        if constraint["child_table"] != FORECAST_TABLE:
            continue
        if constraint["parent_table"] not in targets:
            continue
        child_column = quote_identifier(constraint["child_column"])
        parent_table = quote_identifier(constraint["parent_table"])
        parent_column = quote_identifier(constraint["parent_column"])
        where = ""
        params = ()
        if constraint["parent_table"] == USERS_TABLE:
            where = " WHERE parent_row.id <> %s"
            params = (selected_admin_id,)
        cursor.execute(
            f"SELECT COUNT(*) AS risk_count "
            f"FROM {quote_identifier(FORECAST_TABLE)} AS forecast_row "
            f"JOIN {parent_table} AS parent_row "
            f"ON forecast_row.{child_column} = parent_row.{parent_column}"
            f"{where}",
            params,
        )
        risk_count = int(cursor.fetchone()["risk_count"])
        if risk_count:
            risks.append({**constraint, "risk_count": risk_count})
    return risks


def safe_admin_summary(row):
    return {
        "id": int(row["id"]),
        "username": row.get("username"),
        "role": row.get("role"),
    }


def inspect_database(connection):
    with connection.cursor() as cursor:
        cursor.execute("SELECT DATABASE() AS database_name")
        database_name = cursor.fetchone()["database_name"]
        tables = list_tables(cursor)
        users, admins, selected_admin, selection_reason = select_admin(cursor)
        constraints = foreign_keys(cursor)
        existing_clear_tables = [table for table in CLEAR_TABLES if table in tables]
        expected_tables = set(existing_clear_tables) | {USERS_TABLE, FORECAST_TABLE}
        return {
            "database": database_name,
            "tables": tables,
            "unexpected_tables": sorted(set(tables) - expected_tables),
            "counts": table_counts(cursor, tables),
            "users_total": len(users),
            "admins": [safe_admin_summary(row) for row in admins],
            "selected_admin": safe_admin_summary(selected_admin),
            "selection_reason": selection_reason,
            "forecast_snapshot": forecast_snapshot(cursor),
            "forecast_columns": table_columns(cursor, FORECAST_TABLE),
            "forecast_indexes": table_indexes(cursor, FORECAST_TABLE),
            "foreign_keys": constraints,
            "deletion_order": deletion_order(existing_clear_tables, constraints),
            "forecast_parent_delete_risks": forecast_parent_delete_risks(
                cursor, constraints, int(selected_admin["id"])
            ),
        }


def execute_cleanup(connection):
    connection.begin()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS database_name")
            database_name = cursor.fetchone()["database_name"]
            if database_name != "inventory_db":
                raise ResetSafetyError(
                    f"Refusing cleanup for unexpected database: {database_name!r}"
                )

            tables = list_tables(cursor)
            existing_clear_tables = [table for table in CLEAR_TABLES if table in tables]
            expected_tables = set(existing_clear_tables) | {USERS_TABLE, FORECAST_TABLE}
            unexpected_tables = sorted(set(tables) - expected_tables)
            if unexpected_tables:
                raise ResetSafetyError(
                    f"Unclassified application tables exist: {unexpected_tables!r}"
                )

            users, admins, selected_admin, selection_reason = select_admin(
                cursor, for_update=True
            )
            selected_admin_id = int(selected_admin["id"])
            constraints = foreign_keys(cursor)
            risks = forecast_parent_delete_risks(
                cursor, constraints, selected_admin_id
            )
            if risks:
                raise ResetSafetyError(
                    f"Cleanup would affect forecast_entries through foreign keys: {risks!r}"
                )

            before_snapshot = forecast_snapshot(cursor, lock=True)
            order = deletion_order(existing_clear_tables, constraints)
            deleted = {}
            for table_name in order:
                cursor.execute(f"DELETE FROM {quote_identifier(table_name)}")
                deleted[table_name] = cursor.rowcount

            cursor.execute(
                f"DELETE FROM {quote_identifier(USERS_TABLE)} WHERE id <> %s",
                (selected_admin_id,),
            )
            deleted_users = cursor.rowcount

            counts = table_counts(
                cursor,
                existing_clear_tables + [USERS_TABLE, FORECAST_TABLE],
            )
            uncleared = {
                table_name: counts[table_name]
                for table_name in existing_clear_tables
                if counts[table_name] != 0
            }
            if uncleared:
                raise ResetSafetyError(f"Runtime tables not empty: {uncleared!r}")
            if counts[USERS_TABLE] != 1:
                raise ResetSafetyError(
                    f"Expected one preserved user, found {counts[USERS_TABLE]}."
                )

            cursor.execute(
                f"SELECT * FROM {quote_identifier(USERS_TABLE)} WHERE id = %s",
                (selected_admin_id,),
            )
            preserved_admin = cursor.fetchone()
            if not preserved_admin or preserved_admin != selected_admin:
                raise ResetSafetyError("Selected Admin row changed during cleanup.")

            after_snapshot = forecast_snapshot(cursor)
            if after_snapshot != before_snapshot:
                raise ResetSafetyError(
                    "forecast_entries changed inside cleanup transaction."
                )

        connection.commit()
        return {
            "database": database_name,
            "selected_admin": safe_admin_summary(selected_admin),
            "admin_selection_reason": selection_reason,
            "users_before": len(users),
            "admins_before": len(admins),
            "deleted_users": deleted_users,
            "deletion_order": order,
            "deleted_rows": deleted,
            "forecast_before": before_snapshot,
            "forecast_after_before_commit": after_snapshot,
        }
    except Exception:
        connection.rollback()
        raise


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Preserve one Admin and all FORECAST rows while clearing runtime data."
    )
    parser.add_argument("--inspect", action="store_true", help="Read-only audit (default).")
    parser.add_argument("--execute", action="store_true", help="Execute guarded cleanup.")
    parser.add_argument("--confirm", help="Required exact confirmation for --execute.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.execute and args.confirm != CONFIRMATION:
        print(
            f"ERROR: --execute requires --confirm {CONFIRMATION}",
            file=sys.stderr,
        )
        return 2

    connection = connect_database()
    try:
        result = execute_cleanup(connection) if args.execute else inspect_database(connection)
        print(json.dumps(result, ensure_ascii=False, default=str, sort_keys=True))
        return 0
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
