import os
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pymysql


DEFAULT_EXPORT_DIR = Path("/app/backups/db_excel")
INVALID_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")


def db_config():
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", "3306")),
        "user": os.environ.get("DB_USER", "root"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "database": os.environ.get("DB_NAME", "inventory_db"),
        "cursorclass": pymysql.cursors.DictCursor,
    }


def safe_sheet_name(table_name, used_names):
    base = INVALID_SHEET_CHARS.sub("_", str(table_name or "").strip())
    base = base.strip("'") or "Sheet"
    base = base[:31]

    candidate = base
    counter = 1
    while candidate in used_names:
        suffix = f"_{counter}"
        candidate = f"{base[:31 - len(suffix)]}{suffix}"
        counter += 1

    used_names.add(candidate)
    return candidate


def quote_identifier(identifier):
    return f"`{str(identifier).replace('`', '``')}`"


def fetch_tables(connection):
    with connection.cursor() as cursor:
        cursor.execute("SHOW TABLES")
        rows = cursor.fetchall()
    return [next(iter(row.values())) for row in rows]


def fetch_table_frame(connection, table_name):
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT * FROM {quote_identifier(table_name)}")
        rows = cursor.fetchall()
        columns = [column[0] for column in cursor.description or []]
    return pd.DataFrame(rows, columns=columns)


def export_dir():
    return Path(os.environ.get("EXPORT_EXCEL_DIR", DEFAULT_EXPORT_DIR))


def export_database():
    output_dir = export_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"database_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    connection = None
    try:
        connection = pymysql.connect(**db_config())
        tables = fetch_tables(connection)
        if not tables:
            raise RuntimeError("No tables found in the configured database.")

        used_sheet_names = set()
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            for table_name in tables:
                sheet_name = safe_sheet_name(table_name, used_sheet_names)
                frame = fetch_table_frame(connection, table_name)
                frame.to_excel(writer, sheet_name=sheet_name, index=False)

        print(f"Exported database to: {output_path}")
        return output_path
    finally:
        if connection:
            connection.close()


def main():
    try:
        export_database()
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
