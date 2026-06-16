from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ops_copilot.data_loader import OperationalDataset, load_workbook
from ops_copilot.settings import PROJECT_ROOT


def ensure_postgres_loaded(database_url: str, data_file: Path, *, force: bool = False) -> None:
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg is required to load Postgres") from exc

    schema_sql = (PROJECT_ROOT / "db" / "schema.sql").read_text()
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
            cur.execute("select count(*) from dim_zone")
            existing_zones = cur.fetchone()[0]
        conn.commit()

    if existing_zones and not force:
        dataset = load_workbook(data_file)
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                _upsert_city_aliases(cur, dataset.city_aliases)
                _upsert_metrics(cur, dataset.metrics)
                _upsert_synonyms(cur, dataset.metric_synonyms)
                _upsert_metric_facts(cur, dataset.metric_facts)
            conn.commit()
        return

    ingest_postgres(load_workbook(data_file), database_url)


def ingest_postgres(dataset: OperationalDataset, database_url: str) -> None:
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg is required to load Postgres") from exc

    schema_sql = (PROJECT_ROOT / "db" / "schema.sql").read_text()
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
            _upsert_zones(cur, dataset.zones)
            _upsert_city_aliases(cur, dataset.city_aliases)
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


def _upsert_city_aliases(cur: Any, frame: pd.DataFrame) -> None:
    cur.execute("delete from dim_city_alias")
    if frame.empty:
        return
    cur.executemany(
        """
        insert into dim_city_alias (country, alias, city)
        values (%(country)s, %(alias)s, %(city)s)
        on conflict (country, alias) do update set
          city = excluded.city,
          updated_at = now()
        """,
        _records(frame[["country", "alias", "city"]]),
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
          zone_id, metric_key, week_offset, week_label, value, is_outlier, source_column
        )
        values (
          %(zone_id)s, %(metric_key)s, %(week_offset)s, %(week_label)s,
          %(value)s, %(is_outlier)s, %(source_column)s
        )
        on conflict (zone_id, metric_key, week_offset) do update set
          week_label = excluded.week_label,
          value = excluded.value,
          is_outlier = excluded.is_outlier,
          source_column = excluded.source_column,
          updated_at = now()
        """,
        _records(
            frame[
                [
                    "zone_id",
                    "metric_key",
                    "week_offset",
                    "week_label",
                    "value",
                    "is_outlier",
                    "source_column",
                ]
            ]
        ),
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
