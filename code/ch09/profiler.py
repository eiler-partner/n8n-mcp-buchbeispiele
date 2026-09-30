"""Pure, bounded CSV-quality contract shared by pytest and native n8n Python."""

import csv
from io import StringIO


FIELDS = ["order_id", "region", "amount_cents", "customer"]
REGIONS = ("north", "south")
MAX_CHARS = 65_536
MAX_ROWS = 1_000
MAX_CENTS = 1_000_000


def _analyze(text):
    if not isinstance(text, str) or not text or len(text) > MAX_CHARS:
        raise ValueError("csv_size_or_type")
    reader = csv.DictReader(StringIO(text), strict=True)
    if reader.fieldnames != FIELDS:
        raise ValueError("csv_header")
    accepted = []
    issues = []
    seen = set()
    row_count = 0
    for row in reader:
        line = reader.line_num
        row_count += 1
        if row_count > MAX_ROWS:
            raise ValueError("csv_row_limit")
        if None in row or any(value is None for value in row.values()):
            raise ValueError("csv_columns")
        errors = []
        order_id = row["order_id"].strip()
        if not order_id or len(order_id) > 64:
            errors.append("order_id")
        elif order_id in seen:
            errors.append("duplicate_order_id")
        else:
            seen.add(order_id)
        region = row["region"].strip()
        if region not in REGIONS:
            errors.append("region")
        customer = row["customer"].strip()
        if not customer or len(customer) > 80 or "\x00" in customer:
            errors.append("customer")
        amount = row["amount_cents"].strip()
        if not amount.isascii() or not amount.isdecimal() or int(amount) > MAX_CENTS:
            errors.append("amount_cents")
        if errors:
            issues.append({"line": line, "codes": errors})
        else:
            accepted.append({"order_id": order_id, "region": region, "amount_cents": int(amount)})
    if row_count == 0:
        raise ValueError("csv_empty")
    by_region = {
        region: {
            "count": sum(1 for row in accepted if row["region"] == region),
            "total_cents": sum(row["amount_cents"] for row in accepted if row["region"] == region),
        }
        for region in REGIONS
    }
    result = {
        "row_count": row_count,
        "valid_count": len(accepted),
        "invalid_count": len(issues),
        "total_cents": sum(row["amount_cents"] for row in accepted),
        "by_region": by_region,
        "issues": issues,
    }
    return result, accepted


def profile_csv(text):
    result, _ = _analyze(text)
    return result


def profile_csv_pandas(text):
    """Optional extension: medians from only the already validated rows."""
    import pandas as pd

    result, accepted = _analyze(text)
    frame = pd.DataFrame(accepted, columns=["region", "amount_cents"])
    medians = frame.groupby("region")["amount_cents"].median() if accepted else {}
    result["median_cents"] = {
        region: float(medians[region]) if region in medians else None for region in REGIONS
    }
    return result
