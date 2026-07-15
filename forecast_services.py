import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, localcontext


MONTH_KEY_PATTERN = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


class ForecastValidationError(ValueError):
    pass


def validate_month_key(value):
    if not isinstance(value, str) or not MONTH_KEY_PATTERN.fullmatch(value):
        raise ForecastValidationError("month must use YYYY-MM format.")
    year, month = (int(part) for part in value.split("-"))
    try:
        return date(year, month, 1)
    except ValueError as error:
        raise ForecastValidationError("month must be a valid calendar month.") from error


def month_key(value):
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.strftime("%Y-%m")
    return validate_month_key(value).strftime("%Y-%m")


def choose_default_month(available_months, today=None):
    keys = sorted({month_key(value) for value in available_months})
    if not keys:
        return None
    current = (today or date.today()).strftime("%Y-%m")
    if current in keys:
        return current
    not_after = [value for value in keys if value <= current]
    return not_after[-1] if not_after else keys[0]


def validate_lot_count(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ForecastValidationError("Lot must be a positive whole number or null.")
    if value < 1:
        raise ForecastValidationError("Lot must be at least 1.")
    if value > 2147483647:
        raise ForecastValidationError("Lot is too large.")
    return value


def validate_lot_batch(payload):
    if not isinstance(payload, dict) or set(payload) != {"items"}:
        raise ForecastValidationError("Request body must contain only an items array.")
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise ForecastValidationError("items must be a non-empty array.")

    validated = []
    seen = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict) or set(item) != {"id", "month", "lot_count"}:
            raise ForecastValidationError(
                f"items[{index}] must contain only id, month, and lot_count."
            )
        entry_id = item.get("id")
        if isinstance(entry_id, bool) or not isinstance(entry_id, int) or entry_id < 1:
            raise ForecastValidationError(f"items[{index}].id must be a positive integer.")
        normalized_month = month_key(item.get("month"))
        identity = (entry_id, normalized_month)
        if identity in seen:
            raise ForecastValidationError(
                f"Duplicate entry/month in request: {entry_id}/{normalized_month}."
            )
        seen.add(identity)
        validated.append({
            "id": entry_id,
            "month": normalized_month,
            "forecast_month": validate_month_key(normalized_month),
            "lot_count": validate_lot_count(item.get("lot_count")),
        })
    return validated


def to_decimal(value):
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, bool) or value is None:
        raise ForecastValidationError("Forecast quantity must be numeric.")
    else:
        try:
            result = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as error:
            raise ForecastValidationError("Forecast quantity must be numeric.") from error
    if not result.is_finite():
        raise ForecastValidationError("Forecast quantity must be finite.")
    return result


def calculate_quantity(quantity, lot_count):
    lot_count = validate_lot_count(lot_count)
    if lot_count is None:
        return None
    with localcontext() as context:
        context.prec = 38
        return to_decimal(quantity) / Decimal(lot_count)


def decimal_to_json(value):
    if value is None:
        return None
    decimal_value = to_decimal(value)
    if decimal_value == decimal_value.to_integral_value():
        return int(decimal_value)
    return format(decimal_value, "f").rstrip("0").rstrip(".")


def serialize_forecast_entry(row):
    lot_count = row.get("lot_count")
    if lot_count is not None:
        lot_count = int(lot_count)
    month = month_key(row["forecast_month"])
    quantity = decimal_to_json(row.get("quantity"))
    return {
        "id": int(row["id"]),
        "part_no": row.get("part_no") or "",
        "month": month,
        "month_label": row.get("source_label") or month,
        "quantity": quantity,
        "lot_count": lot_count,
        "quantity_per_lot": decimal_to_json(calculate_quantity(quantity, lot_count)),
    }
