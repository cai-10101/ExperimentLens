"""Markdown, CSV, and static HTML report generation for ExperimentLens."""

import csv
import html
import json
from pathlib import Path

from .analyzer import AnalysisResult, _format_num


def _escape_md(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def generate_report(
    analysis: AnalysisResult,
    *,
    title: str = "ExperimentLens 实验结果统一分析报告",
) -> str:
    """Render a structured, verifiable Markdown report from an AnalysisResult."""
    comp = analysis.comparability
    lines: list[str] = [f"# {title}", ""]

    lines.append("## 1. 概览与可比性检查")
    lines.append("")
    lines.append(f"- **实验数量**：{len(analysis.records)}")
    lines.append(f"- **可比性状态**：{'可比较 (Comparable)' if comp.is_comparable else '不可直接比较 (Not Comparable)'}")
    if comp.is_comparable:
        lines.append(f"- **统一任务 (Task)**：`{comp.task}`")
        lines.append(f"- **统一数据集 (Dataset)**：`{comp.dataset}`")
        lines.append(f"- **统一评价划分 (Split)**：`{comp.split}`")
    else:
        for reason in comp.reasons:
            lines.append(f"- **不可比较原因**：{reason}")
    for warning in comp.warnings:
        lines.append(f"- **异常/缺失提示**：{warning}")
    if analysis.sort_by and comp.is_comparable:
        lines.append(f"- **排序依据指标**：`{analysis.sort_by}`")
    lines.append("")

    lines.append("## 2. 实验结果汇总表")
    lines.append("")
    metrics_cols = list(comp.all_metrics)
    headers = ["Experiment ID", "Model", "Dataset", "Task", "Split"] + metrics_cols + ["Config", "Source"]
    lines.append("| " + " | ".join(_escape_md(h) for h in headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")

    for rec in analysis.records:
        normalized_map = {k.strip(): v for k, v in rec.metrics.items()}
        metric_cells = [
            _format_num(normalized_map[m]) if m in normalized_map else "N/A"
            for m in metrics_cols
        ]
        config_str = json.dumps(rec.config, ensure_ascii=False, sort_keys=True) if rec.config else "{}"
        row = [
            rec.experiment_id.strip(),
            rec.model.strip(),
            rec.dataset.strip(),
            rec.task.strip(),
            rec.split.strip(),
            *metric_cells,
            config_str,
            rec.source.strip(),
        ]
        lines.append("| " + " | ".join(_escape_md(cell) for cell in row) + " |")
    lines.append("")

    lines.append("## 3. 指标统计与比较")
    lines.append("")
    if comp.is_comparable and analysis.metric_summaries:
        stat_headers = ["Metric", "Direction", "Best Experiment", "Best Value", "Max", "Min", "Delta (Max-Min)", "Ranking"]
        lines.append("| " + " | ".join(stat_headers) + " |")
        lines.append("| " + " | ".join("---" for _ in stat_headers) + " |")
        for m_name, summary in analysis.metric_summaries.items():
            dir_label = "higher (越大越好)" if summary.direction == "higher" else "lower (越小越好)"
            stat_row = [
                m_name,
                dir_label,
                summary.best_experiment_id,
                _format_num(summary.best_value),
                f"{_format_num(summary.max_value)} ({summary.max_experiment_id})",
                f"{_format_num(summary.min_value)} ({summary.min_experiment_id})",
                _format_num(summary.spread),
                " > ".join(summary.ranking),
            ]
            lines.append("| " + " | ".join(_escape_md(c) for c in stat_row) + " |")
    else:
        lines.append("> 当前实验集合不满足可比性条件，跳过跨实验极值与排名计算。")
    lines.append("")

    if analysis.config_diffs:
        lines.append("## 4. 实验配置差异")
        lines.append("")
        exp_ids = [r.experiment_id.strip() for r in analysis.records]
        cfg_headers = ["Config Key"] + exp_ids
        lines.append("| " + " | ".join(_escape_md(h) for h in cfg_headers) + " |")
        lines.append("| " + " | ".join("---" for _ in cfg_headers) + " |")
        for cfg_key, val_map in analysis.config_diffs.items():
            cfg_row = [cfg_key] + [json.dumps(val_map.get(eid), ensure_ascii=False) for eid in exp_ids]
            lines.append("| " + " | ".join(_escape_md(c) for c in cfg_row) + " |")
        lines.append("")

    section_num = 5 if analysis.config_diffs else 4
    lines.append(f"## {section_num}. 分析结论")
    lines.append("")
    for conclusion in analysis.conclusions:
        lines.append(f"- {conclusion}")
    lines.append("")

    return "\n".join(lines)


def export_summary_csv(analysis: AnalysisResult, output_path: str | Path) -> Path:
    """Export unified experiment records into a flat CSV summary file, preserving full numeric precision."""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    metrics_cols = list(analysis.comparability.all_metrics)
    fieldnames = [
        "experiment_id", "model", "dataset", "task", "split",
        *[f"metric.{m}" for m in metrics_cols],
        "config", "source",
    ]
    with target.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for rec in analysis.records:
            normalized_map = {k.strip(): v for k, v in rec.metrics.items()}
            row = {
                "experiment_id": rec.experiment_id.strip(),
                "model": rec.model.strip(),
                "dataset": rec.dataset.strip(),
                "task": rec.task.strip(),
                "split": rec.split.strip(),
                "config": json.dumps(rec.config, ensure_ascii=False, sort_keys=True),
                "source": rec.source.strip(),
            }
            for m in metrics_cols:
                # Use str(val) or repr(val) to preserve round-trip floating point precision
                row[f"metric.{m}"] = str(normalized_map[m]) if m in normalized_map else ""
            writer.writerow(row)
    return target


def generate_html_report(
    analysis: AnalysisResult,
    *,
    title: str = "ExperimentLens 实验结果统一分析报告",
) -> str:
    """Generate a self-contained static HTML report with tables, conclusions, and SVG bar charts."""
    comp = analysis.comparability
    metrics_cols = list(comp.all_metrics)
    esc = html.escape

    rows_html = []
    for rec in analysis.records:
        normalized_map = {k.strip(): v for k, v in rec.metrics.items()}
        metric_tds = "".join(
            f"<td>{esc(_format_num(normalized_map[m])) if m in normalized_map else 'N/A'}</td>"
            for m in metrics_cols
        )
        cfg_str = json.dumps(rec.config, ensure_ascii=False, sort_keys=True) if rec.config else "{}"
        rows_html.append(
            "<tr>"
            f"<td>{esc(rec.experiment_id.strip())}</td>"
            f"<td>{esc(rec.model.strip())}</td>"
            f"<td>{esc(rec.dataset.strip())}</td>"
            f"<td>{esc(rec.task.strip())}</td>"
            f"<td>{esc(rec.split.strip())}</td>"
            f"{metric_tds}"
            f"<td><code>{esc(cfg_str)}</code></td>"
            f"<td>{esc(rec.source.strip())}</td>"
            "</tr>"
        )

    charts_html = []
    if comp.is_comparable and analysis.metric_summaries:
        for m_name, summary in analysis.metric_summaries.items():
            scale = max(abs(summary.max_value), 1e-9)
            bars = []
            for rec in analysis.records:
                val = {k.strip(): v for k, v in rec.metrics.items()}[m_name]
                width_pct = max(2.0, min(100.0, (max(val, 0.0) / scale) * 100.0))
                is_best = rec.experiment_id.strip() == summary.best_experiment_id
                color = "#1f7a8c" if is_best else "#6c757d"
                bars.append(
                    f"<div style='margin:6px 0;'>"
                    f"<span style='display:inline-block;width:110px;font-weight:bold;'>{esc(rec.experiment_id.strip())}</span>"
                    f"<div style='display:inline-block;width:60%;background:#e9ecef;border-radius:4px;vertical-align:middle;'>"
                    f"<div style='width:{width_pct:.1f}%;background:{color};height:18px;border-radius:4px;'></div>"
                    f"</div>"
                    f"<span style='margin-left:8px;'>{esc(_format_num(val))}</span>"
                    f"</div>"
                )
            charts_html.append(
                f"<div style='margin-bottom:18px;padding:12px;border:1px solid #dee2e6;border-radius:6px;'>"
                f"<h4>指标图表：{esc(m_name)}（最优：{esc(summary.best_experiment_id)} = {esc(_format_num(summary.best_value))}）</h4>"
                f"{''.join(bars)}"
                f"</div>"
            )

    conclusions_li = "".join(f"<li>{esc(c)}</li>" for c in analysis.conclusions)
    metric_headers = "".join(f"<th>{esc(m)}</th>" for m in metrics_cols)
    status_badge = "可比较 (Comparable)" if comp.is_comparable else f"不可直接比较 ({'; '.join(comp.reasons)})"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{esc(title)}</title>
<style>
body {{ font-family: system-ui, -apple-system, sans-serif; margin: 24px; color: #212529; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
th, td {{ border: 1px solid #ced4da; padding: 8px 10px; text-align: left; }}
th {{ background: #f8f9fa; }}
</style>
</head>
<body>
<h1>{esc(title)}</h1>
<p><strong>可比性状态：</strong>{esc(status_badge)}</p>
<h2>实验结果汇总表</h2>
<table>
<thead><tr><th>Experiment ID</th><th>Model</th><th>Dataset</th><th>Task</th><th>Split</th>{metric_headers}<th>Config</th><th>Source</th></tr></thead>
<tbody>{''.join(rows_html)}</tbody>
</table>
<h2>指标可视化与对比</h2>
{''.join(charts_html) if charts_html else '<p>不可直接比较，已省略图表。</p>'}
<h2>分析结论</h2>
<ul>{conclusions_li}</ul>
</body>
</html>
"""
