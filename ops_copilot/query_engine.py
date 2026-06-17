from __future__ import annotations

import math
import uuid
from typing import Any

import pandas as pd

from ops_copilot.charting import build_chart_spec
from ops_copilot.data_loader import (
    DIMENSION_COLUMNS,
    OperationalDataset,
    normalize_alias_key,
    normalize_text,
    resolve_country,
)
from ops_copilot.models import ChartSpec, QueryResult, SemanticQuery


DEFAULT_DIAGNOSTIC_METRICS = [
    "Perfect Orders",
    "Gross Profit UE",
    "Lead Penetration",
]


class QueryValidationError(ValueError):
    """Raised when the semantic query cannot be safely executed."""


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for item in items:
        if item and item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


class QueryEngine:
    def __init__(self, dataset: OperationalDataset):
        self.dataset = dataset
        self._metric_lookup = self._build_metric_lookup()

    def schema(self, include_examples: bool = True) -> dict[str, Any]:
        return self.dataset.schema(include_examples=include_examples)

    def execute(self, query: SemanticQuery) -> QueryResult:
        if query.intent == "rank":
            return self._rank(query)
        if query.intent in {"aggregate", "compare"}:
            return self._aggregate_or_compare(query)
        if query.intent == "trend":
            return self._trend(query)
        if query.intent == "segment":
            return self._segment(query)
        if query.intent == "growth":
            return self._growth(query)
        if query.intent == "diagnose":
            return self._diagnose(query)
        if query.intent == "correlate":
            return self._correlate(query)
        if query.intent == "lookup":
            return self._lookup(query)
        raise QueryValidationError(f"Unsupported intent: {query.intent}")

    def _rank(self, query: SemanticQuery) -> QueryResult:
        metric_key = self._require_metric(query.metrics)
        dimensions = self._dimensions_or_default(query.dimensions, ["country", "city", "zone"])
        facts, filters_applied = self._metric_rows(metric_key, query)
        value_column = "value"
        caveats = self._caveats(metric_key, query, facts)

        if query.aggregation == "none" and query.period.start_offset == query.period.end_offset:
            selected_columns = dimensions + [value_column]
            if "is_outlier" in facts.columns:
                selected_columns.append("is_outlier")
            grouped = facts[selected_columns].copy()
            if "zone" in grouped.columns:
                grouped = grouped.drop_duplicates(dimensions)
        else:
            aggregation = "avg" if query.aggregation == "none" else query.aggregation
            grouped = self._aggregate_frame(facts, dimensions, value_column, aggregation)

        sort_field = self._sort_field(query, default="value")
        grouped = self._sort_rows(grouped, sort_field, query.limit)
        rows = self._records(grouped)
        metric_name = self._metric_name(metric_key)
        return self._result(
            query=query,
            answer_type="ranking",
            rows=rows,
            filters_applied=filters_applied,
            chart=self._chart(rows, query.visualization or "bar", x=self._best_label(dimensions), y="value"),
            caveats=caveats,
            suggestions=[
                f"Comparar {metric_name} contra Perfect Orders",
                "Ver la tendencia de las ultimas 8 semanas",
                "Exportar este ranking a CSV",
            ],
        )

    def _aggregate_or_compare(self, query: SemanticQuery) -> QueryResult:
        metric_keys = self._metric_keys(query.metrics)
        dimensions = self._dimensions_or_default(query.dimensions, ["country"])
        aggregation = "avg" if query.aggregation == "none" else query.aggregation
        frames = []
        filters_applied: dict[str, list[str]] = {}
        caveats = self._common_caveats(query)

        for metric_key in metric_keys:
            facts, filters_applied = self._metric_rows(metric_key, query)
            caveats.extend(self._caveats(metric_key, query, facts, include_common=False))
            grouped = self._aggregate_frame(facts, dimensions, "value", aggregation)
            grouped.insert(0, "metric", self._metric_name(metric_key))
            frames.append(grouped)

        result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        sort_field = self._sort_field(query, default="value")
        result = self._sort_rows(result, sort_field, query.limit)
        rows = self._records(result)
        return self._result(
            query=query,
            answer_type="comparison" if query.intent == "compare" else "aggregation",
            rows=rows,
            filters_applied=filters_applied,
            chart=self._chart(rows, query.visualization or "bar", x=self._best_label(dimensions), y="value"),
            caveats=_dedupe(caveats),
            suggestions=[
                "Bajar al detalle por ciudad o zona",
                "Comparar contra la tendencia de las ultimas 8 semanas",
                "Revisar las zonas con mayor deterioro",
            ],
        )

    def _trend(self, query: SemanticQuery) -> QueryResult:
        metric_keys = self._metric_keys(query.metrics)
        dimensions = self._dimensions_or_default(query.dimensions, [])
        group_dimensions = dimensions + ["week_offset", "week_label"]
        frames = []
        filters_applied: dict[str, list[str]] = {}
        caveats = self._common_caveats(query)

        for metric_key in metric_keys:
            facts, filters_applied = self._metric_rows(metric_key, query)
            caveats.extend(self._caveats(metric_key, query, facts, include_common=False))
            aggregation = "avg" if query.aggregation == "none" else query.aggregation
            grouped = self._aggregate_frame(facts, group_dimensions, "value", aggregation)
            grouped.insert(0, "metric", self._metric_name(metric_key))
            frames.append(grouped)

        result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        result = result.sort_values(["metric", "week_offset"], ascending=[True, False])
        rows = self._records(result.head(query.limit))
        return self._result(
            query=query,
            answer_type="trend",
            rows=rows,
            filters_applied=filters_applied,
            chart=self._chart(rows, "line", x="week_label", y="value", series="metric"),
            caveats=_dedupe(caveats),
            suggestions=[
                "Comparar esta tendencia contra zonas similares",
                "Ver las zonas que mas se deterioraron en el periodo",
                "Exportar la serie para analisis externo",
            ],
        )

    def _segment(self, query: SemanticQuery) -> QueryResult:
        metric_keys = self._metric_keys(query.metrics)
        if len(metric_keys) < 2:
            raise QueryValidationError("Segment queries require at least two metrics.")
        x_key, y_key = metric_keys[:2]
        x_rows, filters_applied = self._metric_rows(x_key, query)
        y_rows, _ = self._metric_rows(y_key, query)
        caveats = _dedupe(
            self._caveats(x_key, query, x_rows)
            + self._caveats(y_key, query, y_rows, include_common=False)
        )

        x_current = self._current_zone_values(x_rows, x_key, "x_value")
        y_current = self._current_zone_values(y_rows, y_key, "y_value")
        joined = x_current.merge(y_current, on=["zone_id", "country", "city", "zone"], how="inner")
        if joined.empty:
            return self._empty_result(query, filters_applied)

        x_threshold = joined["x_value"].quantile(0.75)
        y_threshold = joined["y_value"].quantile(0.25)
        result = joined[(joined["x_value"] >= x_threshold) & (joined["y_value"] <= y_threshold)].copy()
        result = result.rename(
            columns={
                "x_value": self._metric_name(x_key),
                "y_value": self._metric_name(y_key),
            }
        )
        result = result.sort_values([self._metric_name(x_key), self._metric_name(y_key)], ascending=[False, True])
        rows = self._records(result.head(query.limit))
        return self._result(
            query=query,
            answer_type="segment",
            rows=rows,
            filters_applied=filters_applied,
            chart=self._chart(
                rows,
                "scatter",
                x=self._metric_name(x_key),
                y=self._metric_name(y_key),
            ),
            caveats=caveats
            + [
                f"High {self._metric_name(x_key)} means >= p75 ({x_threshold:.4g}) within the filtered universe.",
                f"Low {self._metric_name(y_key)} means <= p25 ({y_threshold:.4g}) within the filtered universe.",
            ],
            suggestions=[
                "Priorizar estas zonas para diagnostico operativo",
                "Ver si el patron se mantiene en las ultimas 8 semanas",
                "Exportar el listado a CSV",
            ],
        )

    def _growth(self, query: SemanticQuery) -> QueryResult:
        filters_applied = {}
        zones = self._filtered_zones(query.filters)
        filters_applied = self._filters_applied(zones, query.filters)
        facts = self.dataset.order_facts.merge(zones, on="zone_id", how="inner")
        start_offset = query.period.start_offset or 4
        end_offset = query.period.end_offset
        pivot = facts[facts["week_offset"].isin([start_offset, end_offset])].pivot_table(
            index=["zone_id", "country", "city", "zone"],
            columns="week_offset",
            values="orders",
            aggfunc="sum",
        )
        if start_offset not in pivot.columns or end_offset not in pivot.columns:
            return self._empty_result(query, filters_applied)
        result = pivot.reset_index().rename(
            columns={start_offset: "start_orders", end_offset: "end_orders"}
        )
        result["absolute_change"] = result["end_orders"] - result["start_orders"]
        result["pct_change"] = result.apply(
            lambda row: None
            if row["start_orders"] == 0
            else (row["end_orders"] - row["start_orders"]) / row["start_orders"],
            axis=1,
        )

        if query.include_diagnostics:
            result = self._attach_diagnostics(result, query)

        sort_field = self._sort_field(query, default="pct_change")
        result = self._sort_rows(result, sort_field, query.limit)
        rows = self._records(result)
        return self._result(
            query=query,
            answer_type="growth",
            rows=rows,
            filters_applied=filters_applied,
            chart=self._chart(rows, "bar", x="zone", y=sort_field.field),
            caveats=[
                "Growth is calculated from the first to the last selected relative week.",
                "Possible explanations are hypotheses from related metrics, not causal proof.",
            ],
            suggestions=[
                "Revisar si el crecimiento coincide con Perfect Orders estable",
                "Comparar crecimiento absoluto vs crecimiento porcentual",
                "Exportar las zonas con diagnosticos",
            ],
        )

    def _diagnose(self, query: SemanticQuery) -> QueryResult:
        zones = self._filtered_zones(query.filters)
        filters_applied = self._filters_applied(zones, query.filters)
        metric_keys = self._metric_keys(query.metrics or DEFAULT_DIAGNOSTIC_METRICS)
        current_values = []
        caveats = self._common_caveats(query)

        for metric_key in metric_keys:
            q = query.model_copy(update={"metrics": [metric_key], "period": query.period})
            facts, _ = self._metric_rows(metric_key, q)
            caveats.extend(self._caveats(metric_key, query, facts, include_common=False))
            current = self._current_zone_values(facts, metric_key, metric_key)
            metadata = self._metric_metadata(metric_key)
            direction = metadata["default_direction"]
            percentile = current[metric_key].rank(pct=True)
            if direction == "higher_better":
                current[f"{metric_key}_risk"] = 1 - percentile
            elif direction == "lower_better":
                current[f"{metric_key}_risk"] = percentile
            else:
                current[f"{metric_key}_risk"] = 0
            current_values.append(
                current[["zone_id", "country", "city", "zone", metric_key, f"{metric_key}_risk"]]
            )

        result = current_values[0]
        for frame in current_values[1:]:
            result = result.merge(frame, on=["zone_id", "country", "city", "zone"], how="outer")

        orders_q = query.model_copy(update={"period": query.period.model_copy(update={"start_offset": 4})})
        growth = self._growth_frame(orders_q, zones)
        result = result.merge(growth, on=["zone_id", "country", "city", "zone"], how="left")
        risk_columns = [col for col in result.columns if col.endswith("_risk")]
        growth_percentile = result["pct_change"].rank(pct=True, ascending=True)
        result["orders_growth_risk"] = (1 - growth_percentile).fillna(0)
        risk_columns.append("orders_growth_risk")
        result = result.merge(
            zones[["zone_id", "zone_type", "zone_prioritization"]],
            on="zone_id",
            how="left",
        )
        priority_boost = result["zone_prioritization"].map(
            {"High Priority": 0.15, "Prioritized": 0.05}
        ).fillna(0)
        result["problem_score"] = result[risk_columns].fillna(0).mean(axis=1) + priority_boost
        result = result.sort_values("problem_score", ascending=False).head(query.limit)

        rename_map = {key: self._metric_name(key) for key in metric_keys}
        result = result.rename(columns=rename_map)
        rows = self._records(result)
        return self._result(
            query=query,
            answer_type="diagnosis",
            rows=rows,
            filters_applied=filters_applied,
            chart=self._chart(rows, "bar", x="zone", y="problem_score"),
            caveats=_dedupe(
                caveats
                + [
                    "Problematic zones are scored from weak current metrics, order growth risk, and prioritization.",
                    "The scoring definition should be calibrated with business owners before production use.",
                ]
            ),
            suggestions=[
                "Ver el detalle de cada metrica para las primeras zonas",
                "Separar zonas Wealthy y Non Wealthy",
                "Exportar el diagnostico a PDF",
            ],
        )

    def _correlate(self, query: SemanticQuery) -> QueryResult:
        metric_keys = self._metric_keys(query.metrics)
        if len(metric_keys) < 2:
            raise QueryValidationError("Correlation queries require at least two metrics.")
        x_key, y_key = metric_keys[:2]
        x_rows, filters_applied = self._metric_rows(x_key, query)
        y_rows, _ = self._metric_rows(y_key, query)
        caveats = _dedupe(
            self._caveats(x_key, query, x_rows)
            + self._caveats(y_key, query, y_rows, include_common=False)
            + ["Correlation is not causation."]
        )
        joined = self._current_zone_values(x_rows, x_key, "x_value").merge(
            self._current_zone_values(y_rows, y_key, "y_value"),
            on=["zone_id", "country", "city", "zone"],
            how="inner",
        )
        corr = joined["x_value"].corr(joined["y_value"]) if len(joined) > 1 else None
        rows = [
            {
                "metric_x": self._metric_name(x_key),
                "metric_y": self._metric_name(y_key),
                "pearson_correlation": corr,
                "n_zones": int(len(joined)),
            }
        ]
        return self._result(
            query=query,
            answer_type="correlation",
            rows=self._records(pd.DataFrame(rows)),
            filters_applied=filters_applied,
            chart=self._chart(
                self._records(
                    joined.rename(
                        columns={
                            "x_value": self._metric_name(x_key),
                            "y_value": self._metric_name(y_key),
                        }
                    ).head(query.limit)
                ),
                "scatter",
                x=self._metric_name(x_key),
                y=self._metric_name(y_key),
            ),
            caveats=caveats,
            suggestions=[
                "Revisar outliers que puedan explicar la correlacion",
                "Calcular la correlacion por pais",
            ],
        )

    def _lookup(self, query: SemanticQuery) -> QueryResult:
        metric_keys = self._metric_keys(query.metrics)
        frames = []
        filters_applied: dict[str, list[str]] = {}
        caveats = self._common_caveats(query)
        for metric_key in metric_keys:
            facts, filters_applied = self._metric_rows(metric_key, query)
            caveats.extend(self._caveats(metric_key, query, facts, include_common=False))
            frame = facts[
                [
                    "country",
                    "city",
                    "zone",
                    "zone_type",
                    "zone_prioritization",
                    "week_label",
                    "value",
                    "is_outlier",
                ]
            ].copy()
            frame.insert(0, "metric", self._metric_name(metric_key))
            frames.append(frame)
        result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        rows = self._records(result.head(query.limit))
        return self._result(
            query=query,
            answer_type="lookup",
            rows=rows,
            filters_applied=filters_applied,
            chart=self._chart(rows, "table"),
            caveats=_dedupe(caveats),
            suggestions=[
                "Ver la tendencia de este resultado",
                "Compararlo contra zonas similares",
            ],
        )

    def _metric_rows(
        self, metric_key: str, query: SemanticQuery
    ) -> tuple[pd.DataFrame, dict[str, list[str]]]:
        zones = self._filtered_zones(query.filters)
        filters_applied = self._filters_applied(zones, query.filters)
        offsets = set(range(query.period.end_offset, query.period.start_offset + 1))
        if metric_key == "orders":
            facts = self.dataset.order_facts[self.dataset.order_facts["week_offset"].isin(offsets)].copy()
            facts["metric_key"] = "orders"
            facts["metric_name"] = "Orders"
            facts["value"] = facts["orders"]
            facts["is_outlier"] = False
        else:
            facts = self.dataset.metric_facts[
                (self.dataset.metric_facts["metric_key"] == metric_key)
                & (self.dataset.metric_facts["week_offset"].isin(offsets))
            ].copy()
            if "is_outlier" not in facts.columns:
                facts["is_outlier"] = False
        facts = facts.merge(zones, on="zone_id", how="inner")
        outlier_count = int(facts["is_outlier"].fillna(False).sum())
        if query.outlier_policy == "exclude" and outlier_count:
            facts = facts[~facts["is_outlier"].fillna(False)].copy()
        if facts.empty:
            raise QueryValidationError("No rows matched the selected filters and period.")
        facts.attrs["outlier_count"] = outlier_count
        return facts, filters_applied

    def _filtered_zones(self, filters: dict[str, list[str] | str]) -> pd.DataFrame:
        zones = self.dataset.zones.copy()
        country_filter_values = self._country_filter_values(filters)
        for raw_key, raw_value in filters.items():
            key = normalize_text(raw_key).replace(" ", "_")
            if key not in {"country", "city", "zone", "zone_type", "zone_prioritization"}:
                continue
            values = raw_value if isinstance(raw_value, list) else [raw_value]
            if key == "country":
                country_values = [resolve_country(v) for v in values]
                zones = zones[zones["country"].isin(country_values)]
            else:
                expanded_values = list(values)
                if key == "city":
                    for value in values:
                        expanded_values.extend(
                            self._resolve_city_aliases(value, country_filter_values)
                        )
                normalized_values = [normalize_text(v) for v in expanded_values]
                column_norm = zones[key].fillna("").map(normalize_text)
                exact = column_norm.isin(normalized_values)
                if exact.any():
                    zones = zones[exact]
                else:
                    contains = column_norm.apply(
                        lambda candidate: any(value in candidate for value in normalized_values)
                    )
                    zones = zones[contains]
        if zones.empty:
            raise QueryValidationError("No zones matched the selected filters.")
        return zones

    def _country_filter_values(self, filters: dict[str, list[str] | str]) -> list[str] | None:
        for raw_key, raw_value in filters.items():
            key = normalize_text(raw_key).replace(" ", "_")
            if key != "country":
                continue
            values = raw_value if isinstance(raw_value, list) else [raw_value]
            return [resolve_country(value) for value in values]
        return None

    def _resolve_city_aliases(self, value: str, countries: list[str] | None = None) -> list[str]:
        aliases = self.dataset.city_aliases
        if aliases.empty:
            return []
        alias_key = normalize_alias_key(value)
        matches = aliases[aliases["alias"] == alias_key]
        if countries:
            matches = matches[matches["country"].isin(countries)]
        return sorted(str(city) for city in matches["city"].dropna().unique().tolist())

    def _filters_applied(
        self, zones: pd.DataFrame, filters: dict[str, list[str] | str]
    ) -> dict[str, list[str]]:
        applied: dict[str, list[str]] = {}
        for raw_key in filters:
            key = normalize_text(raw_key).replace(" ", "_")
            if key in zones.columns:
                applied[key] = sorted(str(v) for v in zones[key].dropna().unique().tolist())
        return applied

    def _aggregate_frame(
        self, frame: pd.DataFrame, dimensions: list[str], value_column: str, aggregation: str
    ) -> pd.DataFrame:
        if not dimensions:
            dimensions = ["metric_name"] if "metric_name" in frame.columns else []
        agg_map = {
            "avg": "mean",
            "sum": "sum",
            "min": "min",
            "max": "max",
            "median": "median",
            "none": "mean",
        }
        if aggregation not in agg_map:
            raise QueryValidationError(f"Aggregation {aggregation} is not valid for this query.")
        aggregations: dict[str, tuple[str, str]] = {
            "value": (value_column, agg_map[aggregation]),
            "n_zones": ("zone_id", "nunique"),
        }
        if "is_outlier" in frame.columns:
            aggregations["outlier_count"] = ("is_outlier", "sum")
        grouped = frame.groupby(dimensions, dropna=False).agg(**aggregations).reset_index()
        return grouped

    def _current_zone_values(
        self, facts: pd.DataFrame, metric_key: str, value_name: str
    ) -> pd.DataFrame:
        week = facts["week_offset"].min()
        current = facts[facts["week_offset"] == week][
            ["zone_id", "country", "city", "zone", "value"]
        ].copy()
        return current.rename(columns={"value": value_name})

    def _growth_frame(self, query: SemanticQuery, zones: pd.DataFrame) -> pd.DataFrame:
        facts = self.dataset.order_facts.merge(zones, on="zone_id", how="inner")
        start_offset = query.period.start_offset or 4
        end_offset = query.period.end_offset
        pivot = facts[facts["week_offset"].isin([start_offset, end_offset])].pivot_table(
            index=["zone_id", "country", "city", "zone"],
            columns="week_offset",
            values="orders",
            aggfunc="sum",
        )
        if start_offset not in pivot.columns or end_offset not in pivot.columns:
            return pd.DataFrame(columns=["zone_id", "country", "city", "zone", "pct_change"])
        result = pivot.reset_index().rename(
            columns={start_offset: "start_orders", end_offset: "end_orders"}
        )
        result["pct_change"] = result.apply(
            lambda row: None
            if row["start_orders"] == 0
            else (row["end_orders"] - row["start_orders"]) / row["start_orders"],
            axis=1,
        )
        return result[["zone_id", "country", "city", "zone", "pct_change"]]

    def _attach_diagnostics(self, result: pd.DataFrame, query: SemanticQuery) -> pd.DataFrame:
        metric_names = query.diagnostic_metrics or DEFAULT_DIAGNOSTIC_METRICS
        for metric_key in self._metric_keys(metric_names):
            q = query.model_copy(update={"metrics": [metric_key]})
            facts, _ = self._metric_rows(metric_key, q)
            current = self._current_zone_values(facts, metric_key, f"{metric_key}_current")
            result = result.merge(
                current[["zone_id", f"{metric_key}_current"]],
                on="zone_id",
                how="left",
            )
        return result

    def _build_metric_lookup(self) -> dict[str, str]:
        lookup: dict[str, str] = {}
        for item in self.dataset.metrics.to_dict(orient="records"):
            lookup[normalize_text(item["metric_key"])] = item["metric_key"]
            lookup[normalize_text(item["metric_name"])] = item["metric_key"]
        for item in self.dataset.metric_synonyms.to_dict(orient="records"):
            lookup[normalize_text(item["synonym"])] = item["metric_key"]
        return lookup

    def _metric_keys(self, metrics: list[str]) -> list[str]:
        if not metrics:
            raise QueryValidationError("At least one metric is required.")
        keys = []
        for metric in metrics:
            normalized = normalize_text(metric)
            if normalized not in self._metric_lookup:
                valid = ", ".join(self.dataset.metrics["metric_name"].sort_values().tolist())
                raise QueryValidationError(f"Unknown metric '{metric}'. Valid metrics: {valid}")
            keys.append(self._metric_lookup[normalized])
        return keys

    def _require_metric(self, metrics: list[str]) -> str:
        return self._metric_keys(metrics)[0]

    def _metric_metadata(self, metric_key: str) -> dict[str, str]:
        row = self.dataset.metrics[self.dataset.metrics["metric_key"] == metric_key]
        if row.empty:
            raise QueryValidationError(f"Unknown metric key: {metric_key}")
        return row.iloc[0].to_dict()

    def _metric_name(self, metric_key: str) -> str:
        return str(self._metric_metadata(metric_key)["metric_name"])

    def _dimensions_or_default(self, dimensions: list[str], default: list[str]) -> list[str]:
        values = dimensions or default
        normalized = []
        for dim in values:
            key = normalize_text(dim).replace(" ", "_")
            if key not in DIMENSION_COLUMNS:
                raise QueryValidationError(
                    f"Unknown dimension '{dim}'. Valid dimensions: {', '.join(sorted(DIMENSION_COLUMNS))}"
                )
            normalized.append(DIMENSION_COLUMNS[key])
        return normalized

    def _sort_field(self, query: SemanticQuery, default: str) -> Any:
        if not query.sort:
            return type("Sort", (), {"field": default, "direction": "desc"})()
        sort = query.sort[0]
        field = sort.field
        if field in query.metrics:
            field = "value"
        return type("Sort", (), {"field": field, "direction": sort.direction})()

    def _sort_rows(self, frame: pd.DataFrame, sort_field: Any, limit: int) -> pd.DataFrame:
        if frame.empty:
            return frame
        field = sort_field.field
        if field not in frame.columns:
            field = "value" if "value" in frame.columns else frame.columns[-1]
        ascending = sort_field.direction == "asc"
        return frame.sort_values(field, ascending=ascending).head(limit)

    def _best_label(self, dimensions: list[str]) -> str:
        for candidate in ["zone", "city", "country", "zone_type", "zone_prioritization", "week_label"]:
            if candidate in dimensions:
                return candidate
        return dimensions[0] if dimensions else "metric"

    def _period_label(self, query: SemanticQuery) -> str:
        if query.period.start_offset == query.period.end_offset:
            return f"L{query.period.end_offset}W (most recent available week)" if query.period.end_offset == 0 else f"L{query.period.end_offset}W"
        return f"L{query.period.start_offset}W through L{query.period.end_offset}W"

    def _common_caveats(self, query: SemanticQuery) -> list[str]:
        caveats = []
        if query.aggregation == "avg":
            caveats.append("Averages are simple zone averages because denominators are not available.")
        if query.period.start_offset == 0 and query.period.end_offset == 0:
            caveats.append("L0W is the most recent available week, not a calendar date.")
        return caveats

    def _caveats(
        self,
        metric_key: str,
        query: SemanticQuery,
        frame: pd.DataFrame,
        *,
        include_common: bool = True,
    ) -> list[str]:
        caveats = self._common_caveats(query) if include_common else []
        outlier_count = int(frame.attrs.get("outlier_count", 0))
        if outlier_count and query.outlier_policy in {"flag", "exclude"}:
            metric_name = self._metric_name(metric_key)
            action = "excluded" if query.outlier_policy == "exclude" else "flagged"
            caveats.append(
                f"{metric_name} outlier policy: {action} {outlier_count} source rows."
            )
        return caveats

    def _chart(
        self,
        rows: list[dict[str, Any]],
        chart_type: str,
        x: str | None = None,
        y: str | None = None,
        series: str | None = None,
    ) -> ChartSpec:
        chart = build_chart_spec(rows, chart_type, x=x, y=y, series=series)
        if not chart.recommended:
            return chart
        chartjs = self._chartjs(rows, chart_type, x, y, series)
        chart.chartjs = chartjs
        return chart

    def _chartjs(
        self,
        rows: list[dict[str, Any]],
        chart_type: str,
        x: str | None,
        y: str | None,
        series: str | None,
    ) -> dict[str, Any]:
        if not x or not y:
            return {}
        labels = [str(row.get(x, "")) for row in rows]
        if series:
            datasets = []
            for series_value in sorted({str(row.get(series, "")) for row in rows}):
                series_rows = [row for row in rows if str(row.get(series, "")) == series_value]
                datasets.append(
                    {
                        "label": series_value,
                        "data": [row.get(y) for row in series_rows],
                    }
                )
            labels = [str(row.get(x, "")) for row in rows]
        else:
            datasets = [{"label": y, "data": [row.get(y) for row in rows]}]
        return {
            "type": chart_type if chart_type != "bar" else "bar",
            "data": {"labels": labels, "datasets": datasets},
            "options": {"responsive": True, "plugins": {"legend": {"display": bool(series)}}},
        }

    def _records(self, frame: pd.DataFrame | list[dict[str, Any]]) -> list[dict[str, Any]]:
        records = frame if isinstance(frame, list) else frame.to_dict(orient="records")
        cleaned = []
        for row in records:
            cleaned_row = {}
            for key, value in row.items():
                if pd.isna(value):
                    cleaned_row[key] = None
                elif hasattr(value, "item"):
                    cleaned_row[key] = value.item()
                elif isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                    cleaned_row[key] = None
                else:
                    cleaned_row[key] = value
            cleaned.append(cleaned_row)
        return cleaned

    def _empty_result(
        self, query: SemanticQuery, filters_applied: dict[str, list[str]]
    ) -> QueryResult:
        return self._result(
            query=query,
            answer_type=query.intent,
            rows=[],
            filters_applied=filters_applied,
            chart=ChartSpec(recommended=False, type="table"),
            caveats=["No rows matched the selected filters and period."],
            suggestions=["Relax filters or choose a different metric."],
        )

    def _result(
        self,
        query: SemanticQuery,
        answer_type: str,
        rows: list[dict[str, Any]],
        filters_applied: dict[str, list[str]],
        chart: ChartSpec,
        caveats: list[str],
        suggestions: list[str],
    ) -> QueryResult:
        return QueryResult(
            query_id=str(uuid.uuid4()),
            answer_type=answer_type,
            period_label=self._period_label(query),
            filters_applied=filters_applied,
            rows=rows,
            chart=chart,
            caveats=caveats,
            suggested_followups=suggestions,
            row_count=len(rows),
        )
