from __future__ import annotations

import math
import re
import unicodedata
from typing import Any

from ops_copilot.models import ChartSpec, ChartType


MAX_LINE_SERIES = 10


def build_chart_spec(
    rows: list[dict[str, Any]],
    requested_type: str,
    *,
    columns: list[str] | None = None,
    x: str | None = None,
    y: str | None = None,
    series: str | None = None,
) -> ChartSpec:
    """Build the render-ready chart payload consumed by chat and LaTeX exports."""

    visible_columns = columns or _columns_from_rows(rows)
    chart_type = resolve_chart_type(requested_type, rows, visible_columns, preferred_x=x)
    if chart_type in {"none", "table"} or not rows or not visible_columns:
        return ChartSpec(recommended=False, type=chart_type)

    if chart_type == "line":
        chart = _line_chart_from_rows(
            rows,
            visible_columns,
            preferred_x=x,
            preferred_y=y,
            preferred_series=series,
        )
    elif chart_type == "scatter":
        chart = _scatter_chart_from_rows(rows, visible_columns, preferred_x=x, preferred_y=y)
    else:
        chart = _bar_chart_from_rows(rows, visible_columns, preferred_x=x, preferred_y=y)

    return chart or ChartSpec(recommended=False, type="table")


def resolve_chart_type(
    requested_type: str,
    rows: list[dict[str, Any]],
    columns: list[str],
    *,
    preferred_x: str | None = None,
) -> ChartType:
    hint = _normalize_chart_type(requested_type)
    if hint in {"none", "table"}:
        return hint
    if not rows or not columns:
        return "table"
    if _is_small_segment_comparison(rows, columns):
        return "bar" if _has_bar_shape(rows, columns) else "table"
    if hint == "line":
        x_key = _valid_column(preferred_x, columns) or _select_time_key(columns)
        return "line" if x_key and _primary_numeric_columns(rows, columns, x_key) else "table"
    if hint == "scatter":
        if _has_scatter_shape(rows, columns):
            return "scatter"
        return "bar" if _has_bar_shape(rows, columns) else "table"
    if hint == "bar":
        return "bar" if _has_bar_shape(rows, columns) else "table"

    x_key = _valid_column(preferred_x, columns) or _select_time_key(columns)
    if x_key and _primary_numeric_columns(rows, columns, x_key):
        return "line"
    if _has_bar_shape(rows, columns):
        return "bar"
    return "table"


def _normalize_chart_type(value: str) -> str:
    text = str(value or "").strip().lower()
    if text in {"none", "table", "bar", "line", "scatter"}:
        return text
    if text in {"column", "columns", "pie", "donut", "histogram"}:
        return "bar"
    if text in {"trend", "timeseries", "time_series", "area"}:
        return "line"
    if text in {"bubble"}:
        return "scatter"
    if text in {"", "auto", "chart", "graph", "plot", "visualization"}:
        return "auto"
    return "table"


def _bar_chart_from_rows(
    rows: list[dict[str, Any]],
    columns: list[str],
    *,
    preferred_x: str | None,
    preferred_y: str | None,
) -> ChartSpec | None:
    x_key = _valid_column(preferred_x, columns) or _select_category_key(columns, rows)
    if not x_key:
        return None

    is_segment_comparison = _is_small_segment_comparison(rows, columns)
    y_keys = _primary_numeric_columns(rows, columns, x_key, preferred_y=preferred_y)
    y_keys = y_keys[: 1 if is_segment_comparison else 2]
    if not y_keys:
        return None

    data = []
    for row in rows:
        label = _clean_label(row.get(x_key))
        if not label:
            continue
        point: dict[str, Any] = {x_key: label}
        for key in y_keys:
            value = _to_float(row.get(key))
            if value is not None:
                point[key] = value
        if any(isinstance(point.get(key), int | float) for key in y_keys):
            data.append(point)

    if not data:
        return None

    title = f"Bar chart: {', '.join(y_keys)} by {x_key}"
    return ChartSpec(
        recommended=True,
        type="bar",
        title=title,
        x=x_key,
        y=y_keys[0],
        xKey=x_key,
        yKeys=y_keys,
        data=data,
    )


def _line_chart_from_rows(
    rows: list[dict[str, Any]],
    columns: list[str],
    *,
    preferred_x: str | None,
    preferred_y: str | None,
    preferred_series: str | None,
) -> ChartSpec | None:
    x_key = _valid_column(preferred_x, columns) or _select_time_key(columns)
    if not x_key:
        return None

    y_key = _first_primary_numeric_column(rows, columns, x_key, preferred_y=preferred_y)
    if not y_key:
        return None

    series_key = _valid_column(preferred_series, columns) or _select_series_key(
        columns,
        x_key=x_key,
        y_key=y_key,
    )
    if not series_key:
        data = []
        for row in rows:
            value = _to_float(row.get(y_key))
            label = _clean_label(row.get(x_key))
            if value is not None and label:
                data.append({x_key: label, y_key: value})

        data = _sort_line_data(data, x_key)
        if len(data) < 2:
            return None

        return ChartSpec(
            recommended=True,
            type="line",
            title=f"Trend: {y_key}",
            x=x_key,
            y=y_key,
            xKey=x_key,
            yKeys=[y_key],
            data=data,
        )

    x_labels = _ordered_labels([_clean_label(row.get(x_key)) for row in rows])
    series_labels = _ordered_labels([_clean_label(row.get(series_key)) for row in rows])[
        :MAX_LINE_SERIES
    ]
    points_by_x: dict[str, dict[str, Any]] = {label: {x_key: label} for label in x_labels}
    allowed_series = set(series_labels)

    for row in rows:
        x_label = _clean_label(row.get(x_key))
        series_label = _clean_label(row.get(series_key))
        value = _to_float(row.get(y_key))
        if (
            not x_label
            or not series_label
            or value is None
            or x_label not in points_by_x
            or series_label not in allowed_series
        ):
            continue
        points_by_x[x_label][series_label] = value

    data = [
        point
        for point in points_by_x.values()
        if any(isinstance(point.get(label), int | float) for label in series_labels)
    ]
    if len(data) < 2 or not series_labels:
        return None

    return ChartSpec(
        recommended=True,
        type="line",
        title=f"Trend: {y_key} by {series_key}",
        x=x_key,
        y=y_key,
        series=series_key,
        xKey=x_key,
        yKeys=series_labels,
        data=data,
    )


def _scatter_chart_from_rows(
    rows: list[dict[str, Any]],
    columns: list[str],
    *,
    preferred_x: str | None,
    preferred_y: str | None,
) -> ChartSpec | None:
    numeric_keys = _numeric_columns(rows, columns)
    numeric_keys = [key for key in numeric_keys if not _is_minmax_like_key(key)]
    if len(numeric_keys) < 2:
        return None

    preferred_x = _valid_column(preferred_x, numeric_keys)
    preferred_y = _valid_column(preferred_y, numeric_keys)
    x_key = preferred_x or next((key for key in numeric_keys if _is_count_like_key(key)), numeric_keys[0])
    y_key = preferred_y if preferred_y and preferred_y != x_key else None
    if y_key is None:
        y_key = (
            _first_primary_numeric_column(rows, numeric_keys, x_key)
            or next((key for key in numeric_keys if key != x_key), None)
        )
    if not y_key:
        return None

    label_key = next((column for column in columns if column not in numeric_keys), None)
    data = []
    for row in rows:
        x_value = _to_float(row.get(x_key))
        y_value = _to_float(row.get(y_key))
        if x_value is None or y_value is None:
            continue
        point: dict[str, Any] = {x_key: x_value, y_key: y_value}
        if label_key:
            point[label_key] = _clean_label(row.get(label_key))
        data.append(point)

    if len(data) < 2:
        return None

    return ChartSpec(
        recommended=True,
        type="scatter",
        title=f"Scatter chart: {y_key} by {x_key}",
        x=x_key,
        y=y_key,
        xKey=x_key,
        yKeys=[y_key],
        data=data,
    )


def _columns_from_rows(rows: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for row in rows:
        for key in row:
            if key not in seen:
                seen.append(key)
    return seen


def _valid_column(value: str | None, columns: list[str]) -> str | None:
    return value if value in columns else None


def _select_time_key(columns: list[str]) -> str | None:
    for column in columns:
        if re.search(r"week_label|semana|week|fecha|date", column, re.IGNORECASE):
            return column
    return None


def _select_category_key(columns: list[str], rows: list[dict[str, Any]]) -> str | None:
    numeric = set(_numeric_columns(rows, columns))
    non_numeric = [column for column in columns if column not in numeric]
    exact_priorities = [
        "zone",
        "zona",
        "city",
        "ciudad",
        "country",
        "pais",
        "metric",
        "metrica",
        "zone_type",
        "segment",
        "type",
        "label",
    ]

    normalized = {_normalize_key(column): column for column in non_numeric}
    for key in exact_priorities:
        if key in normalized:
            return normalized[key]

    for pattern in [r"\bzone\b", r"zona", r"city|ciudad", r"country|pais", r"metric|metrica"]:
        for column in non_numeric:
            if re.search(pattern, _normalize_key(column), re.IGNORECASE) and not column.endswith("_id"):
                return column

    return non_numeric[0] if non_numeric else None


def _select_series_key(columns: list[str], *, x_key: str, y_key: str) -> str | None:
    candidates = [column for column in columns if column not in {x_key, y_key}]
    exact_priorities = ["zone", "zona", "zone_type", "city", "ciudad", "country", "pais", "segment", "metric", "metrica"]
    normalized = {_normalize_key(column): column for column in candidates}
    for key in exact_priorities:
        if key in normalized:
            return normalized[key]

    for pattern in [r"\bzone\b", r"zona", r"zone_type", r"city|ciudad", r"country|pais", r"segment", r"metric|metrica"]:
        for column in candidates:
            normalized_column = _normalize_key(column)
            if re.search(pattern, normalized_column, re.IGNORECASE) and "offset" not in normalized_column:
                return column
    return None


def _primary_numeric_columns(
    rows: list[dict[str, Any]],
    columns: list[str],
    x_key: str,
    *,
    preferred_y: str | None = None,
) -> list[str]:
    numeric = [
        column
        for column in _numeric_columns(rows, columns)
        if column != x_key
        and not _is_count_like_key(column)
        and not _is_minmax_like_key(column)
        and not re.search(r"variacion|orders total|total ordenes", _normalize_key(column), re.IGNORECASE)
    ]
    numeric = sorted(numeric, key=_metric_column_priority)
    if preferred_y in numeric:
        numeric = [preferred_y] + [column for column in numeric if column != preferred_y]
    return numeric


def _first_primary_numeric_column(
    rows: list[dict[str, Any]],
    columns: list[str],
    x_key: str,
    *,
    preferred_y: str | None = None,
) -> str | None:
    primary = _primary_numeric_columns(rows, columns, x_key, preferred_y=preferred_y)
    if primary:
        return primary[0]
    fallback = [column for column in _numeric_columns(rows, columns) if column != x_key]
    if preferred_y in fallback:
        return preferred_y
    return sorted(fallback, key=_metric_column_priority)[0] if fallback else None


def _metric_column_priority(key: str) -> int:
    normalized = _normalize_key(key)
    if normalized.startswith(("avg_", "average_", "promedio_", "mean_")) or normalized == "value":
        return 0
    if re.search(r"penetration|perfect|gross_profit|profit|order|rate|pct|percent", normalized):
        return 1
    return 2


def _numeric_columns(rows: list[dict[str, Any]], columns: list[str]) -> list[str]:
    numeric = []
    for column in columns:
        if any(_to_float(row.get(column)) is not None for row in rows):
            numeric.append(column)
    return numeric


def _has_bar_shape(rows: list[dict[str, Any]], columns: list[str]) -> bool:
    x_key = _select_category_key(columns, rows)
    return bool(x_key and _primary_numeric_columns(rows, columns, x_key))


def _has_scatter_shape(rows: list[dict[str, Any]], columns: list[str]) -> bool:
    numeric = _numeric_columns(rows, columns)
    primary = [
        column
        for column in numeric
        if not _is_count_like_key(column) and not _is_minmax_like_key(column)
    ]
    count_like = [column for column in numeric if _is_count_like_key(column)]
    return len(primary) >= 2 or (len(rows) > 2 and bool(primary) and bool(count_like))


def _is_small_segment_comparison(rows: list[dict[str, Any]], columns: list[str]) -> bool:
    if len(rows) > 6:
        return False
    return any(
        re.search(r"zone_type|segment|tipo|wealthy", _normalize_key(column), re.IGNORECASE)
        for column in columns
    )


def _ordered_labels(values: list[str]) -> list[str]:
    labels = [value for value in values if value]
    unique = list(dict.fromkeys(labels))
    if unique and all(re.match(r"^L\d+W$", label, re.IGNORECASE) for label in unique):
        return sorted(unique, key=lambda label: int(label[1:-1]), reverse=True)
    return unique


def _sort_line_data(data: list[dict[str, Any]], x_key: str) -> list[dict[str, Any]]:
    labels = _ordered_labels([str(row.get(x_key) or "") for row in data])
    order = {label: index for index, label in enumerate(labels)}
    return sorted(
        data,
        key=lambda row: order.get(str(row.get(x_key) or ""), len(order)),
    )


def _is_count_like_key(key: str) -> bool:
    normalized = _normalize_key(key)
    return (
        normalized in {"n", "count", "zones", "zonas", "n_zones", "n_zonas"}
        or normalized.startswith(("n_", "num_"))
        or normalized.endswith("_count")
        or "count" in normalized
    )


def _is_minmax_like_key(key: str) -> bool:
    normalized = _normalize_key(key)
    return normalized.startswith(("min", "max")) or normalized.endswith(("_min", "_max"))


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
        return number if math.isfinite(number) else None
    if value is None:
        return None
    text = str(value).strip().replace("%", "").replace(",", "")
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _clean_label(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _normalize_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_text.strip().lower().replace(" ", "_")
