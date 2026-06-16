#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ops_copilot.data_loader import OperationalDataset, load_workbook
from ops_copilot.postgres_loader import ingest_postgres
from ops_copilot.settings import default_data_file


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
    print(f"city_aliases={len(dataset.city_aliases)}")
    print(f"metric_facts={len(dataset.metric_facts)}")
    print(f"order_facts={len(dataset.order_facts)}")
    print(f"data_quality_status={dataset.data_quality['status']}")
    for warning in dataset.data_quality.get("warnings", []):
        print(f"warning={warning}")


if __name__ == "__main__":
    main()
