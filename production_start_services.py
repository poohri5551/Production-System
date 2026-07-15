class ProductionStartValidationError(ValueError):
    pass


def production_start_confirmed(value):
    return str(value or "").strip().lower() == "confirmed"


def _same_identifier(left, right):
    if left in (None, "") or right in (None, ""):
        return left in (None, "") and right in (None, "")
    return str(left).strip() == str(right).strip()


def _same_text(left, right):
    return str(left or "").strip() == str(right or "").strip()


def _same_part_no(left, right):
    return str(left or "").strip().upper() == str(right or "").strip().upper()


def validate_production_start_identity(
    start,
    plan,
    authoritative_part,
    requested_plan_id=None,
    requested_lot_no=None,
    requested_part_id=None,
    requested_part_no=None,
):
    if not _same_identifier(start.get("plan_id"), plan.get("id")):
        raise ProductionStartValidationError("Production Start plan identity does not match its production plan")
    if not _same_text(start.get("lot_no"), plan.get("lot_no")):
        raise ProductionStartValidationError("Production Start Lot No. does not match its production plan")
    if start.get("part_id") not in (None, "") and not _same_identifier(start.get("part_id"), authoritative_part.get("id")):
        raise ProductionStartValidationError("Production Start Part identity does not match its production plan")
    if not _same_part_no(start.get("part_no"), authoritative_part.get("part_no")):
        raise ProductionStartValidationError("Production Start Part No. does not match its production plan")

    if requested_plan_id not in (None, "") and not _same_identifier(requested_plan_id, start.get("plan_id")):
        raise ProductionStartValidationError("Production Start plan identity cannot be changed")
    if requested_lot_no not in (None, "") and not _same_text(requested_lot_no, start.get("lot_no")):
        raise ProductionStartValidationError("Production Start Lot No. cannot be changed")
    if requested_part_id not in (None, "") and not _same_identifier(requested_part_id, authoritative_part.get("id")):
        raise ProductionStartValidationError("Production Start Part identity cannot be changed")
    if requested_part_no not in (None, "") and not _same_part_no(requested_part_no, authoritative_part.get("part_no")):
        raise ProductionStartValidationError("Production Start Part No. cannot be changed")


def stamp_locked_production_start_time(cursor, start_id):
    cursor.execute(
        "UPDATE production_starts SET time_start = NOW() "
        "WHERE id = %s AND deleted_at IS NULL AND time_start IS NULL",
        (start_id,),
    )
    stamped = cursor.rowcount == 1
    cursor.execute(
        "SELECT time_start AS timestamp FROM production_starts "
        "WHERE id = %s AND deleted_at IS NULL",
        (start_id,),
    )
    row = cursor.fetchone() or {}
    return stamped, row.get("timestamp")
