PRODUCTION_FINISH_TIMESTAMP_FIELDS = {
    "time_finish": "Production Finish Time",
    "hold_time": "Hold Production Time",
}


class ProductionFinishValidationError(ValueError):
    pass


def validate_production_finish_timestamp_field(field_name):
    if field_name not in PRODUCTION_FINISH_TIMESTAMP_FIELDS:
        raise ProductionFinishValidationError("Unsupported Production Finish timestamp field")
    return field_name


def validate_production_finish_identity(finish, plan, authoritative_part):
    if finish.get("plan_id") != plan.get("id"):
        raise ProductionFinishValidationError("Production Finish plan identity does not match its production plan")
    if str(finish.get("lot_no") or "").strip() != str(plan.get("lot_no") or "").strip():
        raise ProductionFinishValidationError("Production Finish Lot No. does not match its production plan")
    if finish.get("part_id") not in (None, authoritative_part.get("id")):
        raise ProductionFinishValidationError("Production Finish Part identity does not match its production plan")
    if str(finish.get("part_no") or "").strip().upper() != str(authoritative_part.get("part_no") or "").strip().upper():
        raise ProductionFinishValidationError("Production Finish Part No. does not match its production plan")


def stamp_locked_production_finish_timestamp(cursor, finish_id, field_name):
    field_name = validate_production_finish_timestamp_field(field_name)
    cursor.execute(
        f"UPDATE production_finishes SET {field_name} = NOW() "
        f"WHERE id = %s AND deleted_at IS NULL AND {field_name} IS NULL",
        (finish_id,),
    )
    stamped = cursor.rowcount == 1
    cursor.execute(
        f"SELECT {field_name} AS timestamp FROM production_finishes "
        "WHERE id = %s AND deleted_at IS NULL",
        (finish_id,),
    )
    row = cursor.fetchone() or {}
    return stamped, row.get("timestamp")
