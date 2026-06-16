from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


WEEK_METRIC_RE = re.compile(r"^L([0-8])W_(?:ROLL|VALUE)$")
WEEK_ORDERS_RE = re.compile(r"^L([0-8])W$")
UNKNOWN_DIMENSION_VALUE = "Unknown"


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


CITY_ALIASES: dict[str, dict[str, str]] = {
    "MX": {
        "cdmx": "Ciudad De Mexico",
        "ciudad de mexico": "Ciudad De Mexico",
        "ciudad de méxico": "Ciudad De Mexico",
        "d f": "Ciudad De Mexico",
        "df": "Ciudad De Mexico",
        "distrito federal": "Ciudad De Mexico",
        "mexico city": "Ciudad De Mexico",
        "mexico df": "Ciudad De Mexico",
    },
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
    city_aliases: pd.DataFrame
    metric_facts: pd.DataFrame
    order_facts: pd.DataFrame
    data_quality: dict[str, Any]

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
            "sql": {
                "dialect": "Postgres",
                "tables": {
                    "dim_zone": {
                        "grain": "one row per zone",
                        "columns": [
                            "zone_id",
                            "country",
                            "city",
                            "zone",
                            "zone_type",
                            "zone_prioritization",
                        ],
                    },
                    "dim_city_alias": {
                        "grain": "one row per searchable city alias",
                        "columns": [
                            "country",
                            "alias",
                            "city",
                        ],
                    },
                    "semantic_metric": {
                        "grain": "one row per metric definition",
                        "columns": [
                            "metric_key",
                            "metric_name",
                            "source",
                            "default_direction",
                            "value_kind",
                            "outlier_policy",
                        ],
                    },
                    "metric_synonym": {
                        "grain": "metric synonym lookup",
                        "columns": ["synonym", "metric_key"],
                    },
                    "fact_metric_week": {
                        "grain": "one row per zone, metric, and relative week",
                        "columns": [
                            "zone_id",
                            "metric_key",
                            "week_offset",
                            "week_label",
                            "value",
                            "is_outlier",
                            "source_column",
                        ],
                    },
                    "fact_orders_week": {
                        "grain": "one row per zone and relative week",
                        "columns": [
                            "zone_id",
                            "week_offset",
                            "week_label",
                            "orders",
                            "source_column",
                        ],
                    },
                },
                "join_patterns": [
                    "fact_metric_week.zone_id = dim_zone.zone_id",
                    "fact_metric_week.metric_key = semantic_metric.metric_key",
                    "fact_orders_week.zone_id = dim_zone.zone_id",
                    "Join fact_orders_week to fact_metric_week by zone_id and week_offset when comparing orders to metrics.",
                    "For user-provided city names or aliases, resolve a distinct country/city set from dim_city_alias before joining to facts.",
                ],
                "query_rules": [
                    "Use week_offset = 0 for the current/latest week.",
                    "Use week_offset between 7 and 0 for the last 8 weeks.",
                    "Use metric_key or semantic_metric.metric_name to choose metrics.",
                    "City aliases are lowercase ASCII labels in dim_city_alias.alias; for example, CDMX maps to Ciudad De Mexico.",
                    "For metric_key values with outlier_policy = 'flag', exclude fact_metric_week.is_outlier = true from averages unless the user asks to inspect outliers.",
                    "For rates, report values exactly as stored unless the answer explicitly formats them as percentages.",
                    "Business context such as problematic zones should be translated by the model into observable metric conditions.",
                ],
            },
            "data_quality": self.data_quality,
        }
        if include_examples:
            payload["examples"] = {
                "country_aliases": COUNTRY_ALIASES,
                "city_aliases": _city_alias_examples(self.city_aliases),
                "city_values_by_country": _city_values_by_country(self.zones),
                "metric_synonyms": self.metric_synonyms.groupby("metric_key")["synonym"]
                .apply(list)
                .to_dict(),
            }
        return payload


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text).strip().lower()


def normalize_alias_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", normalize_text(value)).strip()


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


def resolve_city_aliases(value: str, countries: list[str] | None = None) -> list[str]:
    key = normalize_alias_key(value)
    country_codes = countries or sorted(CITY_ALIASES)
    resolved = []
    for country in country_codes:
        city = CITY_ALIASES.get(country, {}).get(key)
        if city:
            resolved.append(city)
    return sorted(set(resolved))


def load_workbook(path: Path) -> OperationalDataset:
    input_metrics = pd.read_excel(path, sheet_name="RAW_INPUT_METRICS")
    orders = pd.read_excel(path, sheet_name="RAW_ORDERS")

    zones = _build_zones(input_metrics, orders)
    metrics = _build_metrics(input_metrics)
    synonyms = _build_synonyms(metrics)
    city_aliases = build_city_aliases(zones)
    metric_facts = _build_metric_facts(input_metrics)
    order_facts = _build_order_facts(orders)
    data_quality = _build_data_quality_report(
        input_metrics,
        orders,
        zones,
        metric_facts,
        order_facts,
    )

    return OperationalDataset(
        zones=zones,
        metrics=metrics,
        metric_synonyms=synonyms,
        city_aliases=city_aliases,
        metric_facts=metric_facts,
        order_facts=order_facts,
        data_quality=data_quality,
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
    zones["zone_type"] = zones["zone_type"].fillna(UNKNOWN_DIMENSION_VALUE)
    zones["zone_prioritization"] = zones["zone_prioritization"].fillna(UNKNOWN_DIMENSION_VALUE)
    return zones[
        ["zone_id", "country", "city", "zone", "zone_type", "zone_prioritization"]
    ].sort_values(["country", "city", "zone"])


def build_city_aliases(zones: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    city_rows = zones[["country", "city"]].dropna().drop_duplicates()
    for item in city_rows.to_dict(orient="records"):
        country = str(item["country"])
        city = str(item["city"])
        aliases = _generated_city_aliases(city)
        aliases.update(
            normalize_alias_key(alias)
            for alias, canonical_city in CITY_ALIASES.get(country, {}).items()
            if canonical_city == city
        )
        for alias in sorted(alias for alias in aliases if alias):
            rows.append({"country": country, "alias": alias, "city": city})

    return pd.DataFrame(rows).drop_duplicates(["country", "alias"]).sort_values(
        ["country", "alias"]
    )


def _generated_city_aliases(city: str) -> set[str]:
    canonical = normalize_alias_key(city)
    aliases = {canonical}
    if canonical.startswith("ciudad "):
        aliases.add(f"cd {canonical.removeprefix('ciudad ')}")
    if canonical.startswith("cd "):
        aliases.add(f"ciudad {canonical.removeprefix('cd ')}")
    return aliases


def _city_alias_examples(city_aliases: pd.DataFrame) -> dict[str, dict[str, str]]:
    if city_aliases.empty:
        return {}
    examples = city_aliases[
        city_aliases.apply(
            lambda row: row["alias"] != normalize_alias_key(row["city"]),
            axis=1,
        )
    ]
    return {
        country: dict(group[["alias", "city"]].itertuples(index=False, name=None))
        for country, group in examples.groupby("country")
    }


def _city_values_by_country(zones: pd.DataFrame) -> dict[str, list[str]]:
    return (
        zones.groupby("country")["city"]
        .apply(lambda values: sorted(set(str(value) for value in values.dropna())))
        .to_dict()
    )


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
    source = input_metrics[id_vars + value_vars].drop_duplicates()
    conflicting = source.duplicated(id_vars, keep=False)
    if conflicting.any():
        sample = source.loc[conflicting, id_vars].drop_duplicates().head(5).to_dict(orient="records")
        raise ValueError(f"Conflicting metric rows found for the same zone and metric: {sample}")

    facts = source.melt(
        id_vars=id_vars,
        value_vars=value_vars,
        var_name="source_column",
        value_name="value",
    )
    facts["value"] = pd.to_numeric(facts["value"], errors="coerce")
    facts = facts.dropna(subset=["value"])
    facts["week_offset"] = facts["source_column"].str.extract(WEEK_METRIC_RE).astype(int)
    facts["week_label"] = "L" + facts["week_offset"].astype(str) + "W"
    facts["metric_key"] = facts["METRIC"].astype(str).map(metric_key_for)
    facts["is_outlier"] = _metric_outlier_mask(facts)
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
            "is_outlier",
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
    )
    facts["orders"] = pd.to_numeric(facts["orders"], errors="coerce")
    facts = facts.dropna(subset=["orders"])
    if (facts["orders"] < 0).any():
        sample = facts[facts["orders"] < 0][id_vars + ["source_column", "orders"]].head(5)
        raise ValueError(f"Negative order values found: {sample.to_dict(orient='records')}")
    facts["week_offset"] = facts["source_column"].str.extract(WEEK_ORDERS_RE).astype(int)
    facts["week_label"] = "L" + facts["week_offset"].astype(str) + "W"
    facts["zone_id"] = facts.apply(
        lambda row: make_zone_id(row["COUNTRY"], row["CITY"], row["ZONE"]),
        axis=1,
    )
    return facts[["zone_id", "week_offset", "week_label", "orders", "source_column"]]


def _metric_outlier_mask(facts: pd.DataFrame) -> pd.Series:
    values = pd.to_numeric(facts["value"], errors="coerce")
    mask = pd.Series(False, index=facts.index)
    mask = mask | (facts["metric_key"].eq("lead_penetration") & ((values < 0) | (values > 1)))
    return mask.fillna(False).astype(bool)


def _build_data_quality_report(
    input_metrics: pd.DataFrame,
    orders: pd.DataFrame,
    zones: pd.DataFrame,
    metric_facts: pd.DataFrame,
    order_facts: pd.DataFrame,
) -> dict[str, Any]:
    metric_week_cols = [col for col in input_metrics.columns if WEEK_METRIC_RE.match(str(col))]
    order_week_cols = [col for col in orders.columns if WEEK_ORDERS_RE.match(str(col))]
    metric_id_cols = ["COUNTRY", "CITY", "ZONE", "METRIC"]
    metric_source = input_metrics[metric_id_cols + metric_week_cols]
    metric_duplicate_rows_removed = int(metric_source.duplicated().sum())

    metric_zones = input_metrics[["COUNTRY", "CITY", "ZONE"]].drop_duplicates()
    order_zones = orders[["COUNTRY", "CITY", "ZONE"]].drop_duplicates()
    order_only_zones = order_zones.merge(
        metric_zones,
        on=["COUNTRY", "CITY", "ZONE"],
        how="left",
        indicator=True,
    )
    order_only_zones = order_only_zones[order_only_zones["_merge"].eq("left_only")]
    metric_only_zones = metric_zones.merge(
        order_zones,
        on=["COUNTRY", "CITY", "ZONE"],
        how="left",
        indicator=True,
    )
    metric_only_zones = metric_only_zones[metric_only_zones["_merge"].eq("left_only")]

    rate_keys = {
        metadata["metric_key"]
        for metadata in METRIC_METADATA.values()
        if metadata["value_kind"] == "rate"
    }
    rate_facts = metric_facts[metric_facts["metric_key"].isin(rate_keys)]
    invalid_rate_facts = rate_facts[(rate_facts["value"] < 0) | (rate_facts["value"] > 1)]
    outlier_counts = (
        metric_facts[metric_facts["is_outlier"]]
        .groupby("metric_key")
        .size()
        .sort_values(ascending=False)
        .to_dict()
    )
    warnings = []
    if metric_duplicate_rows_removed:
        warnings.append(
            f"Removed {metric_duplicate_rows_removed} exact duplicate metric source rows before fact generation."
        )
    if outlier_counts:
        warnings.append(f"Flagged metric outliers by metric: {outlier_counts}.")
    missing_metadata_count = int((zones["zone_type"] == UNKNOWN_DIMENSION_VALUE).sum())
    if missing_metadata_count:
        warnings.append(
            f"{missing_metadata_count} order-only zones have no source zone_type or prioritization and are labeled Unknown."
        )

    return {
        "status": "passed_with_warnings" if warnings else "passed",
        "warnings": warnings,
        "metric_week_columns": [str(col) for col in metric_week_cols],
        "order_week_columns": [str(col) for col in order_week_cols],
        "metric_duplicate_rows_removed": metric_duplicate_rows_removed,
        "metric_fact_duplicate_keys": int(
            metric_facts.duplicated(["zone_id", "metric_key", "week_offset"]).sum()
        ),
        "order_fact_duplicate_keys": int(
            order_facts.duplicated(["zone_id", "week_offset"]).sum()
        ),
        "metric_zones": int(len(metric_zones)),
        "order_zones": int(len(order_zones)),
        "order_only_zones": int(len(order_only_zones)),
        "metric_only_zones": int(len(metric_only_zones)),
        "unknown_zone_metadata_zones": missing_metadata_count,
        "invalid_rate_metric_cells": int(len(invalid_rate_facts)),
        "outlier_cells_by_metric": {str(key): int(value) for key, value in outlier_counts.items()},
    }
