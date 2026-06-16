from __future__ import annotations

import math
import os
import json
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ops_copilot.insights import InsightFinding, InsightReport


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
    summary = "\n".join(_summary_item(finding) for finding in report.executive_summary[:5])
    category_sections = "\n".join(
        _category_section(category.title, category.findings)
        for category in report.categories
    )
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
{{\Huge \textbf{{Rappi Ops Executive Insight Report}}}}\\[4pt]
{{\large {_latex_escape(report.period_label)}}}\\[2pt]
{{\small Generated at {_latex_escape(report.generated_at)} from {_latex_escape(report.source)}}}
\end{{center}}

\vspace{{4pt}}
\hrule
\vspace{{8pt}}

\section*{{Executive Summary}}
\begin{{enumerate}}
{summary}
\end{{enumerate}}

\section*{{Insight Charts}}
{charts}

\section*{{Detail by Category}}
{category_sections}

\section*{{Data Caveats}}
\begin{{itemize}}
{caveats}
\end{{itemize}}

\end{{document}}
"""


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
    tex_path = build_dir / "executive-insights.tex"
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

    built_pdf = build_dir / "executive-insights.pdf"
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
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
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
        fragments.append(f"WoW impact {_format_pct(evidence.get('change_score'))}")
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
        points.append((_short_label(finding), impact * 100))
    if not points:
        return ""

    limit = max(12.0, max(abs(value) for _, value in points) * 1.18)
    positive = [(label, value) for label, value in points if value >= 0]
    negative = [(label, value) for label, value in points if value < 0]
    return _xbar_chart(
        title="WoW anomaly impact",
        xlabel="Directional week-over-week impact (positive is better)",
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
    weak_metrics = findings[0].evidence.get("weak_metrics")
    if not isinstance(weak_metrics, list):
        return ""

    points = []
    for item in weak_metrics[:5]:
        if not isinstance(item, dict):
            continue
        risk = _to_float(item.get("risk"))
        metric = str(item.get("metric") or "")
        if risk is not None and metric:
            points.append((_truncate(metric, 35), risk * 100))
    if not points:
        return ""

    zone_label = _truncate(str(findings[0].evidence.get("zone") or findings[0].title), 40)
    return _xbar_chart(
        title=f"Opportunity drivers: {zone_label}",
        xlabel="Metric risk percentile (higher is worse)",
        points=points,
        series=[("Risk", "rappiOrange", points)],
        xmin=0,
        xmax=100,
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


def _format_number(value: Any, digits: int) -> str:
    number = _to_float(value)
    if number is None:
        return "n/a"
    return f"{number:.{digits}f}"
