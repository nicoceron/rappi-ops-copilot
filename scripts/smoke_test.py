#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ops_copilot.data_loader import load_workbook
from ops_copilot.models import SemanticQuery
from ops_copilot.query_engine import QueryEngine
from ops_copilot.settings import default_data_file


def main() -> None:
    engine = QueryEngine(load_workbook(default_data_file()))
    cases = [
        (
            "top lead penetration",
            SemanticQuery(
                intent="rank",
                metrics=["Lead Penetration"],
                dimensions=["country", "city", "zone"],
                limit=5,
                visualization="bar",
            ),
        ),
        (
            "wealthy comparison mx",
            SemanticQuery(
                intent="compare",
                metrics=["Perfect Orders"],
                dimensions=["zone_type"],
                filters={"country": "Mexico"},
                aggregation="avg",
                visualization="bar",
            ),
        ),
        (
            "chapinero gp trend",
            SemanticQuery(
                intent="trend",
                metrics=["Gross Profit UE"],
                filters={"zone": "Chapinero"},
                period={"start_offset": 7, "end_offset": 0},
                aggregation="avg",
                visualization="line",
            ),
        ),
        (
            "lead avg country",
            SemanticQuery(
                intent="aggregate",
                metrics=["Lead Penetration"],
                dimensions=["country"],
                aggregation="avg",
                visualization="bar",
            ),
        ),
        (
            "n8n wrapped lead avg country",
            SemanticQuery(
                intent="aggregate",
                metrics={"values": ["Lead Penetration"]},
                dimensions={"values": ["country"]},
                sort={"values": []},
                diagnostic_metrics={"values": []},
                aggregation="avg",
                visualization="bar",
            ),
        ),
        (
            "high lead low perfect",
            SemanticQuery(
                intent="segment",
                metrics=["Lead Penetration", "Perfect Orders"],
                limit=10,
                visualization="scatter",
            ),
        ),
        (
            "orders growth diagnostics",
            SemanticQuery(
                intent="growth",
                metrics=["Orders"],
                period={"start_offset": 4, "end_offset": 0},
                include_diagnostics=True,
                diagnostic_metrics=["Lead Penetration", "Perfect Orders", "Gross Profit UE"],
                limit=10,
                visualization="bar",
            ),
        ),
        (
            "problem zones mx",
            SemanticQuery(
                intent="diagnose",
                metrics=[],
                filters={"country": "MX"},
                limit=10,
                visualization="bar",
            ),
        ),
    ]

    for name, query in cases:
        result = engine.execute(query)
        if result.row_count < 1:
            raise SystemExit(f"{name}: expected at least one row")
        print(f"ok {name}: {result.row_count} rows ({result.answer_type})")


if __name__ == "__main__":
    main()
