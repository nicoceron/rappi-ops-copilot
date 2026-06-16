#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ops_copilot.data_loader import OperationalDataset, load_workbook
from ops_copilot.settings import PROJECT_ROOT, default_data_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest the Rappi ops workbook into Postgres.")
    parser.add_argument("--data-file", type=Path, default=default_data_file())
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read and normalize the workbook without writing to Postgres.",
    )
    args = parser.parse_args()

    dataset = load_workbook(args.data_file)
    print_summary(dataset)

    if args.dry_run or not args.database_url:
        print("Dry run complete. Set DATABASE_URL or pass --database-url to load Postgres.")
        return

    ingest_postgres(dataset, args.database_url)
    print("Postgres ingestion complete.")


def print_summary(dataset: OperationalDataset) -> None:
    print(f"zones={len(dataset.zones)}")
    print(f"metrics={len(dataset.metrics)}")
    print(f"metric_synonyms={len(dataset.metric_synonyms)}")
    print(f"metric_facts={len(dataset.metric_facts)}")
    print(f"order_facts={len(dataset.order_facts)}")


def ingest_postgres(dataset: OperationalDataset, database_url: str) -> None:
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit(
            "psycopg is not installed. Install project dependencies with `pip install -e .`."
        ) from exc

    schema_sql = (PROJECT_ROOT / "db" / "schema.sql").read_text()
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
            _upsert_zones(cur, dataset.zones)
            _upsert_metrics(cur, dataset.metrics)
            _upsert_synonyms(cur, dataset.metric_synonyms)
            _upsert_metric_facts(cur, dataset.metric_facts)
            _upsert_order_facts(cur, dataset.order_facts)
        conn.commit()


def _upsert_zones(cur: Any, frame: pd.DataFrame) -> None:
    cur.executemany(
        """
        insert into dim_zone (zone_id, country, city, zone, zone_type, zone_prioritization)
        values (%(zone_id)s, %(country)s, %(city)s, %(zone)s, %(zone_type)s, %(zone_prioritization)s)
        on conflict (zone_id) do update set
          country = excluded.country,
          city = excluded.city,
          zone = excluded.zone,
          zone_type = excluded.zone_type,
          zone_prioritization = excluded.zone_prioritization,
          updated_at = now()
        """,
        _records(frame),
    )


def _upsert_metrics(cur: Any, frame: pd.DataFrame) -> None:
    cur.executemany(
        """
        insert into semantic_metric (
          metric_key, metric_name, source, default_direction, value_kind, outlier_policy, description
        )
        values (
          %(metric_key)s, %(metric_name)s, %(source)s, %(default_direction)s,
          %(value_kind)s, %(outlier_policy)s, %(description)s
        )
        on conflict (metric_key) do update set
          metric_name = excluded.metric_name,
          source = excluded.source,
          default_direction = excluded.default_direction,
          value_kind = excluded.value_kind,
          outlier_policy = excluded.outlier_policy,
          description = excluded.description,
          updated_at = now()
        """,
        _records(frame),
    )


def _upsert_synonyms(cur: Any, frame: pd.DataFrame) -> None:
    cur.executemany(
        """
        insert into metric_synonym (synonym, metric_key)
        values (%(synonym)s, %(metric_key)s)
        on conflict (synonym) do update set metric_key = excluded.metric_key
        """,
        _records(frame),
    )


def _upsert_metric_facts(cur: Any, frame: pd.DataFrame) -> None:
    cur.executemany(
        """
        insert into fact_metric_week (
          zone_id, metric_key, week_offset, week_label, value, source_column
        )
        values (
          %(zone_id)s, %(metric_key)s, %(week_offset)s, %(week_label)s,
          %(value)s, %(source_column)s
        )
        on conflict (zone_id, metric_key, week_offset) do update set
          week_label = excluded.week_label,
          value = excluded.value,
          source_column = excluded.source_column,
          updated_at = now()
        """,
        _records(frame[["zone_id", "metric_key", "week_offset", "week_label", "value", "source_column"]]),
    )


def _upsert_order_facts(cur: Any, frame: pd.DataFrame) -> None:
    cur.executemany(
        """
        insert into fact_orders_week (
          zone_id, week_offset, week_label, orders, source_column
        )
        values (
          %(zone_id)s, %(week_offset)s, %(week_label)s, %(orders)s, %(source_column)s
        )
        on conflict (zone_id, week_offset) do update set
          week_label = excluded.week_label,
          orders = excluded.orders,
          source_column = excluded.source_column,
          updated_at = now()
        """,
        _records(frame),
    )


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    clean = frame.where(pd.notna(frame), None)
    records = clean.to_dict(orient="records")
    for row in records:
        for key, value in row.items():
            if hasattr(value, "item"):
                row[key] = value.item()
    return records


if __name__ == "__main__":
    main()
