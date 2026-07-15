class PartValidationError(ValueError):
    pass


class PartNotFoundError(LookupError):
    pass


def normalize_part_no(part_no):
    return (part_no or '').strip().upper()


def require_normalized_part_no(part_no):
    normalized = normalize_part_no(part_no)
    if not normalized:
        raise PartValidationError("part_no is required")
    return normalized


def run_part_transaction(conn, operation):
    try:
        with conn.cursor() as cursor:
            result = operation(cursor)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise


def _table_exists(cursor, table_name):
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
        LIMIT 1
        """,
        (table_name,),
    )
    return cursor.fetchone() is not None


def _column_exists(cursor, table_name, column_name):
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s
        LIMIT 1
        """,
        (table_name, column_name),
    )
    return cursor.fetchone() is not None


def _index_exists(cursor, table_name, index_name):
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND INDEX_NAME = %s
        LIMIT 1
        """,
        (table_name, index_name),
    )
    return cursor.fetchone() is not None


def _foreign_key_exists(cursor, table_name, constraint_name):
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.TABLE_CONSTRAINTS
        WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = %s
            AND CONSTRAINT_NAME = %s
            AND CONSTRAINT_TYPE = 'FOREIGN KEY'
        LIMIT 1
        """,
        (table_name, constraint_name),
    )
    return cursor.fetchone() is not None


def _ensure_column(cursor, table_name, column_name, column_definition):
    if _table_exists(cursor, table_name) and not _column_exists(cursor, table_name, column_name):
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_definition}")


def _ensure_index(cursor, table_name, index_name, columns_sql):
    if _table_exists(cursor, table_name) and not _index_exists(cursor, table_name, index_name):
        cursor.execute(f"CREATE INDEX {index_name} ON {table_name} ({columns_sql})")


def _ensure_foreign_key(cursor, table_name, constraint_name, column_name, reference_sql, on_delete):
    if _table_exists(cursor, table_name) and not _foreign_key_exists(cursor, table_name, constraint_name):
        cursor.execute(
            f"""
            ALTER TABLE {table_name}
            ADD CONSTRAINT {constraint_name}
            FOREIGN KEY ({column_name}) REFERENCES {reference_sql}
            ON DELETE {on_delete}
            """
        )


def ensure_parts_schema(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS parts (
            id INT AUTO_INCREMENT PRIMARY KEY,
            part_no VARCHAR(100) NOT NULL,
            normalized_part_no VARCHAR(100)
                GENERATED ALWAYS AS (UPPER(TRIM(part_no))) STORED,
            description VARCHAR(255) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            deleted_at DATETIME NULL,
            UNIQUE KEY uq_parts_normalized_part_no (normalized_part_no)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    part_tables = [
        "production_plans",
        "setting_dies",
        "qc_inspections",
        "production_starts",
        "production_finishes",
    ]
    for table_name in part_tables:
        _ensure_column(
            cursor,
            table_name,
            "part_id",
            "part_id INT NULL COMMENT 'TODO: make NOT NULL after backend part_id writes are fully verified'",
        )
        _ensure_column(cursor, table_name, "deleted_at", "deleted_at DATETIME NULL")

    for table_name in ["qc_inspections", "production_starts", "production_finishes"]:
        _ensure_column(
            cursor,
            table_name,
            "plan_id",
            "plan_id INT NULL COMMENT 'TODO: make NOT NULL where workflow always requires a production plan'",
        )

    _seed_parts_from_existing_part_numbers(cursor)
    _backfill_part_ids(cursor)
    _backfill_plan_ids(cursor)

    _ensure_index(cursor, "production_plans", "idx_production_plans_part_id", "part_id")
    _ensure_index(cursor, "setting_dies", "idx_setting_dies_part_id", "part_id")
    _ensure_index(cursor, "qc_inspections", "idx_qc_inspections_part_id", "part_id")
    _ensure_index(cursor, "production_starts", "idx_production_starts_part_id", "part_id")
    _ensure_index(cursor, "production_finishes", "idx_production_finishes_part_id", "part_id")

    _ensure_index(cursor, "qc_inspections", "idx_qc_inspections_plan_id", "plan_id")
    _ensure_index(cursor, "production_starts", "idx_production_starts_plan_id", "plan_id")
    _ensure_index(cursor, "production_finishes", "idx_production_finishes_plan_id", "plan_id")
    _ensure_index(cursor, "qc_inspections", "idx_qc_inspections_lot_no", "lot_no")
    _ensure_index(cursor, "production_starts", "idx_production_starts_lot_no", "lot_no")
    _ensure_index(cursor, "production_finishes", "idx_production_finishes_lot_no", "lot_no")
    _ensure_index(cursor, "production_plans", "idx_production_plans_deleted_at", "deleted_at")
    _ensure_index(cursor, "setting_dies", "idx_setting_dies_deleted_at", "deleted_at")
    _ensure_index(cursor, "qc_inspections", "idx_qc_inspections_deleted_at", "deleted_at")
    _ensure_index(cursor, "production_starts", "idx_production_starts_deleted_at", "deleted_at")
    _ensure_index(cursor, "production_finishes", "idx_production_finishes_deleted_at", "deleted_at")

    _ensure_foreign_key(
        cursor, "production_plans", "fk_production_plans_part", "part_id", "parts(id)", "RESTRICT"
    )
    _ensure_foreign_key(
        cursor, "setting_dies", "fk_setting_dies_part", "part_id", "parts(id)", "RESTRICT"
    )
    _ensure_foreign_key(
        cursor, "qc_inspections", "fk_qc_inspections_part", "part_id", "parts(id)", "RESTRICT"
    )
    _ensure_foreign_key(
        cursor,
        "production_starts",
        "fk_production_starts_part",
        "part_id",
        "parts(id)",
        "RESTRICT",
    )
    _ensure_foreign_key(
        cursor,
        "production_finishes",
        "fk_production_finishes_part",
        "part_id",
        "parts(id)",
        "RESTRICT",
    )
    _ensure_foreign_key(
        cursor,
        "qc_inspections",
        "fk_qc_inspections_plan",
        "plan_id",
        "production_plans(id)",
        "RESTRICT",
    )
    _ensure_foreign_key(
        cursor,
        "production_starts",
        "fk_production_starts_plan",
        "plan_id",
        "production_plans(id)",
        "RESTRICT",
    )
    _ensure_foreign_key(
        cursor,
        "production_finishes",
        "fk_production_finishes_plan",
        "plan_id",
        "production_plans(id)",
        "SET NULL",
    )


def _seed_parts_from_existing_part_numbers(cursor):
    source_tables = [
        "production_plans",
        "setting_dies",
        "qc_inspections",
        "production_starts",
        "production_finishes",
    ]
    for table_name in source_tables:
        if not _table_exists(cursor, table_name):
            continue
        cursor.execute(
            f"""
            INSERT INTO parts (part_no)
            SELECT DISTINCT TRIM(part_no)
            FROM {table_name}
            WHERE part_no IS NOT NULL AND TRIM(part_no) <> ''
            ON DUPLICATE KEY UPDATE part_no = parts.part_no
            """
        )


def _backfill_part_ids(cursor):
    for table_name in [
        "production_plans",
        "setting_dies",
        "qc_inspections",
        "production_starts",
        "production_finishes",
    ]:
        if not _table_exists(cursor, table_name):
            continue
        cursor.execute(
            f"""
            UPDATE {table_name} t
            JOIN parts p ON p.normalized_part_no = UPPER(TRIM(t.part_no))
            SET t.part_id = p.id
            WHERE t.part_id IS NULL
                AND t.part_no IS NOT NULL
                AND TRIM(t.part_no) <> ''
            """
        )


def _backfill_plan_ids(cursor):
    if _table_exists(cursor, "qc_inspections"):
        cursor.execute(
            """
            UPDATE qc_inspections q
            JOIN (
                SELECT lot_no, MAX(plan_id) AS plan_id
                FROM setting_dies
                WHERE lot_no IS NOT NULL AND TRIM(lot_no) <> ''
                GROUP BY lot_no
            ) s ON s.lot_no = q.lot_no
            SET q.plan_id = s.plan_id
            WHERE q.plan_id IS NULL
            """
        )

    if _table_exists(cursor, "production_starts"):
        cursor.execute(
            """
            UPDATE production_starts ps
            JOIN (
                SELECT lot_no, MAX(plan_id) AS plan_id
                FROM setting_dies
                WHERE lot_no IS NOT NULL AND TRIM(lot_no) <> ''
                GROUP BY lot_no
            ) s ON s.lot_no = ps.lot_no
            SET ps.plan_id = s.plan_id
            WHERE ps.plan_id IS NULL
            """
        )

    if _table_exists(cursor, "production_finishes"):
        cursor.execute(
            """
            UPDATE production_finishes pf
            JOIN (
                SELECT lot_no, MAX(plan_id) AS plan_id
                FROM setting_dies
                WHERE lot_no IS NOT NULL AND TRIM(lot_no) <> ''
                GROUP BY lot_no
            ) s ON s.lot_no = pf.lot_no
            SET pf.plan_id = s.plan_id
            WHERE pf.plan_id IS NULL
            """
        )

    for table_name in ["setting_dies", "qc_inspections", "production_starts", "production_finishes"]:
        if not _table_exists(cursor, table_name):
            continue
        cursor.execute(
            f"""
            UPDATE {table_name} t
            JOIN production_plans p ON p.id = t.plan_id
            SET t.part_id = p.part_id
            WHERE t.part_id IS NULL AND p.part_id IS NOT NULL
            """
        )


def find_part_by_part_no(cursor, part_no):
    normalized = require_normalized_part_no(part_no)
    cursor.execute(
        """
        SELECT id, part_no, normalized_part_no, description, created_at, updated_at, deleted_at
        FROM parts
        WHERE normalized_part_no = %s
        LIMIT 1
        """,
        (normalized,),
    )
    return cursor.fetchone()


def find_or_create_part_by_part_no(cursor, part_no):
    normalized = require_normalized_part_no(part_no)
    display_part_no = (part_no or "").strip()
    cursor.execute(
        """
        SELECT id, part_no, normalized_part_no, description, created_at, updated_at, deleted_at
        FROM parts
        WHERE normalized_part_no = %s
        LIMIT 1
        """,
        (normalized,),
    )
    part = cursor.fetchone()
    if part:
        if part.get("deleted_at") is not None:
            cursor.execute("UPDATE parts SET deleted_at = NULL WHERE id = %s", (part["id"],))
            part["deleted_at"] = None
        return part

    cursor.execute("INSERT INTO parts (part_no) VALUES (%s)", (display_part_no,))
    part_id = cursor.lastrowid
    return {
        "id": part_id,
        "part_no": display_part_no,
        "normalized_part_no": normalized,
        "description": None,
        "deleted_at": None,
    }


def validate_plan_part_consistency(cursor, plan_id, part_no):
    if not plan_id:
        return find_or_create_part_by_part_no(cursor, part_no), None

    part = find_or_create_part_by_part_no(cursor, part_no)
    cursor.execute(
        """
        SELECT id, part_id, part_no
        FROM production_plans
        WHERE id = %s AND deleted_at IS NULL
        LIMIT 1
        """,
        (plan_id,),
    )
    plan = cursor.fetchone()
    if not plan:
        raise PartValidationError("Production plan was not found")

    if plan.get("part_id") is not None:
        if int(plan["part_id"]) != int(part["id"]):
            raise PartValidationError("Submitted part_no does not match the selected production plan")
        return part, plan

    plan_part_no = normalize_part_no(plan.get("part_no"))
    if plan_part_no and plan_part_no != normalize_part_no(part_no):
        raise PartValidationError("Submitted part_no does not match the selected production plan")

    cursor.execute("UPDATE production_plans SET part_id = %s WHERE id = %s", (part["id"], plan_id))
    plan["part_id"] = part["id"]
    return part, plan


def get_part_with_relations(cursor, part_no):
    part = find_part_by_part_no(cursor, part_no)
    if not part:
        raise PartNotFoundError("part_no was not found")

    relations = {"part": part}
    for key, table_name in [
        ("production_plans", "production_plans"),
        ("setting_dies", "setting_dies"),
        ("qc_inspections", "qc_inspections"),
        ("production_starts", "production_starts"),
        ("production_finishes", "production_finishes"),
    ]:
        cursor.execute(
            f"""
            SELECT *
            FROM {table_name}
            WHERE part_id = %s
            ORDER BY id DESC
            """,
            (part["id"],),
        )
        relations[key] = cursor.fetchall()
    return relations


def update_part_by_part_no(cursor, part_no, payload):
    part = find_part_by_part_no(cursor, part_no)
    if not part:
        raise PartNotFoundError("part_no was not found")

    fields = []
    params = []
    if "part_no" in payload:
        new_part_no = (payload.get("part_no") or "").strip()
        require_normalized_part_no(new_part_no)
        fields.append("part_no = %s")
        params.append(new_part_no)
    if "description" in payload:
        fields.append("description = %s")
        params.append(payload.get("description"))
    if "deleted_at" in payload:
        fields.append("deleted_at = %s")
        params.append(payload.get("deleted_at"))

    if fields:
        params.append(part["id"])
        cursor.execute(f"UPDATE parts SET {', '.join(fields)} WHERE id = %s", tuple(params))

    return find_part_by_part_no(cursor, payload.get("part_no") or part_no)


def soft_delete_part_by_part_no(cursor, part_no):
    part = find_part_by_part_no(cursor, part_no)
    if not part:
        raise PartNotFoundError("part_no was not found")

    cursor.execute("UPDATE parts SET deleted_at = NOW() WHERE id = %s", (part["id"],))
    return part
