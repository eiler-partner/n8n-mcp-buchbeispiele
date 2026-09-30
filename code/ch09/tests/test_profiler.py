import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fixtures import CLEAN, DIRTY
from profiler import MAX_CHARS, MAX_ROWS, profile_csv, profile_csv_pandas


def test_clean_contract():
    result = profile_csv(CLEAN)
    assert result == {
        "row_count": 3,
        "valid_count": 3,
        "invalid_count": 0,
        "total_cents": 1700,
        "by_region": {
            "north": {"count": 2, "total_cents": 1200},
            "south": {"count": 1, "total_cents": 500},
        },
        "issues": [],
    }
    assert profile_csv_pandas(CLEAN) == {
        **result,
        "median_cents": {"north": 600.0, "south": 500.0},
    }


def test_dirty_contract():
    result = profile_csv(DIRTY)
    assert result["row_count"] == 4
    assert result["valid_count"] == 1
    assert result["invalid_count"] == 3
    assert result["total_cents"] == 1200
    assert result["issues"] == [
        {"line": 3, "codes": ["amount_cents"]},
        {"line": 4, "codes": ["duplicate_order_id"]},
        {"line": 5, "codes": ["amount_cents"]},
    ]
    assert profile_csv_pandas(DIRTY)["median_cents"] == {"north": 1200.0, "south": None}


def test_physical_line_number_after_quoted_newline():
    source = (
        "order_id,region,amount_cents,customer\n"
        'A,north,1,"X\nY"\n'
        "B,south,bad,C\n"
    )
    assert profile_csv(source)["issues"] == [{"line": 4, "codes": ["amount_cents"]}]


def test_invalid_first_row_still_reserves_order_id():
    source = (
        "order_id,region,amount_cents,customer\n"
        "X-1,north,abc,Ada\n"
        "X-1,north,100,Ada\n"
    )
    result = profile_csv(source)
    assert result["valid_count"] == 0
    assert result["total_cents"] == 0
    assert result["issues"] == [
        {"line": 2, "codes": ["amount_cents"]},
        {"line": 3, "codes": ["duplicate_order_id"]},
    ]


@pytest.mark.parametrize(
    ("source", "error"),
    [
        ("x,y\n1,2\n", "csv_header"),
        ("order_id,region,amount_cents,customer\n", "csv_empty"),
        ("x" * (MAX_CHARS + 1), "csv_size_or_type"),
        (None, "csv_size_or_type"),
        ("order_id,region,amount_cents,customer\nA,north,1,C,x\n", "csv_columns"),
        (
            "order_id,region,amount_cents,customer\n"
            + "A,north,1,C\n" * (MAX_ROWS + 1),
            "csv_row_limit",
        ),
    ],
)
def test_rejected_input(source, error):
    with pytest.raises(ValueError, match=error):
        profile_csv(source)


def test_generated_workflows_and_runner_policy():
    from build_workflows import workflow

    for kind in ("core", "pandas"):
        generated = workflow(kind)
        file = Path(__file__).resolve().parents[1] / "n8n" / "workflows" / f"ch09-{kind}.json"
        assert json.loads(file.read_text(encoding="utf-8")) == generated
        assert generated["nodes"][1]["parameters"]["language"] == "pythonNative"
        assert generated["nodes"][2]["parameters"]["mode"] == "runOnceForEachItem"
    config = json.loads(
        (Path(__file__).resolve().parents[1] / "runner-config.json").read_text(encoding="utf-8")
    )
    python = next(r for r in config["task-runners"] if r["runner-type"] == "python")
    assert python["env-overrides"]["N8N_RUNNERS_STDLIB_ALLOW"] == "csv,io"
    assert python["env-overrides"]["N8N_RUNNERS_EXTERNAL_ALLOW"] == "pandas"
    assert "*" not in str(python["env-overrides"])
