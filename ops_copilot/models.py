from __future__ import annotations

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
    outlier_policy: OutlierPolicy = "flag"
    include_diagnostics: bool = False
    diagnostic_metrics: list[str] = Field(default_factory=list)

    @field_validator("dimensions", "metrics", "diagnostic_metrics", mode="before")
    @classmethod
    def coerce_string_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return list(value)


class ChartSpec(BaseModel):
    recommended: bool
    type: ChartType
    x: str | None = None
    y: str | None = None
    series: str | None = None
    chartjs: dict[str, Any] | None = None


class QueryResult(BaseModel):
    query_id: str
    answer_type: str
    period_label: str
    filters_applied: dict[str, list[str]]
    rows: list[dict[str, Any]]
    chart: ChartSpec
    caveats: list[str] = Field(default_factory=list)
    suggested_followups: list[str] = Field(default_factory=list)
    row_count: int

