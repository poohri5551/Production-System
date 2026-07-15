QC_TIMESTAMP_FIELDS = {
    "time_start": "Time Start Inspection Part",
    "time_end": "Time End Inspection Part",
}


class QCTimestampValidationError(ValueError):
    pass


def validate_qc_timestamp_field(field_name):
    if field_name not in QC_TIMESTAMP_FIELDS:
        raise QCTimestampValidationError("Unsupported QC timestamp field")
    return field_name


def validate_qc_identity_request(plan, requested_plan_id=None, requested_lot_no=None, requested_part_no=None):
    authoritative_plan_id = str(plan.get("id") or "")
    authoritative_lot_no = str(plan.get("lot_no") or "").strip()
    authoritative_part_no = str(plan.get("part_no") or "").strip()

    if requested_plan_id not in (None, "") and str(requested_plan_id).strip() != authoritative_plan_id:
        raise QCTimestampValidationError("Submitted plan_id does not match the selected production plan")
    if requested_lot_no not in (None, "") and str(requested_lot_no).strip() != authoritative_lot_no:
        raise QCTimestampValidationError("Submitted lot_no does not match the selected production plan")
    if requested_part_no not in (None, "") and str(requested_part_no).strip().upper() != authoritative_part_no.upper():
        raise QCTimestampValidationError("Submitted part_no does not match the selected production plan")


def stamp_locked_qc_timestamp(cursor, qc_id, field_name):
    field_name = validate_qc_timestamp_field(field_name)
    cursor.execute(
        f"UPDATE qc_inspections SET {field_name} = NOW() "
        f"WHERE id = %s AND deleted_at IS NULL AND {field_name} IS NULL",
        (qc_id,),
    )
    stamped = cursor.rowcount == 1
    cursor.execute(
        f"SELECT {field_name} AS timestamp FROM qc_inspections "
        "WHERE id = %s AND deleted_at IS NULL",
        (qc_id,),
    )
    row = cursor.fetchone() or {}
    return stamped, row.get("timestamp")
