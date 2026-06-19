from __future__ import annotations

import math
import os
import json
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ops_copilot.insights import AuthoredReportFinding, InsightFinding, InsightReport


class LatexBuildError(RuntimeError):
    """Raised when a LaTeX report cannot be compiled into PDF."""


class LatexCompileResult:
    def __init__(self, pdf_path: Path, tex_source: str, repair_notes: list[str]) -> None:
        self.pdf_path = pdf_path
        self.tex_source = tex_source
        self.repair_notes = repair_notes


def render_report_latex(report: InsightReport) -> str:
    """Render an executive insight report as standalone LaTeX source."""

    categories = {category.key: category.findings for category in report.categories}
    if report.authored_report:
        findings_by_id = _findings_by_id(report)
        title = report.authored_report.title
        subtitle = report.authored_report.subtitle or report.period_label
        opening_note = report.authored_report.opening_note
        summary = "\n".join(
            _authored_summary_item(item, findings_by_id)
            for item in report.authored_report.executive_summary[:5]
        )
        category_sections = "\n".join(
            _authored_category_section(section, findings_by_id)
            for section in report.authored_report.sections
        )
        closing_note = report.authored_report.closing_note
    else:
        title = "Rappi Ops Executive Insight Report"
        subtitle = report.period_label
        opening_note = ""
        summary = "\n".join(_summary_item(finding) for finding in report.executive_summary[:5])
        category_sections = "\n".join(
            _category_section(category.title, category.findings)
            for category in report.categories
        )
        closing_note = ""
    caveats = "\n".join(f"\\item {_latex_escape(caveat)}" for caveat in report.data_caveats)
    charts = "\n".join(
        chart
        for chart in [
            _anomaly_chart(categories.get("anomalies", [])),
            _trend_chart(categories.get("worrying_trends", [])),
            _benchmark_chart(categories.get("benchmarking", [])),
            _correlation_chart(categories.get("correlations", [])),
            _opportunity_chart(categories.get("opportunities", [])),
        ]
        if chart
    )

    if not summary:
        summary = "\\item No critical findings were detected with the current thresholds."
    if not caveats:
        caveats = "\\item No caveats were provided."
    opening_block = (
        "\\section*{Executive Takeaway}\n"
        f"{_latex_escape(opening_note)}\n"
        if opening_note
        else ""
    )
    closing_block = (
        "\\section*{Closing Note}\n"
        f"{_latex_escape(closing_note)}\n"
        if closing_note
        else ""
    )

    return rf"""\documentclass[10pt]{{article}}
\usepackage[utf8]{{inputenc}}
\usepackage[T1]{{fontenc}}
\usepackage{{lmodern}}
\usepackage[margin=0.55in]{{geometry}}
\usepackage{{xcolor}}
\usepackage{{booktabs}}
\usepackage{{tabularx}}
\usepackage{{enumitem}}
\usepackage{{float}}
\usepackage{{fancyhdr}}
\usepackage{{hyperref}}
\usepackage{{tikz}}
\usepackage{{pgfplots}}
\pgfplotsset{{compat=1.18}}

\definecolor{{rappiOrange}}{{HTML}}{{FF5A1F}}
\definecolor{{rappiInk}}{{HTML}}{{16181D}}
\definecolor{{rappiMuted}}{{HTML}}{{626A75}}
\definecolor{{rappiLine}}{{HTML}}{{D9DEE6}}
\definecolor{{rappiSoft}}{{HTML}}{{F4F6F8}}
\definecolor{{rappiRed}}{{HTML}}{{D84B3E}}
\definecolor{{rappiGreen}}{{HTML}}{{1E8A57}}
\definecolor{{rappiBlue}}{{HTML}}{{207EA8}}
\definecolor{{rappiPurple}}{{HTML}}{{7A68D8}}

\hypersetup{{colorlinks=true, linkcolor=rappiOrange, urlcolor=rappiOrange}}
\pagestyle{{fancy}}
\fancyhf{{}}
\lhead{{Rappi Ops Copilot}}
\rhead{{Automatic Insights}}
\cfoot{{\thepage}}
\renewcommand{{\headrulewidth}}{{0.3pt}}
\setlength{{\parindent}}{{0pt}}
\setlength{{\parskip}}{{5pt}}
\setlist[itemize]{{leftmargin=*, topsep=2pt, itemsep=2pt}}
\setlist[enumerate]{{leftmargin=*, topsep=2pt, itemsep=4pt}}

\newcommand{{\severity}}[1]{{\textcolor{{rappiOrange}}{{\textbf{{#1}}}}}}
\newcommand{{\findingtitle}}[1]{{\textbf{{#1}}}}

\begin{{document}}

\begin{{center}}
{{\Huge \textbf{{{_latex_escape(title)}}}}}\\[4pt]
{{\large {_latex_escape(subtitle)}}}\\[2pt]
{{\small Generated at {_latex_escape(report.generated_at)} from {_latex_escape(report.source)}}}
\end{{center}}

\vspace{{4pt}}
\hrule
\vspace{{8pt}}

{opening_block}

\section*{{Executive Summary}}
\begin{{enumerate}}
{summary}
\end{{enumerate}}

\section*{{Insight Charts}}
{charts}

\section*{{Detail by Category}}
{category_sections}

{closing_block}

\section*{{Data Caveats}}
\begin{{itemize}}
{caveats}
\end{{itemize}}

\end{{document}}
"""


def render_query_result_latex(result: Any) -> str:
    """Render a cached query result as a standalone LaTeX export report."""

    rows = list(getattr(result, "rows", []) or [])
    all_columns = _query_result_columns(result, rows)
    columns = all_columns[:8]
    omitted_columns = max(0, len(all_columns) - len(columns))
    visible_rows = rows[:60]
    row_count = int(getattr(result, "row_count", len(rows)) or len(rows))
    table_note = _query_table_note(
        row_count=row_count,
        returned_rows=len(rows),
        visible_rows=len(visible_rows),
        truncated=bool(getattr(result, "truncated", False)),
        omitted_columns=omitted_columns,
    )
    table = _query_result_table(visible_rows, columns)
    chart = _query_result_chart(result, rows, all_columns)
    chart_block = f"\\section*{{Chart}}\n{chart}\n\n" if chart else ""
    caveats = _latex_items(getattr(result, "caveats", []) or [], "No caveats were provided.")
    followups = _latex_items(
        getattr(result, "suggested_followups", []) or [],
        "No follow-up suggestions were provided.",
    )
    metadata = _query_metadata(result, row_count, rows, all_columns)
    question = str(getattr(result, "question", "") or "").strip()
    sql = str(getattr(result, "sql", "") or "").strip()
    question_block = (
        "\\section*{User Request}\n"
        f"{_latex_escape(question)}\n\n"
        if question
        else ""
    )
    sql_block = (
        "\\section*{Read-Only SQL}\n"
        f"{{\\small\\ttfamily\\raggedright {_latex_escape(_truncate_context(sql, 1800))}\\par}}\n\n"
        if sql
        else ""
    )

    return rf"""\documentclass[10pt]{{article}}
\usepackage[utf8]{{inputenc}}
\usepackage[T1]{{fontenc}}
\usepackage{{lmodern}}
\usepackage[margin=0.6in]{{geometry}}
\usepackage{{xcolor}}
\usepackage{{booktabs}}
\usepackage{{longtable}}
\usepackage{{tabularx}}
\usepackage{{array}}
\usepackage{{enumitem}}
\usepackage{{float}}
\usepackage{{fancyhdr}}
\usepackage{{hyperref}}
\usepackage{{tikz}}
\usepackage{{pgfplots}}
\pgfplotsset{{compat=1.18}}

\definecolor{{rappiOrange}}{{HTML}}{{FF5A1F}}
\definecolor{{rappiInk}}{{HTML}}{{16181D}}
\definecolor{{rappiMuted}}{{HTML}}{{626A75}}
\definecolor{{rappiLine}}{{HTML}}{{D9DEE6}}
\definecolor{{rappiSoft}}{{HTML}}{{F4F6F8}}
\definecolor{{rappiRed}}{{HTML}}{{D84B3E}}
\definecolor{{rappiGreen}}{{HTML}}{{1E8A57}}
\definecolor{{rappiBlue}}{{HTML}}{{207EA8}}
\definecolor{{rappiPurple}}{{HTML}}{{7A68D8}}

\hypersetup{{colorlinks=true, linkcolor=rappiOrange, urlcolor=rappiOrange}}
\pagestyle{{fancy}}
\fancyhf{{}}
\lhead{{Rappi Ops Copilot}}
\rhead{{Query Export Report}}
\cfoot{{\thepage}}
\renewcommand{{\headrulewidth}}{{0.3pt}}
\setlength{{\parindent}}{{0pt}}
\setlength{{\parskip}}{{5pt}}
\setlist[itemize]{{leftmargin=*, topsep=2pt, itemsep=2pt}}

\begin{{document}}

\begin{{center}}
{{\Huge \textbf{{Rappi Ops Query Export}}}}\\[4pt]
{{\large CSV companion and PDF report}}\\[2pt]
{{\small Generated from cached API result {_latex_escape(getattr(result, "query_id", ""))}}}
\end{{center}}

\vspace{{4pt}}
\hrule
\vspace{{8pt}}

\section*{{Result Metadata}}
{metadata}

{question_block}
{sql_block}
{chart_block}
\section*{{Result Preview}}
{table_note}
{table}

\section*{{Caveats}}
\begin{{itemize}}
{caveats}
\end{{itemize}}

\section*{{Suggested Follow-Ups}}
\begin{{itemize}}
{followups}
\end{{itemize}}

\end{{document}}
"""


def query_result_latex_context(result: Any) -> str:
    rows = list(getattr(result, "rows", []) or [])
    payload = {
        "query_id": getattr(result, "query_id", ""),
        "question": getattr(result, "question", ""),
        "answer_type": getattr(result, "answer_type", "model_sql"),
        "period_label": getattr(result, "period_label", ""),
        "sql": getattr(result, "sql", ""),
        "columns": _query_result_columns(result, rows),
        "row_count": getattr(result, "row_count", len(rows)),
        "truncated": getattr(result, "truncated", False),
        "chart": _chart_payload(getattr(result, "chart", None)),
        "caveats": getattr(result, "caveats", []),
        "sample_rows": rows[:10],
    }
    return json.dumps(payload, ensure_ascii=True, indent=2, default=str)


def compile_latex_pdf(tex_source: str, output_pdf: Path) -> Path:
    """Compile LaTeX source into a PDF using a local TeX engine."""

    compiler = _latex_compiler()
    if compiler is None:
        raise LatexBuildError(
            "No LaTeX compiler found. Install tectonic, pdflatex, xelatex, or latexmk."
        )

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    build_dir = output_pdf.parent / ".latex-build"
    build_dir.mkdir(parents=True, exist_ok=True)
    tex_path = build_dir / f"{output_pdf.stem}.tex"
    tex_path.write_text(tex_source, encoding="utf-8")

    command = _compile_command(compiler, tex_path, build_dir)
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise LatexBuildError("LaTeX compilation timed out after 120 seconds.") from exc

    if completed.returncode != 0:
        detail = "\n".join(
            part.strip()
            for part in [completed.stdout[-2500:], completed.stderr[-2500:]]
            if part.strip()
        )
        raise LatexBuildError(f"LaTeX compilation failed.\n{detail}")

    built_pdf = build_dir / f"{output_pdf.stem}.pdf"
    if not built_pdf.exists():
        raise LatexBuildError(f"LaTeX compiler did not produce {built_pdf}.")

    shutil.copyfile(built_pdf, output_pdf)
    return output_pdf


def compile_latex_pdf_with_repair(
    tex_source: str,
    output_pdf: Path,
    *,
    context: str = "",
    max_repairs: int | None = None,
) -> LatexCompileResult:
    """Compile LaTeX, using DeepSeek to repair compiler errors during the run."""

    if max_repairs is None:
        max_repairs = _repair_attempts()

    current_source = tex_source
    repair_notes: list[str] = []
    last_error = ""

    for attempt in range(max_repairs + 1):
        try:
            pdf_path = compile_latex_pdf(current_source, output_pdf)
            return LatexCompileResult(pdf_path, current_source, repair_notes)
        except LatexBuildError as exc:
            last_error = str(exc)
            if "No LaTeX compiler found" in last_error:
                break
            if attempt >= max_repairs:
                break

            repaired_source = repair_latex_with_deepseek(
                current_source,
                compiler_error=last_error,
                context=context,
                attempt=attempt + 1,
            )
            if repaired_source.strip() == current_source.strip():
                raise LatexBuildError(
                    "LaTeX compilation failed and the LLM returned an unchanged document.\n"
                    f"{last_error}"
                ) from exc

            repair_notes.append(f"repair_attempt_{attempt + 1}: {last_error[:800]}")
            current_source = repaired_source

    raise LatexBuildError(
        f"LaTeX compilation failed after {max_repairs + 1} compile attempt(s).\n{last_error}"
    )


def repair_latex_with_deepseek(
    tex_source: str,
    *,
    compiler_error: str,
    context: str,
    attempt: int,
) -> str:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise LatexBuildError(
            "LaTeX compilation failed and DEEPSEEK_API_KEY is not configured for "
            "automatic LaTeX repair."
        )

    prompt = _latex_repair_prompt(tex_source, compiler_error, context, attempt)
    payload = {
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
        "messages": [
            {
                "role": "system",
                "content": (
                    "You repair LaTeX documents generated by an automatic analytics report. "
                    "Return only the full corrected LaTeX source. Do not use markdown. "
                    "Do not change business findings, numbers, recommendations, or chart data "
                    "unless the compiler error requires escaping or syntax correction."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1200]
        raise LatexBuildError(f"DeepSeek LaTeX repair request failed: {detail}") from exc
    except Exception as exc:
        raise LatexBuildError(f"DeepSeek LaTeX repair request failed: {exc}") from exc

    try:
        content = response_payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LatexBuildError("DeepSeek LaTeX repair returned an unexpected response.") from exc

    repaired = _extract_latex_source(str(content))
    if "\\documentclass" not in repaired or "\\end{document}" not in repaired:
        raise LatexBuildError("DeepSeek LaTeX repair did not return a complete document.")
    return repaired


def latex_repair_context(report: InsightReport) -> str:
    payload = {
        "period_label": report.period_label,
        "data_caveats": report.data_caveats,
        "authored_report": (
            report.authored_report.model_dump(mode="json")
            if report.authored_report
            else None
        ),
        "executive_summary": [
            {
                "id": finding.id,
                "category": finding.category,
                "severity": finding.severity,
                "title": finding.title,
                "summary": finding.summary,
                "recommendation": finding.recommendation,
                "evidence": finding.evidence,
            }
            for finding in report.executive_summary[:5]
        ],
        "categories": [
            {
                "key": category.key,
                "title": category.title,
                "finding_count": len(category.findings),
            }
            for category in report.categories
        ],
    }
    return json.dumps(payload, ensure_ascii=True, indent=2)


def _latex_compiler() -> str | None:
    for candidate in ["tectonic", "latexmk", "xelatex", "pdflatex"]:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def _compile_command(compiler: str, tex_path: Path, build_dir: Path) -> list[str]:
    name = Path(compiler).name
    if name == "tectonic":
        return [
            compiler,
            "--outdir",
            str(build_dir),
            "--keep-logs",
            str(tex_path),
        ]
    if name == "latexmk":
        return [
            compiler,
            "-pdf",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-output-directory",
            str(build_dir),
            str(tex_path),
        ]
    return [
        compiler,
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-output-directory",
        str(build_dir),
        str(tex_path),
    ]


def _repair_attempts() -> int:
    raw_value = os.getenv("LATEX_REPAIR_ATTEMPTS", "2")
    try:
        value = int(raw_value)
    except ValueError:
        return 2
    return max(0, min(value, 5))


def _latex_repair_prompt(
    tex_source: str,
    compiler_error: str,
    context: str,
    attempt: int,
) -> str:
    return (
        f"Repair attempt: {attempt}\n\n"
        "Business/report context. Treat this as read-only evidence; do not alter claims:\n"
        f"{_truncate_context(context, 6000)}\n\n"
        "Compiler error/log tail:\n"
        f"{_truncate_context(compiler_error, 6000)}\n\n"
        "Full LaTeX source to repair:\n"
        f"{tex_source}\n\n"
        "Return only the full corrected LaTeX document, starting with \\documentclass."
    )


def _extract_latex_source(content: str) -> str:
    stripped = content.strip()
    if "```" not in stripped:
        return stripped

    parts = stripped.split("```")
    for part in parts:
        candidate = part.strip()
        if candidate.startswith("latex"):
            candidate = candidate[len("latex") :].strip()
        if "\\documentclass" in candidate and "\\end{document}" in candidate:
            return candidate
    return stripped


def _truncate_context(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[:max_length] + "\n[truncated]"


def _query_metadata(result: Any, row_count: int, rows: list[Any], columns: list[str]) -> str:
    answer_type = str(getattr(result, "answer_type", "model_sql") or "model_sql")
    period_label = str(getattr(result, "period_label", "Model-generated SQL result") or "")
    chart_hint = _resolved_query_chart_hint(result, rows, columns)
    filters = getattr(result, "filters_applied", None)
    if isinstance(filters, dict) and filters:
        filter_text = "; ".join(
            f"{key}: {', '.join(str(item) for item in values)}"
            for key, values in filters.items()
        )
    else:
        filter_text = "None"

    items = [
        ("Query ID", getattr(result, "query_id", "")),
        ("Answer type", answer_type),
        ("Period", period_label),
        ("Rows in export", row_count),
        ("Filters", filter_text),
    ]
    if chart_hint:
        items.append(("Recommended visualization", chart_hint))

    body = "\n".join(
        f"\\textbf{{{_latex_escape(label)}}} & {_latex_escape(value)} \\\\"
        for label, value in items
    )
    return rf"""\begin{{tabularx}}{{\linewidth}}{{@{{}}lX@{{}}}}
{body}
\end{{tabularx}}
"""


def _query_result_columns(result: Any, rows: list[Any]) -> list[str]:
    raw_columns = getattr(result, "columns", None)
    columns = [str(column) for column in raw_columns or [] if str(column)]
    if columns:
        return columns

    seen: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in row:
            text = str(key)
            if text not in seen:
                seen.append(text)
    return seen


def _query_table_note(
    *,
    row_count: int,
    returned_rows: int,
    visible_rows: int,
    truncated: bool,
    omitted_columns: int,
) -> str:
    notes = [
        f"The CSV companion contains the full cached result returned by the API ({row_count} rows)."
    ]
    if visible_rows < returned_rows:
        notes.append(f"This PDF preview shows the first {visible_rows} rows.")
    if truncated:
        notes.append("The original SQL response was limited by the API row cap.")
    if omitted_columns:
        notes.append(f"{omitted_columns} additional column(s) are available in the CSV.")
    return " ".join(_latex_escape(note) for note in notes)


def _query_result_table(rows: list[Any], columns: list[str]) -> str:
    if not rows or not columns:
        return "No rows returned."

    width = _query_column_width(len(columns))
    column_spec = "".join(
        f">{{\\raggedright\\arraybackslash}}p{{{width:.3f}\\linewidth}}"
        for _ in columns
    )
    header = " & ".join(_latex_escape(_truncate(column, 26)) for column in columns) + r" \\"
    body = "\n".join(
        " & ".join(_latex_escape(_format_query_value(_row_value(row, column))) for column in columns)
        + r" \\"
        for row in rows
    )

    return rf"""\scriptsize
\setlength{{\tabcolsep}}{{3pt}}
\renewcommand{{\arraystretch}}{{1.16}}
\begin{{longtable}}{{@{{}}{column_spec}@{{}}}}
\toprule
{header}
\midrule
\endfirsthead
\toprule
{header}
\midrule
\endhead
{body}
\bottomrule
\end{{longtable}}
\normalsize
"""


def _query_result_chart(result: Any, rows: list[Any], columns: list[str]) -> str:
    chart_payload = _chart_payload(getattr(result, "chart", None))
    chart_from_payload = _query_chart_from_payload(chart_payload)
    if chart_from_payload:
        return chart_from_payload

    if not rows or not columns:
        return ""

    hint = _resolved_query_chart_hint(result, rows, columns)
    preferred_x = _valid_chart_column(
        chart_payload.get("x") or chart_payload.get("xKey") or chart_payload.get("category"),
        columns,
    )
    preferred_y = _valid_chart_column(
        chart_payload.get("y") or chart_payload.get("yKey") or chart_payload.get("metric"),
        columns,
    )
    preferred_series = _valid_chart_column(chart_payload.get("series"), columns)
    if hint == "none":
        return ""
    if hint == "table":
        hint = _auto_query_chart_hint(rows, columns)
    if hint == "table":
        return ""
    if hint in {"line", "area"}:
        return _query_line_chart(
            rows,
            columns,
            preferred_x=preferred_x,
            preferred_y=preferred_y,
            preferred_series=preferred_series,
        )
    if hint in {"scatter", "bubble"}:
        return _query_scatter_chart(rows, columns, preferred_x=preferred_x, preferred_y=preferred_y)
    if hint in {"pie", "donut"}:
        return _query_pie_chart_from_rows(
            rows,
            columns,
            preferred_x=preferred_x,
            preferred_y=preferred_y,
            donut=hint == "donut",
        )
    return _query_bar_chart(rows, columns, preferred_x=preferred_x, preferred_y=preferred_y)


def _query_chart_from_payload(chart: Any) -> str:
    payload = _chart_payload(chart)
    if not payload:
        return ""

    chart_type = _normalize_query_chart_hint(
        str(
            payload.get("type")
            or payload.get("kind")
            or payload.get("chartType")
            or payload.get("visualization")
            or ""
        )
    )
    if chart_type in {"none", "table"}:
        return ""

    shape = _payload_chart_shape(payload, chart_type)
    title = _payload_string(payload.get("title"))
    if not shape:
        return ""

    data = shape["data"]
    x_key = shape["x_key"]
    y_keys = shape["y_keys"]
    z_key = shape.get("z_key")
    stacked = _payload_chart_mode(payload) == "stacked"

    if chart_type in {"pie", "donut"}:
        return _query_pie_chart_from_payload(
            data,
            x_key=x_key,
            y_key=y_keys[0],
            title=title,
            donut=chart_type == "donut",
        )
    if chart_type == "area":
        return _query_area_chart_from_payload(
            data,
            x_key=x_key,
            y_keys=y_keys,
            title=title,
            stacked=stacked,
        )
    if chart_type == "combo":
        return _query_combo_chart_from_payload(
            data,
            x_key=x_key,
            y_keys=y_keys,
            title=title,
        )
    if chart_type == "line":
        return _query_line_chart_from_payload(
            data,
            x_key=x_key,
            y_keys=y_keys,
            title=title,
        )
    if chart_type in {"scatter", "bubble"}:
        return _query_scatter_chart_from_payload(
            data,
            x_key=x_key,
            y_key=y_keys[0],
            title=title,
            z_key=z_key if chart_type == "bubble" else None,
        )
    return _query_bar_chart_from_payload(
        data,
        x_key=x_key,
        y_keys=y_keys,
        title=title,
        stacked=stacked,
    )


def _chart_payload(chart: Any) -> dict[str, Any]:
    if chart is None:
        return {}
    if isinstance(chart, dict):
        return chart
    if hasattr(chart, "model_dump"):
        dumped = chart.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {}
    payload: dict[str, Any] = {}
    for key in [
        "type",
        "kind",
        "chartType",
        "visualization",
        "title",
        "name",
        "label",
        "x",
        "y",
        "series",
        "xKey",
        "yKey",
        "yKeys",
        "zKey",
        "sizeKey",
        "radiusKey",
        "category",
        "nameKey",
        "labelKey",
        "valueKey",
        "data",
        "labels",
        "categories",
        "values",
        "datasets",
        "points",
        "mode",
        "variant",
        "layout",
        "stacked",
        "chartjs",
    ]:
        if hasattr(chart, key):
            payload[key] = getattr(chart, key)
    return payload


def _payload_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _payload_y_keys(payload: dict[str, Any]) -> list[str]:
    raw_y_keys = payload.get("yKeys")
    if isinstance(raw_y_keys, list):
        y_keys = [item.strip() for item in raw_y_keys if isinstance(item, str) and item.strip()]
        if y_keys:
            return y_keys
    for key in ["yKey", "y", "metric", "valueKey"]:
        y_key = _payload_string(payload.get(key))
        if y_key:
            return [y_key]
    return []


def _payload_chart_shape(payload: dict[str, Any], chart_type: str) -> dict[str, Any] | None:
    for extractor in [
        _payload_label_dataset_shape,
        _payload_label_value_shape,
        _payload_xy_shape,
    ]:
        shape = extractor(payload)
        if shape:
            return shape

    if chart_type == "histogram":
        histogram = _payload_histogram_shape(payload)
        if histogram:
            return histogram

    rows = _payload_direct_rows(payload)
    if not rows:
        return None

    x_key = (
        _payload_string(payload.get("xKey"))
        or _payload_string(payload.get("x"))
        or _payload_string(payload.get("category"))
        or _payload_string(payload.get("nameKey"))
        or _payload_string(payload.get("labelKey"))
        or _infer_payload_x_key(rows, chart_type)
    )
    if not x_key:
        return None

    z_key = (
        _payload_string(payload.get("zKey"))
        or _payload_string(payload.get("sizeKey"))
        or _payload_string(payload.get("radiusKey"))
    )
    y_keys = _payload_y_keys(payload)
    if not y_keys:
        y_keys = _infer_payload_y_keys(rows, x_key=x_key, z_key=z_key, chart_type=chart_type)
    if not z_key and chart_type == "bubble" and y_keys:
        z_key = _infer_payload_z_key(rows, x_key=x_key, y_key=y_keys[0])

    return {"data": rows, "x_key": x_key, "y_keys": y_keys, "z_key": z_key} if y_keys else None


def _payload_direct_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, list):
        rows = [row for row in data if isinstance(row, dict)]
        if rows:
            return rows
    points = payload.get("points")
    if isinstance(points, list):
        return [row for row in points if isinstance(row, dict)]
    return []


def _payload_object_sources(payload: dict[str, Any]) -> list[dict[str, Any]]:
    sources = [payload]
    data = payload.get("data")
    if isinstance(data, dict):
        sources.append(data)
    chartjs = payload.get("chartjs")
    if isinstance(chartjs, dict) and isinstance(chartjs.get("data"), dict):
        sources.append(chartjs["data"])
    return sources


def _payload_label_dataset_shape(payload: dict[str, Any]) -> dict[str, Any] | None:
    for source in _payload_object_sources(payload):
        labels = _payload_list(source.get("labels")) or _payload_list(source.get("categories"))
        datasets = _payload_list(source.get("datasets")) or _payload_list(source.get("series"))
        dataset_rows = [dataset for dataset in datasets or [] if isinstance(dataset, dict)]
        if not labels or not dataset_rows:
            continue

        x_key = (
            _payload_string(payload.get("xKey"))
            or _payload_string(payload.get("x"))
            or _payload_string(payload.get("category"))
            or _payload_string(payload.get("nameKey"))
            or _payload_string(payload.get("labelKey"))
            or "label"
        )
        rows: list[dict[str, Any]] = [{x_key: label} for label in labels]
        y_keys: list[str] = []
        for index, dataset in enumerate(dataset_rows):
            y_key = (
                _payload_string(dataset.get("label"))
                or _payload_string(dataset.get("name"))
                or _payload_string(dataset.get("key"))
                or _payload_string(dataset.get("metric"))
                or _payload_string(dataset.get("yKey"))
                or f"value_{index + 1}"
            )
            values = _payload_list(dataset.get("data")) or _payload_list(dataset.get("values"))
            if not values:
                continue
            y_keys.append(y_key)
            for value_index, value in enumerate(values[: len(rows)]):
                rows[value_index][y_key] = _payload_point_value(value, y_key)
        if y_keys:
            return {"data": rows, "x_key": x_key, "y_keys": y_keys}
    return None


def _payload_label_value_shape(payload: dict[str, Any]) -> dict[str, Any] | None:
    for source in _payload_object_sources(payload):
        labels = _payload_list(source.get("labels")) or _payload_list(source.get("categories"))
        values = _payload_list(source.get("values")) or _payload_list(source.get("y"))
        if not labels or not values:
            continue

        x_key = (
            _payload_string(payload.get("xKey"))
            or _payload_string(payload.get("x"))
            or _payload_string(payload.get("category"))
            or _payload_string(payload.get("nameKey"))
            or _payload_string(payload.get("labelKey"))
            or "label"
        )
        y_key = _payload_string(payload.get("yKey")) or _payload_string(payload.get("metric")) or _payload_string(payload.get("valueKey")) or "value"
        rows = [
            {x_key: label, y_key: _payload_point_value(values[index], y_key)}
            for index, label in enumerate(labels[: len(values)])
        ]
        return {"data": rows, "x_key": x_key, "y_keys": [y_key]}
    return None


def _payload_xy_shape(payload: dict[str, Any]) -> dict[str, Any] | None:
    x_values = _payload_list(payload.get("x"))
    y_values = _payload_list(payload.get("y"))
    if not x_values or not y_values:
        return None
    x_key = (
        _payload_string(payload.get("xKey"))
        or _payload_string(payload.get("category"))
        or _payload_string(payload.get("nameKey"))
        or _payload_string(payload.get("labelKey"))
        or "x"
    )
    y_key = _payload_string(payload.get("yKey")) or _payload_string(payload.get("metric")) or _payload_string(payload.get("valueKey")) or "y"
    rows = [
        {x_key: x_value, y_key: _payload_point_value(y_values[index], y_key)}
        for index, x_value in enumerate(x_values[: len(y_values)])
    ]
    return {"data": rows, "x_key": x_key, "y_keys": [y_key]}


def _payload_histogram_shape(payload: dict[str, Any]) -> dict[str, Any] | None:
    raw_values = _payload_list(payload.get("values")) or _payload_list(payload.get("data"))
    values = [_to_float(value) for value in raw_values or []]
    values = [value for value in values if value is not None]
    if len(values) < 2:
        return None
    minimum = min(values)
    maximum = max(values)
    if minimum == maximum:
        return {"data": [{"bin": _format_number(minimum, 2), "count": len(values)}], "x_key": "bin", "y_keys": ["count"]}

    bin_count = min(10, max(4, math.ceil(math.sqrt(len(values)))))
    width = (maximum - minimum) / bin_count
    bins = [{"start": minimum + index * width, "end": minimum + (index + 1) * width, "count": 0} for index in range(bin_count)]
    bins[-1]["end"] = maximum
    for value in values:
        index = min(bin_count - 1, int((value - minimum) / width))
        bins[index]["count"] += 1
    rows = [
        {
            "bin": f"{_format_number(bin['start'], 2)}-{_format_number(bin['end'], 2)}",
            "count": bin["count"],
        }
        for bin in bins
    ]
    return {"data": rows, "x_key": "bin", "y_keys": ["count"]}


def _payload_list(value: Any) -> list[Any] | None:
    return value if isinstance(value, list) else None


def _payload_point_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        for candidate_key in [key, "y", "value", "count", "total", "x"]:
            if candidate_key in value and value[candidate_key] is not None:
                return value[candidate_key]
        return ""
    return value


def _infer_payload_x_key(rows: list[dict[str, Any]], chart_type: str) -> str | None:
    keys = list(dict.fromkeys(key for row in rows for key in row))
    if not keys:
        return None
    preferred = (
        ["x"]
        if chart_type in {"scatter", "bubble"}
        else ["label", "name", "category", "x", "week_label", "week", "date", "zone", "city", "country"]
    )
    normalized = {key.lower(): key for key in keys}
    for key in preferred:
        if key in normalized:
            return normalized[key]
    for key in keys:
        if any(_to_float(row.get(key)) is None for row in rows):
            return key
    return keys[0]


def _infer_payload_y_keys(
    rows: list[dict[str, Any]],
    *,
    x_key: str,
    z_key: str | None,
    chart_type: str,
) -> list[str]:
    numeric = [
        key
        for key in dict.fromkeys(key for row in rows for key in row)
        if key not in {x_key, z_key} and any(_to_float(row.get(key)) is not None for row in rows)
    ]
    if chart_type in {"scatter", "bubble"} and "y" in numeric:
        return ["y"]
    if "value" in numeric:
        return ["value"]
    limit = 8 if chart_type in {"line", "area", "combo"} else 4
    return numeric[:limit]


def _infer_payload_z_key(rows: list[dict[str, Any]], *, x_key: str, y_key: str) -> str | None:
    numeric = [
        key
        for key in dict.fromkeys(key for row in rows for key in row)
        if key not in {x_key, y_key} and any(_to_float(row.get(key)) is not None for row in rows)
    ]
    normalized = {key.lower(): key for key in numeric}
    for key in ["z", "size", "radius", "volume", "count", "n", "orders"]:
        if key in normalized:
            return normalized[key]
    return numeric[0] if numeric else None


def _payload_chart_mode(payload: dict[str, Any]) -> str:
    raw = " ".join(
        str(value)
        for value in [
            payload.get("type"),
            payload.get("kind"),
            payload.get("chartType"),
            payload.get("mode"),
            payload.get("variant"),
            payload.get("layout"),
        ]
        if value is not None
    ).lower()
    raw = re.sub(r"[_-]+", " ", raw)
    if payload.get("stacked") is True or re.search(r"\bstack(?:ed)?\b", raw):
        return "stacked"
    if re.search(r"\bgroup(?:ed)?\b", raw):
        return "grouped"
    return ""


def _query_bar_chart_from_payload(
    data: list[dict[str, Any]],
    *,
    x_key: str,
    y_keys: list[str],
    title: str | None,
    stacked: bool = False,
) -> str:
    x_labels = [_chart_label(row.get(x_key)) for row in data]
    x_labels = [label for label in x_labels if label]
    if not x_labels:
        return ""

    plots = []
    colors = ["rappiOrange", "rappiBlue", "rappiGreen", "rappiPurple"]
    series_indexes = list(range(len(y_keys) - 1, -1, -1)) if stacked and len(y_keys) > 1 else list(range(len(y_keys)))
    for index in series_indexes:
        y_key = y_keys[index]
        coords = []
        for point_index, row in enumerate(data):
            if stacked and len(y_keys) > 1:
                values = [_to_float(row.get(key)) or 0.0 for key in y_keys[: index + 1]]
                value = sum(values)
            else:
                value = _to_float(row.get(y_key))
            label = _chart_label(row.get(x_key))
            if value is None or not label:
                continue
            coords.append(f"({point_index},{value:.6g})")
        if coords:
            color = colors[index % len(colors)]
            plot_options = f"fill={color}, draw={color}"
            if stacked and len(y_keys) > 1:
                plot_options += ", bar shift=0pt"
            plots.append(
                f"\\addplot[{plot_options}] coordinates "
                f"{{{' '.join(coords)}}};\n"
                f"\\addlegendentry{{{_latex_escape(_truncate(y_key, 28))}}}"
            )
    if not plots:
        return ""

    xticks, xticklabels, tick_style = _payload_tick_options(data, x_key)
    bar_width = _payload_bar_width(len(data))
    ylabel = _axis_title(y_keys[0]) if len(y_keys) == 1 else "Value"
    legend = (
        "legend style={font=\\scriptsize, at={(0.02,0.98)}, anchor=north west, fill=white, fill opacity=0.82, text opacity=1, draw=rappiLine},"
        if len(y_keys) > 1
        else "legend style={draw=none},"
    )
    caption = title or _chart_title("Bar chart", y_keys[0], x_key)
    ybar_mode = "ybar, bar shift=0pt," if stacked and len(y_keys) > 1 else "ybar,"
    return rf"""\begin{{figure}}[H]
\centering
\begin{{tikzpicture}}
\begin{{axis}}[
  width=0.95\linewidth,
  height=6.7cm,
  {ybar_mode}
  bar width={bar_width:.2f}pt,
  xlabel={{{_latex_escape(_axis_title(x_key))}}},
  ylabel={{{_latex_escape(ylabel)}}},
  xtick={{{xticks}}},
  xticklabels={{{xticklabels}}},
  xticklabel style={{{tick_style}}},
  ymajorgrids=true,
  grid style={{draw=rappiLine}},
  {legend}
]
{chr(10).join(plots)}
\end{{axis}}
\end{{tikzpicture}}
\caption{{{_latex_escape(caption)}}}
\end{{figure}}
"""


def _query_area_chart_from_payload(
    data: list[dict[str, Any]],
    *,
    x_key: str,
    y_keys: list[str],
    title: str | None,
    stacked: bool = False,
) -> str:
    if len(data) < 2:
        return ""

    plots = []
    colors = ["rappiBlue", "rappiOrange", "rappiGreen", "rappiPurple", "rappiRed", "rappiMuted"]
    for index, y_key in enumerate(y_keys):
        coords = []
        for point_index, row in enumerate(data):
            value = _to_float(row.get(y_key))
            if value is not None:
                coords.append(f"({point_index},{value:.6g})")
        if len(coords) >= 2:
            color = colors[index % len(colors)]
            if stacked:
                plots.append(
                    f"\\addplot+[mark=none, thick, color={color}, fill={color}!22] coordinates "
                    f"{{{' '.join(coords)}}} \\closedcycle;\n"
                    f"\\addlegendentry{{{_latex_escape(_truncate(y_key, 28))}}}"
                )
            else:
                plots.append(
                    f"\\addplot+[mark=none, thick, color={color}, fill={color}!18] coordinates "
                    f"{{{' '.join(coords)}}} \\closedcycle;\n"
                    f"\\addlegendentry{{{_latex_escape(_truncate(y_key, 28))}}}"
                )
    if not plots:
        return ""

    xticks, xticklabels, tick_style = _payload_tick_options(data, x_key)
    ylabel = _axis_title(y_keys[0]) if len(y_keys) == 1 else "Value"
    legend = (
        "legend style={font=\\scriptsize, at={(0.02,0.98)}, anchor=north west, fill=white, fill opacity=0.82, text opacity=1, draw=rappiLine},"
        if len(y_keys) > 1
        else "legend style={draw=none},"
    )
    caption = title or _chart_title("Area chart", y_keys[0], x_key)
    return rf"""\begin{{figure}}[H]
\centering
\begin{{tikzpicture}}
\begin{{axis}}[
  width=0.95\linewidth,
  height=6.7cm,
  ymin=0,
  xlabel={{{_latex_escape(_axis_title(x_key))}}},
  ylabel={{{_latex_escape(ylabel)}}},
  xtick={{{xticks}}},
  xticklabels={{{xticklabels}}},
  xticklabel style={{{tick_style}}},
  ymajorgrids=true,
  grid style={{draw=rappiLine}},
  {legend}
]
{chr(10).join(plots)}
\end{{axis}}
\end{{tikzpicture}}
\caption{{{_latex_escape(caption)}}}
\end{{figure}}
"""


def _query_line_chart_from_payload(
    data: list[dict[str, Any]],
    *,
    x_key: str,
    y_keys: list[str],
    title: str | None,
) -> str:
    if len(data) < 2:
        return ""

    plots = []
    colors = ["rappiBlue", "rappiOrange", "rappiGreen", "rappiPurple", "rappiRed", "rappiMuted"]
    for index, y_key in enumerate(y_keys):
        coords = []
        for point_index, row in enumerate(data):
            value = _to_float(row.get(y_key))
            if value is not None:
                coords.append(f"({point_index},{value:.6g})")
        if len(coords) >= 2:
            color = colors[index % len(colors)]
            plots.append(
                f"\\addplot+[mark=*, thick, color={color}] coordinates "
                f"{{{' '.join(coords)}}};\n"
                f"\\addlegendentry{{{_latex_escape(_truncate(y_key, 28))}}}"
            )
    if not plots:
        return ""

    xticks, xticklabels, tick_style = _payload_tick_options(data, x_key)
    ylabel = _axis_title(y_keys[0]) if len(y_keys) == 1 else "Value"
    legend = (
        "legend style={font=\\scriptsize, at={(0.02,0.98)}, anchor=north west, fill=white, fill opacity=0.82, text opacity=1, draw=rappiLine},"
        if len(y_keys) > 1
        else "legend style={draw=none},"
    )
    caption = title or _chart_title("Line chart", y_keys[0], x_key)
    return rf"""\begin{{figure}}[H]
\centering
\begin{{tikzpicture}}
\begin{{axis}}[
  width=0.95\linewidth,
  height=6.7cm,
  xlabel={{{_latex_escape(_axis_title(x_key))}}},
  ylabel={{{_latex_escape(ylabel)}}},
  xtick={{{xticks}}},
  xticklabels={{{xticklabels}}},
  xticklabel style={{{tick_style}}},
  ymajorgrids=true,
  grid style={{draw=rappiLine}},
  {legend}
]
{chr(10).join(plots)}
\end{{axis}}
\end{{tikzpicture}}
\caption{{{_latex_escape(caption)}}}
\end{{figure}}
"""


def _query_combo_chart_from_payload(
    data: list[dict[str, Any]],
    *,
    x_key: str,
    y_keys: list[str],
    title: str | None,
) -> str:
    if len(data) < 2 or len(y_keys) < 2:
        return _query_bar_chart_from_payload(data, x_key=x_key, y_keys=y_keys, title=title)

    plots = []
    colors = ["rappiOrange", "rappiBlue", "rappiGreen", "rappiPurple", "rappiRed", "rappiMuted"]
    first_key = y_keys[0]
    bar_coords = []
    for point_index, row in enumerate(data):
        value = _to_float(row.get(first_key))
        if value is not None and _chart_label(row.get(x_key)):
            bar_coords.append(f"({point_index},{value:.6g})")
    if bar_coords:
        plots.append(
            f"\\addplot+[ybar, fill={colors[0]}, draw={colors[0]}] coordinates "
            f"{{{' '.join(bar_coords)}}};\n"
            f"\\addlegendentry{{{_latex_escape(_truncate(first_key, 28))}}}"
        )

    for index, y_key in enumerate(y_keys[1:], start=1):
        coords = []
        for point_index, row in enumerate(data):
            value = _to_float(row.get(y_key))
            if value is not None:
                coords.append(f"({point_index},{value:.6g})")
        if len(coords) >= 2:
            color = colors[index % len(colors)]
            plots.append(
                f"\\addplot+[mark=*, thick, color={color}] coordinates "
                f"{{{' '.join(coords)}}};\n"
                f"\\addlegendentry{{{_latex_escape(_truncate(y_key, 28))}}}"
            )
    if not plots:
        return ""

    xticks, xticklabels, tick_style = _payload_tick_options(data, x_key)
    bar_width = _payload_bar_width(len(data))
    caption = title or _chart_title("Combo chart", first_key, x_key)
    return rf"""\begin{{figure}}[H]
\centering
\begin{{tikzpicture}}
\begin{{axis}}[
  width=0.95\linewidth,
  height=6.7cm,
  bar width={bar_width:.2f}pt,
  xlabel={{{_latex_escape(_axis_title(x_key))}}},
  ylabel={{Value}},
  xtick={{{xticks}}},
  xticklabels={{{xticklabels}}},
  xticklabel style={{{tick_style}}},
  ymajorgrids=true,
  grid style={{draw=rappiLine}},
  legend style={{font=\scriptsize, at={{(0.02,0.98)}}, anchor=north west, fill=white, fill opacity=0.82, text opacity=1, draw=rappiLine}},
]
{chr(10).join(plots)}
\end{{axis}}
\end{{tikzpicture}}
\caption{{{_latex_escape(caption)}}}
\end{{figure}}
"""


def _query_pie_chart_from_payload(
    data: list[dict[str, Any]],
    *,
    x_key: str,
    y_key: str,
    title: str | None,
    donut: bool = False,
) -> str:
    slices = _pie_slices(data, x_key=x_key, y_key=y_key)
    if len(slices) < 2:
        return ""

    return _tikz_pie_chart(
        title=title or _chart_title("Donut chart" if donut else "Pie chart", y_key, x_key),
        slices=slices,
        donut=donut,
    )


def _query_pie_chart_from_rows(
    rows: list[Any],
    columns: list[str],
    *,
    preferred_x: str | None,
    preferred_y: str | None,
    donut: bool = False,
) -> str:
    category_col = preferred_x or _preferred_category_column(rows, columns)
    y_col = preferred_y or _preferred_y_column(rows, columns, exclude={category_col or ""})
    if category_col is None or y_col is None:
        return ""

    row_dicts = [row for row in rows if isinstance(row, dict)]
    slices = _pie_slices(row_dicts, x_key=category_col, y_key=y_col)
    if len(slices) < 2:
        return ""

    return _tikz_pie_chart(
        title=_chart_title("Donut chart" if donut else "Pie chart", y_col, category_col),
        slices=slices,
        donut=donut,
    )


def _pie_slices(
    data: list[dict[str, Any]],
    *,
    x_key: str,
    y_key: str,
) -> list[tuple[str, float]]:
    slices = []
    for row in data:
        label = _chart_label(row.get(x_key))
        value = _to_float(row.get(y_key))
        if label and value is not None and value > 0:
            slices.append((_truncate(label, 28), value))
    slices = sorted(slices, key=lambda item: item[1], reverse=True)
    if len(slices) > 8:
        kept = slices[:7]
        other = sum(value for _, value in slices[7:])
        slices = kept + [("Other", other)]
    return slices


def _tikz_pie_chart(
    *,
    title: str,
    slices: list[tuple[str, float]],
    donut: bool,
) -> str:
    total = sum(value for _, value in slices)
    if total <= 0:
        return ""

    colors = ["rappiOrange", "rappiBlue", "rappiGreen", "rappiPurple", "rappiRed", "rappiMuted"]
    start = 90.0
    paths = []
    legend_rows = []
    for index, (label, value) in enumerate(slices):
        angle = 360.0 * value / total
        end = start - angle
        color = colors[index % len(colors)]
        paths.append(
            f"\\path[fill={color}, draw=white, line width=0.7pt] "
            f"(0,0) -- ({start:.4f}:2.15) arc ({start:.4f}:{end:.4f}:2.15) -- cycle;"
        )
        legend_rows.append(
            f"\\node[anchor=west, font=\\scriptsize] at (0, {-0.34 * index:.2f}) "
            f"{{\\textcolor{{{color}}}{{\\rule{{7pt}}{{7pt}}}} "
            f"{_latex_escape(label)} ({value / total * 100:.1f}\\%)}};"
        )
        start = end

    center = (
        "\\fill[white] (0,0) circle (1.05);\n\\draw[rappiLine, line width=0.4pt] (0,0) circle (1.05);"
        if donut
        else ""
    )
    return rf"""\begin{{figure}}[H]
\centering
\begin{{tikzpicture}}
{chr(10).join(paths)}
{center}
\begin{{scope}}[xshift=3.05cm,yshift=1.25cm]
{chr(10).join(legend_rows)}
\end{{scope}}
\end{{tikzpicture}}
\caption{{{_latex_escape(title)}}}
\end{{figure}}
"""


def _payload_tick_options(data: list[dict[str, Any]], x_key: str) -> tuple[str, str, str]:
    count = len(data)
    if count <= 18:
        step = 1
        max_label = 24
        tick_style = r"font=\scriptsize, rotate=35, anchor=east"
    elif count <= 40:
        step = 2
        max_label = 20
        tick_style = r"font=\tiny, rotate=55, anchor=east"
    else:
        step = max(1, math.ceil(count / 24))
        max_label = 18
        tick_style = r"font=\tiny, rotate=60, anchor=east"

    tick_indexes = list(range(0, count, step))
    if count and tick_indexes[-1] != count - 1:
        tick_indexes.append(count - 1)

    xticks = ",".join(str(index) for index in tick_indexes)
    xticklabels = ",".join(
        f"{{{_latex_escape(_truncate(_chart_label(data[index].get(x_key)), max_label))}}}"
        for index in tick_indexes
    )
    return xticks, xticklabels, tick_style


def _payload_bar_width(point_count: int) -> float:
    if point_count <= 0:
        return 7.0
    return max(1.2, min(7.0, 95.0 / point_count))


def _query_scatter_chart_from_payload(
    data: list[dict[str, Any]],
    *,
    x_key: str,
    y_key: str,
    title: str | None,
    z_key: str | None = None,
) -> str:
    coords = []
    for row in data:
        x_value = _to_float(row.get(x_key))
        y_value = _to_float(row.get(y_key))
        if x_value is not None and y_value is not None:
            coords.append(f"({x_value:.6g},{y_value:.6g})")
    if len(coords) < 2:
        return ""

    size_note = f" Bubble size: {_axis_title(z_key)}." if z_key else ""
    caption = title or _chart_title("Scatter chart", y_key, x_key)
    return rf"""\begin{{figure}}[H]
\centering
\begin{{tikzpicture}}
\begin{{axis}}[
  width=0.9\linewidth,
  height=6.5cm,
  xlabel={{{_latex_escape(_axis_title(x_key))}}},
  ylabel={{{_latex_escape(_axis_title(y_key))}}},
  xmajorgrids=true,
  ymajorgrids=true,
  grid style={{draw=rappiLine}},
]
\addplot+[only marks, mark=*, mark size=3pt, color=rappiPurple] coordinates {{{' '.join(coords)}}};
\end{{axis}}
\end{{tikzpicture}}
\caption{{{_latex_escape(caption + size_note)}}}
\end{{figure}}
"""


def _query_chart_hint(result: Any) -> str:
    hint = str(getattr(result, "visualization_hint", "") or "").strip().lower()
    if hint:
        return _normalize_query_chart_hint(hint)
    chart = getattr(result, "chart", None)
    if chart is not None:
        payload = _chart_payload(chart)
        return _normalize_query_chart_hint(str(payload.get("type") or "").strip().lower())
    return ""


def _resolved_query_chart_hint(result: Any, rows: list[Any], columns: list[str]) -> str:
    hint = _query_chart_hint(result)
    if hint in {"none", "table"}:
        return hint
    if not rows or not columns:
        return "table"
    if _is_small_segment_comparison(rows, columns):
        return "bar"
    if hint in {"line", "area"}:
        return hint if _has_time_column(columns) and _plottable_numeric_columns(rows, columns) else "table"
    if hint in {"scatter", "bubble"}:
        if _has_scatter_shape(rows, columns):
            return hint
        return "bar" if _has_bar_shape(rows, columns) else "table"
    if hint in {"pie", "donut", "histogram", "combo"}:
        return hint if _has_bar_shape(rows, columns) else "table"
    if hint == "bar":
        return "bar" if _has_bar_shape(rows, columns) else "table"
    return "table"


def _auto_query_chart_hint(rows: list[Any], columns: list[str]) -> str:
    if not rows or not columns:
        return "table"
    if _is_small_segment_comparison(rows, columns):
        return "bar"
    if _has_time_column(columns) and _plottable_numeric_columns(rows, columns):
        return "line"
    if _has_bar_shape(rows, columns):
        return "bar"
    if _has_scatter_shape(rows, columns):
        return "scatter"
    return "table"


def _normalize_query_chart_hint(value: str) -> str:
    text = re.sub(r"[\s-]+", "_", str(value or "").strip().lower())
    if text in {"none", "table", "bar", "line", "scatter", "area", "pie", "donut", "histogram", "bubble", "combo"}:
        return text
    if text in {"doughnut", "donut_chart", "doughnut_chart"}:
        return "donut"
    if text in {"pie_chart"}:
        return "pie"
    if text in {"bar_chart", "column", "columns", "column_chart", "grouped_bar", "stacked_bar", "horizontal_bar"}:
        return "bar"
    if text in {"trend", "timeseries", "time_series", "line_chart", "area_chart", "stacked_area"}:
        return "area" if "area" in text else "line"
    if text in {"scatterplot", "scatter_plot"}:
        return "scatter"
    if text in {"bubble_chart"}:
        return "bubble"
    if text in {"histograma", "distribution"}:
        return "histogram"
    if text in {"combined", "composed", "mixed", "dual_axis"}:
        return "combo"
    if value in {"none", "table", "bar", "line", "scatter"}:
        return value
    return "table"


def _valid_chart_column(value: Any, columns: list[str]) -> str | None:
    if not isinstance(value, str):
        return None
    return value if value in columns else None


def _has_time_column(columns: list[str]) -> bool:
    return any(re.search(r"week|semana|date|fecha", column, re.IGNORECASE) for column in columns)


def _has_bar_shape(rows: list[Any], columns: list[str]) -> bool:
    return _preferred_category_column(rows, columns) is not None and bool(
        _plottable_numeric_columns(rows, columns)
    )


def _has_scatter_shape(rows: list[Any], columns: list[str]) -> bool:
    numeric = _numeric_columns(rows, columns)
    primary = [
        column
        for column in numeric
        if not _is_count_column(column) and not _is_minmax_column(column)
    ]
    count_like = [column for column in numeric if _is_count_column(column)]
    return len(primary) >= 2 or (len(rows) > 2 and bool(primary) and bool(count_like))


def _is_small_segment_comparison(rows: list[Any], columns: list[str]) -> bool:
    return len(rows) <= 6 and any(
        re.search(r"zone_type|segment|tipo|wealthy", column, re.IGNORECASE)
        for column in columns
    )


def _primary_numeric_columns(rows: list[Any], columns: list[str]) -> list[str]:
    return [
        column
        for column in _numeric_columns(rows, columns)
        if not _is_count_column(column) and not _is_minmax_column(column)
    ]


def _plottable_numeric_columns(rows: list[Any], columns: list[str]) -> list[str]:
    primary = _primary_numeric_columns(rows, columns)
    if primary:
        return primary
    return [
        column
        for column in _numeric_columns(rows, columns)
        if not _is_minmax_column(column)
    ]


def _query_line_chart(
    rows: list[Any],
    columns: list[str],
    *,
    preferred_x: str | None = None,
    preferred_y: str | None = None,
    preferred_series: str | None = None,
) -> str:
    x_col = preferred_x or _preferred_x_column(columns, ["week_label", "week", "semana", "date", "fecha"])
    if x_col is None and "week_offset" in columns:
        x_col = "week_offset"
    if x_col is None:
        return ""

    series_col = preferred_series or _preferred_series_column(columns, exclude={x_col})
    y_col = preferred_y or _preferred_y_column(rows, columns, exclude={x_col, series_col or "", "week_offset"})
    if y_col is None:
        return ""

    x_labels = _ordered_x_labels(rows, x_col)
    if len(x_labels) < 2:
        return ""

    x_index = {label: index for index, label in enumerate(x_labels)}
    series_values: dict[str, list[tuple[int, float]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        x_label = _chart_label(row.get(x_col))
        value = _to_float(row.get(y_col))
        if x_label not in x_index or value is None:
            continue
        series_label = _chart_label(row.get(series_col)) if series_col else _truncate(y_col, 24)
        series_values.setdefault(series_label, []).append((x_index[x_label], value))

    series_items = [
        (label, sorted(points))
        for label, points in series_values.items()
        if len(points) >= 2
    ][:10]
    if not series_items:
        return ""

    scale, ylabel = _chart_scale(y_col, [value for _, points in series_items for _, value in points])
    plots = []
    colors = [
        "rappiBlue",
        "rappiOrange",
        "rappiGreen",
        "rappiPurple",
        "rappiRed",
        "rappiMuted",
    ]
    max_y = 1.0
    for index, (label, points) in enumerate(series_items):
        coords = " ".join(f"({x},{value * scale:.4f})" for x, value in points)
        max_y = max(max_y, *(value * scale for _, value in points))
        plots.append(
            "\\addplot+[mark=*, thick, color="
            f"{colors[index % len(colors)]}] coordinates {{{coords}}};\n"
            f"\\addlegendentry{{{_latex_escape(_truncate(label, 28))}}}"
        )

    xticks = ",".join(str(index) for index in range(len(x_labels)))
    xticklabels = ",".join(f"{{{_latex_escape(label)}}}" for label in x_labels)
    ymax = max_y * 1.18 if max_y > 0 else 1
    return rf"""\begin{{figure}}[H]
\centering
\begin{{tikzpicture}}
\begin{{axis}}[
  width=0.95\linewidth,
  height=7.0cm,
  ymin=0,
  ymax={ymax:.4f},
  xlabel={{{_latex_escape(_axis_title(x_col))}}},
  ylabel={{{_latex_escape(ylabel)}}},
  xtick={{{xticks}}},
  xticklabels={{{xticklabels}}},
  xticklabel style={{font=\scriptsize, rotate=35, anchor=east}},
  ymajorgrids=true,
  grid style={{draw=rappiLine}},
  legend style={{font=\scriptsize, at={{(1.02,1)}}, anchor=north west}},
]
{chr(10).join(plots)}
\end{{axis}}
\end{{tikzpicture}}
\caption{{{_latex_escape(_chart_title("Line chart", y_col, x_col))}}}
\end{{figure}}
"""


def _query_bar_chart(
    rows: list[Any],
    columns: list[str],
    *,
    preferred_x: str | None = None,
    preferred_y: str | None = None,
) -> str:
    category_col = preferred_x or _preferred_category_column(rows, columns)
    y_col = preferred_y or _preferred_y_column(rows, columns, exclude={category_col or ""})
    if category_col is None or y_col is None:
        return ""

    points = []
    raw_values = []
    for row in rows[:14]:
        if not isinstance(row, dict):
            continue
        value = _to_float(row.get(y_col))
        label = _chart_label(row.get(category_col))
        if value is None or not label:
            continue
        raw_values.append(value)
        points.append((_truncate(label, 34), value))
    if len(points) < 2:
        return ""

    scale, xlabel = _chart_scale(y_col, raw_values)
    scaled_points = [(label, value * scale) for label, value in points]
    xmax = max(value for _, value in scaled_points) * 1.18
    return _xbar_chart(
        title=_chart_title("Bar chart", y_col, category_col),
        xlabel=xlabel,
        points=scaled_points,
        series=[(_truncate(y_col, 28), "rappiOrange", scaled_points)],
        xmin=0,
        xmax=max(1.0, xmax),
    )


def _query_scatter_chart(
    rows: list[Any],
    columns: list[str],
    *,
    preferred_x: str | None = None,
    preferred_y: str | None = None,
) -> str:
    numeric = [
        column
        for column in _numeric_columns(rows, columns)
        if not _is_minmax_column(column) and "offset" not in column.lower()
    ]
    if len(numeric) < 2:
        return ""

    x_col = preferred_x if preferred_x in numeric else next((column for column in numeric if _is_count_column(column)), numeric[0])
    y_col = preferred_y if preferred_y in numeric and preferred_y != x_col else None
    if y_col is None:
        y_col = next(
            (
                column
                for column in numeric
                if column != x_col and not _is_count_column(column) and not _is_minmax_column(column)
            ),
            None,
        )
    if y_col is None:
        y_col = next((column for column in numeric if column != x_col), None)
    if y_col is None:
        return ""

    label_col = _preferred_category_column(rows, columns)

    raw_points = []
    for row in rows[:80]:
        if not isinstance(row, dict):
            continue
        x = _to_float(row.get(x_col))
        y = _to_float(row.get(y_col))
        if x is None or y is None:
            continue
        raw_points.append((x, y))
    if len(raw_points) < 2:
        return ""

    x_values = [point[0] for point in raw_points]
    y_values = [point[1] for point in raw_points]
    x_scale, xlabel = _chart_scale(x_col, x_values)
    y_scale, ylabel = _chart_scale(y_col, y_values)
    coords = " ".join(f"({x * x_scale:.4f},{y * y_scale:.4f})" for x, y in raw_points)
    label_note = (
        f" Labels available in CSV: {_latex_escape(label_col)}."
        if label_col and label_col not in {x_col, y_col}
        else ""
    )
    return rf"""\begin{{figure}}[H]
\centering
\begin{{tikzpicture}}
\begin{{axis}}[
  width=0.9\linewidth,
  height=6.5cm,
  xlabel={{{_latex_escape(xlabel)}}},
  ylabel={{{_latex_escape(ylabel)}}},
  xmajorgrids=true,
  ymajorgrids=true,
  grid style={{draw=rappiLine}},
]
\addplot+[only marks, mark=*, mark size=3pt, color=rappiPurple] coordinates {{{coords}}};
\end{{axis}}
\end{{tikzpicture}}
\caption{{{_latex_escape(_chart_title("Scatter chart", y_col, x_col) + label_note)}}}
\end{{figure}}
"""


def _preferred_x_column(columns: list[str], names: list[str]) -> str | None:
    normalized = {column.lower(): column for column in columns}
    for name in names:
        if name in normalized:
            return normalized[name]
    for column in columns:
        lowered = column.lower()
        if any(name in lowered for name in names):
            return column
    return None


def _preferred_series_column(columns: list[str], exclude: set[str]) -> str | None:
    for pattern in ["country", "city", "zone_type", "zone", "metric", "segment"]:
        for column in columns:
            lowered = column.lower()
            if column not in exclude and pattern in lowered and "offset" not in lowered:
                return column
    return None


def _preferred_category_column(rows: list[Any], columns: list[str]) -> str | None:
    for pattern in ["country", "city", "zone", "metric", "segment", "type", "label"]:
        for column in columns:
            if pattern in column.lower() and column not in _numeric_columns(rows, columns):
                return column
    numeric = set(_numeric_columns(rows, columns))
    return next((column for column in columns if column not in numeric), None)


def _preferred_y_column(
    rows: list[Any],
    columns: list[str],
    *,
    exclude: set[str],
) -> str | None:
    numeric = _numeric_columns(rows, columns)
    candidates = [
        column
        for column in numeric
        if column not in exclude
        and not _is_count_column(column)
        and not _is_minmax_column(column)
        and "offset" not in column.lower()
    ]
    if candidates:
        return sorted(candidates, key=_y_column_priority)[0]
    fallback = [column for column in numeric if column not in exclude]
    return sorted(fallback, key=_y_column_priority)[0] if fallback else None


def _y_column_priority(column: str) -> tuple[int, int]:
    lowered = column.lower()
    if "problem_score" in lowered or lowered.endswith("_score"):
        return (0, len(column))
    if "pct_change" in lowered or "percent_change" in lowered or "growth_rate" in lowered:
        return (1, len(column))
    if "absolute_change" in lowered or lowered.endswith("_change"):
        return (2, len(column))
    if lowered == "value" or lowered.startswith(("avg_", "average_", "mean_")):
        return (3, len(column))
    if any(token in lowered for token in ["penetration", "perfect", "gross_profit", "rate"]):
        return (4, len(column))
    if lowered.endswith("_current"):
        return (5, len(column))
    return (10, len(column))


def _numeric_columns(rows: list[Any], columns: list[str]) -> list[str]:
    numeric = []
    for column in columns:
        values = [
            _to_float(row.get(column))
            for row in rows
            if isinstance(row, dict) and row.get(column) is not None
        ]
        values = [value for value in values if value is not None]
        if values and len(values) >= max(1, min(3, len(rows) // 4)):
            numeric.append(column)
    return numeric


def _ordered_x_labels(rows: list[Any], x_col: str) -> list[str]:
    labels = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = _chart_label(row.get(x_col))
        if label and label not in seen:
            labels.append(label)
            seen.add(label)
    if labels and all(re.match(r"^L\d+W$", label, re.IGNORECASE) for label in labels):
        return sorted(labels, key=lambda label: int(label[1:-1]), reverse=True)
    return labels[:16]


def _chart_scale(column: str, values: list[float]) -> tuple[float, str]:
    finite = [value for value in values if math.isfinite(value)]
    lowered = column.lower()
    if finite and max(abs(value) for value in finite) <= 1.2 and any(
        token in lowered for token in ["rate", "pct", "percent", "penetration", "cvr", "order"]
    ):
        return 100.0, f"{_axis_title(column)} (%)"
    return 1.0, _axis_title(column)


def _chart_label(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _axis_title(column: str) -> str:
    return column.replace("_", " ").strip().title()


def _chart_title(kind: str, y_col: str, x_col: str) -> str:
    return f"{kind}: {_axis_title(y_col)} by {_axis_title(x_col)}"


def _is_count_column(column: str) -> bool:
    lowered = column.lower()
    return (
        lowered in {"n", "count", "zones", "zonas", "n_zones", "orders", "start_orders", "end_orders"}
        or lowered.startswith(("n_", "num_"))
        or lowered.endswith(("_count", "_orders"))
        or "count" in lowered
    )


def _is_minmax_column(column: str) -> bool:
    lowered = column.lower()
    return lowered.startswith("min") or lowered.startswith("max") or lowered.endswith("_min") or lowered.endswith("_max")


def _query_column_width(column_count: int) -> float:
    if column_count <= 1:
        return 0.92
    if column_count == 2:
        return 0.45
    if column_count == 3:
        return 0.30
    if column_count == 4:
        return 0.225
    return max(0.108, 0.90 / column_count)


def _row_value(row: Any, column: str) -> Any:
    if isinstance(row, dict):
        return row.get(column)
    return ""


def _format_query_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        return f"{value:.6g}"
    if isinstance(value, dict | list):
        return _truncate(json.dumps(value, ensure_ascii=True, default=str), 120)
    return _truncate(str(value), 120)


def _latex_items(values: list[Any], empty_text: str) -> str:
    items = [str(value).strip() for value in values if str(value).strip()]
    if not items:
        items = [empty_text]
    return "\n".join(f"\\item {_latex_escape(item)}" for item in items)


def _findings_by_id(report: InsightReport) -> dict[str, InsightFinding]:
    return {
        finding.id: finding
        for category in report.categories
        for finding in category.findings
    }


def _authored_summary_item(
    item: AuthoredReportFinding, findings_by_id: dict[str, InsightFinding]
) -> str:
    source = findings_by_id.get(item.finding_id)
    severity = source.severity.upper() if source else "INFO"
    headline = item.headline or (source.title if source else "Insight")
    insight = item.insight or (source.summary if source else "")
    recommendation = item.recommendation or (source.recommendation if source else "")
    return (
        f"\\item \\severity{{{_latex_escape(severity)}}} "
        f"\\findingtitle{{{_latex_escape(headline)}}}\\\\\n"
        f"{_latex_escape(insight)}\\\\\n"
        f"\\textit{{Recommended action:}} {_latex_escape(recommendation)}"
    )


def _authored_category_section(
    section: Any, findings_by_id: dict[str, InsightFinding]
) -> str:
    if not section.findings:
        body = "\\item No findings detected for this category."
    else:
        body = "\n".join(
            _authored_detail_item(item, findings_by_id)
            for item in section.findings[:3]
        )
    narrative = _latex_escape(section.narrative) if section.narrative else ""
    return rf"""\subsection*{{{_latex_escape(section.title)}}}
{narrative}
\begin{{itemize}}
{body}
\end{{itemize}}
"""


def _authored_detail_item(
    item: AuthoredReportFinding, findings_by_id: dict[str, InsightFinding]
) -> str:
    source = findings_by_id.get(item.finding_id)
    severity = source.severity.upper() if source else "INFO"
    headline = item.headline or (source.title if source else "Insight")
    insight = item.insight or (source.summary if source else "")
    recommendation = item.recommendation or (source.recommendation if source else "")
    evidence = _compact_evidence(source) if source else ""
    evidence_text = f" \\textit{{Evidence:}} {_latex_escape(evidence)}" if evidence else ""
    return (
        f"\\item \\severity{{{_latex_escape(severity)}}} "
        f"\\findingtitle{{{_latex_escape(headline)}}}. "
        f"{_latex_escape(insight)} "
        f"\\textit{{Action:}} {_latex_escape(recommendation)}"
        f"{evidence_text}"
    )


def _summary_item(finding: InsightFinding) -> str:
    return (
        f"\\item \\severity{{{_latex_escape(finding.severity.upper())}}} "
        f"\\findingtitle{{{_latex_escape(finding.title)}}}\\\\\n"
        f"{_latex_escape(finding.summary)}\\\\\n"
        f"\\textit{{Recommended action:}} {_latex_escape(finding.recommendation)}"
    )


def _category_section(title: str, findings: list[InsightFinding]) -> str:
    if not findings:
        body = "\\item No findings detected for this category."
    else:
        body = "\n".join(_detail_item(finding) for finding in findings[:3])
    return rf"""\subsection*{{{_latex_escape(title)}}}
\begin{{itemize}}
{body}
\end{{itemize}}
"""


def _detail_item(finding: InsightFinding) -> str:
    evidence = _compact_evidence(finding)
    evidence_text = f" \\textit{{Evidence:}} {_latex_escape(evidence)}" if evidence else ""
    return (
        f"\\item \\severity{{{_latex_escape(finding.severity.upper())}}} "
        f"\\findingtitle{{{_latex_escape(finding.title)}}}. "
        f"{_latex_escape(finding.summary)} "
        f"\\textit{{Action:}} {_latex_escape(finding.recommendation)}"
        f"{evidence_text}"
    )


def _compact_evidence(finding: InsightFinding) -> str:
    evidence = finding.evidence
    fragments = []
    for key in ["country", "city", "zone", "metric"]:
        value = evidence.get(key)
        if value:
            fragments.append(str(value))
    if "change_score" in evidence:
        fragments.append(f"WoW score {_format_signed_score(evidence.get('change_score'))}")
    if "underperformance_score" in evidence:
        fragments.append(
            f"peer gap score {_format_number(evidence.get('underperformance_score'), 2)}"
        )
    if "pearson_correlation" in evidence:
        fragments.append(f"r={_format_number(evidence.get('pearson_correlation'), 2)}")
    if "opportunity_score" in evidence:
        fragments.append(f"score={_format_number(evidence.get('opportunity_score'), 2)}")
    return " | ".join(fragments[:6])


def _anomaly_chart(findings: list[InsightFinding]) -> str:
    points = []
    for finding in findings[:6]:
        change = _to_float(finding.evidence.get("change_score"))
        if change is None:
            continue
        direction = str(finding.evidence.get("direction") or "")
        impact = -change if direction == "lower_better" else change
        points.append((_short_label(finding), impact))
    if not points:
        return ""

    limit = max(1.0, max(abs(value) for _, value in points) * 1.18)
    positive = [(label, value) for label, value in points if value >= 0]
    negative = [(label, value) for label, value in points if value < 0]
    return _xbar_chart(
        title="WoW anomaly score",
        xlabel="Direction-adjusted change score (positive is favorable)",
        points=points,
        series=[
            ("Improvements", "rappiGreen", positive),
            ("Deteriorations", "rappiRed", negative),
        ],
        xmin=-limit,
        xmax=limit,
    )


def _trend_chart(findings: list[InsightFinding]) -> str:
    series = []
    max_value = 10.0
    for finding in findings[:3]:
        raw_values = finding.evidence.get("values")
        if not isinstance(raw_values, dict):
            continue
        start = _to_float(raw_values.get("L3W"))
        if start is None or abs(start) < 1e-9:
            continue
        direction = str(finding.evidence.get("direction") or "")
        coords = []
        for week_index, week in enumerate(["L3W", "L2W", "L1W", "L0W"]):
            raw = _to_float(raw_values.get(week))
            if raw is None:
                continue
            if direction == "lower_better":
                deterioration = (raw - start) / abs(start)
            else:
                deterioration = (start - raw) / abs(start)
            value = max(0.0, deterioration * 100)
            max_value = max(max_value, value)
            coords.append(f"({week_index},{value:.2f})")
        if coords:
            series.append((_short_label(finding, max_length=38), " ".join(coords)))
    if not series:
        return ""

    plots = []
    colors = ["rappiOrange", "rappiRed", "rappiBlue"]
    for index, (label, coords) in enumerate(series):
        plots.append(
            "\\addplot+[mark=*, thick, color="
            f"{colors[index % len(colors)]}] coordinates {{{coords}}};\n"
            f"\\addlegendentry{{{_latex_escape(label)}}}"
        )

    return rf"""\begin{{figure}}[H]
\centering
\begin{{tikzpicture}}
\begin{{axis}}[
  width=\linewidth,
  height=6.0cm,
  ymin=0,
  ymax={max_value * 1.18:.2f},
  xlabel={{Relative week}},
  ylabel={{Cumulative deterioration from L3W (\%)}},
  xtick={{0,1,2,3}},
  xticklabels={{L3W,L2W,L1W,L0W}},
  ymajorgrids=true,
  grid style={{draw=rappiLine}},
  legend style={{font=\scriptsize, at={{(0.02,0.98)}}, anchor=north west}},
]
{chr(10).join(plots)}
\end{{axis}}
\end{{tikzpicture}}
\caption{{Strict 3-week deterioration from the L3W baseline.}}
\end{{figure}}
"""


def _benchmark_chart(findings: list[InsightFinding]) -> str:
    points = []
    for finding in findings[:6]:
        value = _to_float(finding.evidence.get("underperformance_score"))
        if value is not None:
            points.append((_short_label(finding), value))
    if not points:
        return ""

    upper = max(20.0, max(value for _, value in points) * 1.18)
    return _xbar_chart(
        title="Peer benchmark gaps",
        xlabel="IQR-scaled underperformance score (higher is worse)",
        points=points,
        series=[("Underperformance", "rappiBlue", points)],
        xmin=0,
        xmax=upper,
    )


def _correlation_chart(findings: list[InsightFinding]) -> str:
    points = []
    rows = []
    for finding in findings[:6]:
        corr = _to_float(finding.evidence.get("pearson_correlation"))
        low_low = _to_float(finding.evidence.get("low_low_count"))
        if corr is None or low_low is None:
            continue
        label = (
            f"{finding.evidence.get('metric_x', 'Metric A')} / "
            f"{finding.evidence.get('metric_y', 'Metric B')}"
        )
        points.append(f"({corr:.4f},{low_low:.2f})")
        rows.append(
            f"{_latex_escape(_truncate(label, 46))} & {corr:.2f} & {int(low_low)} \\\\"
        )
    if not points:
        return ""

    scatter_coords = " ".join(points)
    table = "\n".join(rows)
    return rf"""\begin{{figure}}[H]
\centering
\begin{{tikzpicture}}
\begin{{axis}}[
  width=0.95\linewidth,
  height=6.0cm,
  xmin=-1,
  xmax=1,
  xlabel={{Pearson correlation}},
  ylabel={{Low-low zones}},
  ymajorgrids=true,
  xmajorgrids=true,
  grid style={{draw=rappiLine}},
]
\addplot+[only marks, mark=*, mark size=3.5pt, color=rappiPurple] coordinates {{{scatter_coords}}};
\addplot[domain=-1:1, samples=2, color=rappiMuted, dashed, mark=none] {{0}};
\end{{axis}}
\end{{tikzpicture}}
\caption{{Metric relationships and low-low zone concentration.}}
\end{{figure}}

\begin{{tabularx}}{{\linewidth}}{{Xrr}}
\toprule
Metric pair & Correlation & Low-low zones \\
\midrule
{table}
\bottomrule
\end{{tabularx}}
"""


def _opportunity_chart(findings: list[InsightFinding]) -> str:
    if not findings:
        return ""

    points = []
    for finding in findings[:5]:
        score = _to_float(finding.evidence.get("opportunity_score"))
        if score is not None:
            points.append((_short_label(finding, max_length=38), score))
    if not points:
        return ""

    upper = max(1.0, max(value for _, value in points) * 1.18)
    return _xbar_chart(
        title="Opportunity scores",
        xlabel="Composite intervention score (higher is more urgent)",
        points=points,
        series=[("Opportunity score", "rappiOrange", points)],
        xmin=0,
        xmax=upper,
    )


def _xbar_chart(
    *,
    title: str,
    xlabel: str,
    points: list[tuple[str, float]],
    series: list[tuple[str, str, list[tuple[str, float]]]],
    xmin: float,
    xmax: float,
) -> str:
    ytick = ",".join(str(index) for index in range(1, len(points) + 1))
    yticklabels = ",".join(f"{{{_latex_escape(label)}}}" for label, _ in points)
    plots = []
    label_to_y = {label: index for index, (label, _) in enumerate(points, start=1)}
    for _series_name, color, series_points in series:
        coords = " ".join(
            f"({value:.2f},{label_to_y[label]})"
            for label, value in series_points
            if label in label_to_y
        )
        if not coords:
            continue
        plots.append(
            f"\\addplot+[xbar, fill={color}, draw={color}] coordinates {{{coords}}};"
        )

    return rf"""\begin{{figure}}[H]
\centering
\begin{{tikzpicture}}
\begin{{axis}}[
  xbar,
  width=0.76\linewidth,
  height={max(4.4, 0.55 * len(points) + 2.2):.2f}cm,
  xmin={xmin:.2f},
  xmax={xmax:.2f},
  xlabel={{{_latex_escape(xlabel)}}},
  ytick={{{ytick}}},
  yticklabels={{{yticklabels}}},
  yticklabel style={{font=\scriptsize, text width=4.1cm, align=right}},
  xmajorgrids=true,
  grid style={{draw=rappiLine}},
]
{chr(10).join(plots)}
\end{{axis}}
\end{{tikzpicture}}
\caption{{{_latex_escape(title)}}}
\end{{figure}}
"""


def _short_label(finding: InsightFinding, max_length: int = 34) -> str:
    evidence = finding.evidence
    zone = str(evidence.get("zone") or "")
    city = str(evidence.get("city") or "")
    metric = str(evidence.get("metric") or "")
    pieces = [piece for piece in [zone, city, metric] if piece]
    return _truncate(" - ".join(pieces) or finding.title, max_length)


def _latex_escape(value: Any) -> str:
    text = str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    escaped = "".join(replacements.get(char, char) for char in text)
    return (
        escaped.replace("–", "-")
        .replace("—", "-")
        .replace("−", "-")
        .replace("\u202f", " ")
        .replace("\xa0", " ")
    )


def _truncate(value: str, max_length: int) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= max_length:
        return cleaned
    return f"{cleaned[: max_length - 5].rstrip()} [..]"


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        try:
            number = float(value)
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def _format_pct(value: Any) -> str:
    number = _to_float(value)
    if number is None:
        return "n/a"
    return f"{number * 100:+.1f}%"


def _format_signed_score(value: Any) -> str:
    number = _to_float(value)
    if number is None:
        return "n/a"
    return f"{number:+.2f}" if abs(number) < 10 else f"{number:+.1f}"


def _format_number(value: Any, digits: int) -> str:
    number = _to_float(value)
    if number is None:
        return "n/a"
    return f"{number:.{digits}f}"
