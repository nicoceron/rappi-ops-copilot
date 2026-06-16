from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


Direction = Literal["higher_better", "lower_better", "unknown"]
ValueKind = Literal["rate", "currency_per_order", "count", "index", "unknown"]
Intent = Literal[
    "lookup",
    "rank",
    "aggregate",
    "compare",
    "trend",
    "segment",
    "diagnose",
    "growth",
    "correlate",
    "export",
]
Aggregation = Literal[
    "none",
    "avg",
    "sum",
    "min",
    "max",
    "median",
    "pct_change",
    "absolute_change",
]
ChartType = Literal["none", "table", "bar", "line", "scatter"]
OutlierPolicy = Literal["none", "flag", "exclude"]
ExportFormat = Literal["csv", "pdf"]


class Period(BaseModel):
    type: Literal["relative_weeks"] = "relative_weeks"
    start_offset: int = Field(default=0, ge=0, le=8)
    end_offset: int = Field(default=0, ge=0, le=8)

    @model_validator(mode="after")
    def validate_offsets(self) -> "Period":
        if self.start_offset < self.end_offset:
            raise ValueError("start_offset must be greater than or equal to end_offset")
        return self


class SortField(BaseModel):
    field: str
    direction: Literal["asc", "desc"] = "desc"


class SemanticQuery(BaseModel):
    question: str = ""
    language: Literal["es", "en", "auto"] = "auto"
    intent: Intent
    metrics: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    filters: dict[str, list[str] | str] = Field(default_factory=dict)
    period: Period = Field(default_factory=Period)
    aggregation: Aggregation = "none"
    sort: list[SortField] = Field(default_factory=list)
    limit: int = Field(default=50, ge=1, le=500)
    visualization: ChartType = "table"
    outlier_policy: OutlierPolicy = "exclude"
    include_diagnostics: bool = False
    diagnostic_metrics: list[str] = Field(default_factory=list)

    @field_validator("dimensions", "metrics", "diagnostic_metrics", mode="before")
    @classmethod
    def coerce_string_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            text = value.strip()
            if not text or text in {"[]", "{}"}:
                return []
            try:
                return cls.coerce_string_list(json.loads(text))
            except json.JSONDecodeError:
                return [value]
        if isinstance(value, dict):
            if not value:
                return []
            for key in ("values", "items", "metrics", "dimensions", "diagnostic_metrics"):
                if key in value:
                    return cls.coerce_string_list(value[key])
            if all(str(key).isdigit() for key in value):
                return [str(value[key]) for key in sorted(value, key=lambda item: int(str(item)))]
            return [str(item) for item in value.values() if item is not None and str(item).strip()]
        return [str(item) for item in value if item is not None and str(item).strip()]

    @field_validator("sort", mode="before")
    @classmethod
    def coerce_sort_list(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, str):
            text = value.strip()
            if not text or text in {"[]", "{}"}:
                return []
            try:
                return cls.coerce_sort_list(json.loads(text))
            except json.JSONDecodeError:
                return [{"field": value, "direction": "desc"}]
        if isinstance(value, dict):
            if not value:
                return []
            for key in ("values", "items", "sort"):
                if key in value:
                    return cls.coerce_sort_list(value[key])
            if "field" in value:
                return [value]
            return list(value.values())
        return list(value)


class ChartSpec(BaseModel):
    recommended: bool
    type: ChartType
    x: str | None = None
    y: str | None = None
    series: str | None = None
    chartjs: dict[str, Any] | None = None


class ExportDownload(BaseModel):
    format: ExportFormat
    label: str
    href: str
    browser_url: str
    api_path: str
    content_type: str


class QueryResult(BaseModel):
    query_id: str
    answer_type: str
    period_label: str
    filters_applied: dict[str, list[str]]
    rows: list[dict[str, Any]]
    chart: ChartSpec
    caveats: list[str] = Field(default_factory=list)
    suggested_followups: list[str] = Field(default_factory=list)
    exports: list[ExportDownload] = Field(default_factory=list)
    row_count: int
