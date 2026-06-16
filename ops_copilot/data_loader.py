from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


WEEK_METRIC_RE = re.compile(r"^L([0-8])W_ROLL$")
WEEK_ORDERS_RE = re.compile(r"^L([0-8])W$")


METRIC_METADATA: dict[str, dict[str, str]] = {
    "Gross Profit UE": {
        "metric_key": "gross_profit_ue",
        "default_direction": "higher_better",
        "value_kind": "currency_per_order",
        "outlier_policy": "none",
    },
    "Perfect Orders": {
        "metric_key": "perfect_orders",
        "default_direction": "higher_better",
        "value_kind": "rate",
        "outlier_policy": "none",
    },
    "Lead Penetration": {
        "metric_key": "lead_penetration",
        "default_direction": "higher_better",
        "value_kind": "rate",
        "outlier_policy": "flag",
    },
    "% PRO Users Who Breakeven": {
        "metric_key": "pro_users_who_breakeven",
        "default_direction": "higher_better",
        "value_kind": "rate",
        "outlier_policy": "none",
    },
    "% Restaurants Sessions With Optimal Assortment": {
        "metric_key": "restaurants_sessions_optimal_assortment",
        "default_direction": "higher_better",
        "value_kind": "rate",
        "outlier_policy": "none",
    },
    "MLTV Top Verticals Adoption": {
        "metric_key": "mltv_top_verticals_adoption",
        "default_direction": "higher_better",
        "value_kind": "rate",
        "outlier_policy": "none",
    },
    "Non-Pro PTC > OP": {
        "metric_key": "non_pro_ptc_to_op",
        "default_direction": "unknown",
        "value_kind": "rate",
        "outlier_policy": "none",
    },
    "Pro Adoption (Last Week Status)": {
        "metric_key": "pro_adoption_last_week_status",
        "default_direction": "higher_better",
        "value_kind": "rate",
        "outlier_policy": "none",
    },
    "Restaurants Markdowns / GMV": {
        "metric_key": "restaurants_markdowns_gmv",
        "default_direction": "unknown",
        "value_kind": "rate",
        "outlier_policy": "none",
    },
    "Restaurants SS > ATC CVR": {
        "metric_key": "restaurants_ss_to_atc_cvr",
        "default_direction": "higher_better",
        "value_kind": "rate",
        "outlier_policy": "none",
    },
    "Restaurants SST > SS CVR": {
        "metric_key": "restaurants_sst_to_ss_cvr",
        "default_direction": "higher_better",
        "value_kind": "rate",
        "outlier_policy": "none",
    },
    "Retail SST > SS CVR": {
        "metric_key": "retail_sst_to_ss_cvr",
        "default_direction": "higher_better",
        "value_kind": "rate",
        "outlier_policy": "none",
    },
    "Turbo Adoption": {
        "metric_key": "turbo_adoption",
        "default_direction": "higher_better",
        "value_kind": "rate",
        "outlier_policy": "none",
    },
    "Orders": {
        "metric_key": "orders",
        "default_direction": "higher_better",
        "value_kind": "count",
        "outlier_policy": "none",
    },
}


METRIC_SYNONYMS: dict[str, list[str]] = {
    "gross_profit_ue": ["gross profit ue", "gp ue", "profit ue", "gross profit"],
    "perfect_orders": [
        "perfect order",
        "perfect orders",
        "orden perfecta",
        "ordenes perfectas",
        "ordenes perfecta",
    ],
    "lead_penetration": [
        "lead penetration",
        "% lead penetration",
        "penetracion de leads",
        "penetracion lead",
    ],
    "orders": ["orders", "ordenes", "pedidos"],
    "turbo_adoption": ["turbo adoption", "adopcion turbo"],
    "pro_adoption_last_week_status": ["pro adoption", "adopcion pro"],
}


COUNTRY_ALIASES: dict[str, str] = {
    "argentina": "AR",
    "ar": "AR",
    "brasil": "BR",
    "brazil": "BR",
    "br": "BR",
    "chile": "CL",
    "cl": "CL",
    "colombia": "CO",
    "co": "CO",
    "costa rica": "CR",
    "cr": "CR",
    "ecuador": "EC",
    "ec": "EC",
    "mexico": "MX",
    "méxico": "MX",
    "mx": "MX",
    "peru": "PE",
    "perú": "PE",
    "pe": "PE",
    "uruguay": "UY",
    "uy": "UY",
}


DIMENSION_COLUMNS = {
    "country": "country",
    "city": "city",
    "zone": "zone",
    "zone_type": "zone_type",
    "zone_prioritization": "zone_prioritization",
    "week_offset": "week_offset",
    "week_label": "week_label",
}


@dataclass(frozen=True)
class OperationalDataset:
    zones: pd.DataFrame
    metrics: pd.DataFrame
    metric_synonyms: pd.DataFrame
    metric_facts: pd.DataFrame
    order_facts: pd.DataFrame

    def schema(self, include_examples: bool = True) -> dict[str, Any]:
        metrics = (
            self.metrics.sort_values("metric_name")
            .loc[
                :,
                [
                    "metric_key",
                    "metric_name",
                    "source",
                    "default_direction",
                    "value_kind",
                    "outlier_policy",
                ],
            ]
            .to_dict(orient="records")
        )
        payload: dict[str, Any] = {
            "dimensions": sorted(DIMENSION_COLUMNS),
            "countries": sorted(self.zones["country"].dropna().unique().tolist()),
            "zone_types": sorted(self.zones["zone_type"].dropna().unique().tolist()),
            "zone_prioritizations": sorted(
                self.zones["zone_prioritization"].dropna().unique().tolist()
            ),
            "metrics": metrics,
            "time_semantics": {
                "L0W": "most recent available week",
                "L1W": "one week before L0W",
                "last_8_weeks_default": "L7W through L0W",
                "available_offsets": list(range(8, -1, -1)),
            },
        }
        if include_examples:
            payload["examples"] = {
                "country_aliases": COUNTRY_ALIASES,
                "metric_synonyms": self.metric_synonyms.groupby("metric_key")["synonym"]
                .apply(list)
                .to_dict(),
            }
        return payload


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text).strip().lower()


def make_zone_id(country: str, city: str, zone: str) -> str:
    return f"{country}|{city}|{zone}"


def metric_key_for(metric_name: str) -> str:
    if metric_name in METRIC_METADATA:
        return METRIC_METADATA[metric_name]["metric_key"]
    base = normalize_text(metric_name)
    return re.sub(r"[^a-z0-9]+", "_", base).strip("_")


def resolve_country(value: str) -> str:
    key = normalize_text(value)
    return COUNTRY_ALIASES.get(key, str(value).strip().upper())


def load_workbook(path: Path) -> OperationalDataset:
    input_metrics = pd.read_excel(path, sheet_name="RAW_INPUT_METRICS")
    orders = pd.read_excel(path, sheet_name="RAW_ORDERS")

    zones = _build_zones(input_metrics, orders)
    metrics = _build_metrics(input_metrics)
    synonyms = _build_synonyms(metrics)
    metric_facts = _build_metric_facts(input_metrics)
    order_facts = _build_order_facts(orders)

    return OperationalDataset(
        zones=zones,
        metrics=metrics,
        metric_synonyms=synonyms,
        metric_facts=metric_facts,
        order_facts=order_facts,
    )


def _build_zones(input_metrics: pd.DataFrame, orders: pd.DataFrame) -> pd.DataFrame:
    metric_zones = input_metrics[
        ["COUNTRY", "CITY", "ZONE", "ZONE_TYPE", "ZONE_PRIORITIZATION"]
    ].drop_duplicates()
    order_zones = orders[["COUNTRY", "CITY", "ZONE"]].drop_duplicates()
    order_zones = order_zones.merge(
        metric_zones,
        on=["COUNTRY", "CITY", "ZONE"],
        how="left",
    )
    zones = pd.concat([metric_zones, order_zones], ignore_index=True).drop_duplicates(
        subset=["COUNTRY", "CITY", "ZONE"]
    )
    zones = zones.rename(
        columns={
            "COUNTRY": "country",
            "CITY": "city",
            "ZONE": "zone",
            "ZONE_TYPE": "zone_type",
            "ZONE_PRIORITIZATION": "zone_prioritization",
        }
    )
    zones["zone_id"] = zones.apply(
        lambda row: make_zone_id(row["country"], row["city"], row["zone"]),
        axis=1,
    )
    return zones[
        ["zone_id", "country", "city", "zone", "zone_type", "zone_prioritization"]
    ].sort_values(["country", "city", "zone"])


def _build_metrics(input_metrics: pd.DataFrame) -> pd.DataFrame:
    observed = sorted(set(input_metrics["METRIC"].dropna().astype(str)) | {"Orders"})
    rows: list[dict[str, str]] = []
    for metric_name in observed:
        metadata = METRIC_METADATA.get(
            metric_name,
            {
                "metric_key": metric_key_for(metric_name),
                "default_direction": "unknown",
                "value_kind": "unknown",
                "outlier_policy": "none",
            },
        )
        rows.append(
            {
                "metric_key": metadata["metric_key"],
                "metric_name": metric_name,
                "source": "RAW_ORDERS" if metric_name == "Orders" else "RAW_INPUT_METRICS",
                "default_direction": metadata["default_direction"],
                "value_kind": metadata["value_kind"],
                "outlier_policy": metadata["outlier_policy"],
                "description": "",
            }
        )
    return pd.DataFrame(rows).sort_values("metric_name")


def _build_synonyms(metrics: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    for item in metrics.to_dict(orient="records"):
        key = item["metric_key"]
        candidates = {
            normalize_text(item["metric_name"]),
            normalize_text(key.replace("_", " ")),
            *[normalize_text(s) for s in METRIC_SYNONYMS.get(key, [])],
        }
        for synonym in sorted(candidates):
            rows.append({"synonym": synonym, "metric_key": key})
    return pd.DataFrame(rows).drop_duplicates("synonym").sort_values("synonym")


def _build_metric_facts(input_metrics: pd.DataFrame) -> pd.DataFrame:
    id_vars = ["COUNTRY", "CITY", "ZONE", "METRIC"]
    value_vars = [col for col in input_metrics.columns if WEEK_METRIC_RE.match(str(col))]
    facts = input_metrics.melt(
        id_vars=id_vars,
        value_vars=value_vars,
        var_name="source_column",
        value_name="value",
    ).dropna(subset=["value"])
    facts["week_offset"] = facts["source_column"].str.extract(WEEK_METRIC_RE).astype(int)
    facts["week_label"] = "L" + facts["week_offset"].astype(str) + "W"
    facts["metric_key"] = facts["METRIC"].astype(str).map(metric_key_for)
    facts["zone_id"] = facts.apply(
        lambda row: make_zone_id(row["COUNTRY"], row["CITY"], row["ZONE"]),
        axis=1,
    )
    facts = facts.rename(columns={"METRIC": "metric_name"})
    return facts[
        [
            "zone_id",
            "metric_key",
            "metric_name",
            "week_offset",
            "week_label",
            "value",
            "source_column",
        ]
    ]


def _build_order_facts(orders: pd.DataFrame) -> pd.DataFrame:
    id_vars = ["COUNTRY", "CITY", "ZONE"]
    value_vars = [col for col in orders.columns if WEEK_ORDERS_RE.match(str(col))]
    facts = orders.melt(
        id_vars=id_vars,
        value_vars=value_vars,
        var_name="source_column",
        value_name="orders",
    ).dropna(subset=["orders"])
    facts["week_offset"] = facts["source_column"].str.extract(WEEK_ORDERS_RE).astype(int)
    facts["week_label"] = "L" + facts["week_offset"].astype(str) + "W"
    facts["zone_id"] = facts.apply(
        lambda row: make_zone_id(row["COUNTRY"], row["CITY"], row["ZONE"]),
        axis=1,
    )
    return facts[["zone_id", "week_offset", "week_label", "orders", "source_column"]]

