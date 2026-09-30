"""Synthetic, deterministic input and an independent Python result oracle."""

from __future__ import annotations


CASES = ("empty", "single", "large", "filtered")


def records_for(case: str) -> list[dict]:
    if case == "empty":
        return []
    if case == "single":
        return [{"id": "R-001", "team": "north", "amount": "12.50", "active": True}]
    if case == "filtered":
        return [
            {"id": "R-002", "team": "south", "amount": "9.00", "active": False},
            {"id": "R-003", "team": "north", "amount": "0.00", "active": True},
        ]
    if case == "large":
        return [
            {
                "id": f"R-{i % 125:03d}",
                "team": "north" if i % 2 == 0 else "south",
                "amount": f"{i % 17 + 1}.00",
                "active": i % 9 != 0,
            }
            for i in range(150)
        ]
    raise KeyError(case)


def envelope(case: str) -> dict:
    return {"case": case, "records": records_for(case)}


def expected_summary(case: str) -> dict:
    records = records_for(case)
    eligible = [row for row in records if row["active"] and row["amount"] != "0.00"]
    first_by_id = {}
    for row in eligible:
        first_by_id.setdefault(row["id"], row)
    selected = sorted(first_by_id.values(), key=lambda row: (row["team"], row["id"]))
    totals = {"north": 0, "south": 0}
    for row in selected:
        whole, fraction = row["amount"].split(".")
        totals[row["team"]] += int(whole) * 100 + int(fraction)
    return {
        "case": case,
        "raw_count": len(records),
        "eligible_count": len(eligible),
        "unique_count": len(selected),
        "north_cents": totals["north"],
        "south_cents": totals["south"],
        "first_id": selected[0]["id"] if selected else None,
        "last_id": selected[-1]["id"] if selected else None,
    }
