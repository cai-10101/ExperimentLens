"""Experiment comparability checking, metric aggregation, and ranking analysis."""

from dataclasses import dataclass, field
from typing import Any

from .errors import DataValidationError
from .model import ExperimentRecord

LOWER_IS_BETTER_METRICS = frozenset({
    "loss", "val_loss", "test_loss", "error", "error_rate",
    "mae", "mse", "rmse", "perplexity", "ppl", "wer", "cer", "latency", "runtime",
})

DIRECTION_ALIASES = {
    "higher": "higher",
    "max": "higher",
    "maximize": "higher",
    "lower": "lower",
    "min": "lower",
    "minimize": "lower",
}


@dataclass(frozen=True)
class MetricSummary:
    metric: str
    direction: str
    max_value: float
    max_experiment_id: str
    min_value: float
    min_experiment_id: str
    spread: float
    best_experiment_id: str
    best_value: float
    worst_experiment_id: str
    worst_value: float
    delta: float
    ranking: tuple[str, ...]


@dataclass(frozen=True)
class ComparabilityReport:
    is_comparable: bool
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    dataset: str | None = None
    task: str | None = None
    split: str | None = None
    common_metrics: tuple[str, ...] = ()
    all_metrics: tuple[str, ...] = ()


@dataclass
class AnalysisResult:
    records: list[ExperimentRecord]
    comparability: ComparabilityReport
    metric_summaries: dict[str, MetricSummary] = field(default_factory=dict)
    config_diffs: dict[str, dict[str, Any]] = field(default_factory=dict)
    conclusions: list[str] = field(default_factory=list)
    sort_by: str | None = None


def resolve_metric_direction(
    metric: str,
    overrides: dict[str, str] | None = None,
) -> str:
    if overrides and metric in overrides:
        raw = str(overrides[metric]).strip().lower()
        if raw not in DIRECTION_ALIASES:
            raise DataValidationError(
                f"invalid optimization direction {overrides[metric]!r} for metric {metric!r}; "
                "expected 'higher' or 'lower'"
            )
        return DIRECTION_ALIASES[raw]
    metric_lower = metric.strip().lower()
    if metric_lower in LOWER_IS_BETTER_METRICS or metric_lower.endswith("_loss") or metric_lower.endswith("_error"):
        return "lower"
    return "higher"


def _format_num(value: float) -> str:
    formatted = f"{value:.4f}".rstrip("0").rstrip(".")
    if "." not in formatted:
        return f"{value:.2f}"
    parts = formatted.split(".")
    if len(parts[1]) < 2:
        return f"{value:.2f}"
    return formatted


def analyze_experiments(
    records: list[ExperimentRecord],
    *,
    sort_by: str | None = None,
    metric_directions: dict[str, str] | None = None,
    strict_comparability: bool = False,
    filter_dataset: str | None = None,
    filter_model: str | None = None,
    filter_ids: set[str] | list[str] | None = None,
) -> AnalysisResult:
    """Validate comparability, compute metric summaries, and rank experiments."""
    if not isinstance(records, list) or not records or any(not isinstance(r, ExperimentRecord) for r in records):
        raise DataValidationError("analyze_experiments requires a non-empty list of ExperimentRecord")

    seen_ids: dict[str, str] = {}
    for record in records:
        exp_id = record.experiment_id.strip()
        if exp_id in seen_ids:
            raise DataValidationError(
                f"duplicate experiment_id {exp_id!r} found in {record.source!r} and {seen_ids[exp_id]!r}"
            )
        seen_ids[exp_id] = record.source

    filtered = list(records)
    if filter_dataset is not None:
        target_ds = filter_dataset.strip()
        filtered = [r for r in filtered if r.dataset.strip() == target_ds]
    if filter_model is not None:
        target_model = filter_model.strip()
        filtered = [r for r in filtered if r.model.strip() == target_model]
    if filter_ids is not None:
        allowed_ids = {str(item).strip() for item in filter_ids}
        filtered = [r for r in filtered if r.experiment_id.strip() in allowed_ids]

    if not filtered:
        raise DataValidationError("no experiment records matched the specified filters")

    if metric_directions:
        for m_name in metric_directions:
            resolve_metric_direction(m_name, metric_directions)

    all_metrics_list: list[str] = []
    for record in filtered:
        for m_name in record.metrics:
            clean_m = m_name.strip()
            if clean_m not in all_metrics_list:
                all_metrics_list.append(clean_m)

    common_metrics_list = [
        m for m in all_metrics_list
        if all(m in {k.strip() for k in r.metrics} for r in filtered)
    ]

    reasons: list[str] = []
    warnings: list[str] = []

    datasets = sorted({r.dataset.strip() for r in filtered})
    tasks = sorted({r.task.strip() for r in filtered})
    splits = sorted({r.split.strip() for r in filtered})

    if len(datasets) > 1:
        reasons.append(f"dataset mismatch: {', '.join(datasets)}")
    if len(tasks) > 1:
        reasons.append(f"task mismatch: {', '.join(tasks)}")
    if len(splits) > 1:
        reasons.append(f"split mismatch: {', '.join(splits)}")
    if not common_metrics_list:
        reasons.append("no common metrics shared across all experiments")

    for m_name in all_metrics_list:
        missing = [
            r.experiment_id.strip()
            for r in filtered
            if m_name not in {k.strip() for k in r.metrics}
        ]
        if missing:
            warnings.append(f"metric {m_name!r} is missing in: {', '.join(missing)}")

    if sort_by is not None:
        clean_sort = sort_by.strip()
        if clean_sort not in all_metrics_list:
            raise DataValidationError(f"unknown sort_by metric {clean_sort!r}; available: {', '.join(all_metrics_list)}")
        if clean_sort not in common_metrics_list:
            raise DataValidationError(
                f"cannot sort by metric {clean_sort!r} because it is not present in all experiments"
            )
    else:
        clean_sort = None

    is_comparable = len(reasons) == 0
    if strict_comparability and not is_comparable:
        raise DataValidationError(f"experiments are not comparable: {'; '.join(reasons)}")

    comparability = ComparabilityReport(
        is_comparable=is_comparable,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
        dataset=datasets[0] if len(datasets) == 1 else None,
        task=tasks[0] if len(tasks) == 1 else None,
        split=splits[0] if len(splits) == 1 else None,
        common_metrics=tuple(common_metrics_list),
        all_metrics=tuple(all_metrics_list),
    )

    def _get_metric(rec: ExperimentRecord, metric_key: str) -> float:
        if metric_key in rec.metrics:
            return rec.metrics[metric_key]
        for k, v in rec.metrics.items():
            if k.strip() == metric_key:
                return v
        raise KeyError(metric_key)

    sorted_records = list(filtered)
    if clean_sort is not None and is_comparable:
        direction = resolve_metric_direction(clean_sort, metric_directions)
        if direction == "higher":
            sorted_records.sort(key=lambda r: (-_get_metric(r, clean_sort), r.experiment_id.strip()))
        else:
            sorted_records.sort(key=lambda r: (_get_metric(r, clean_sort), r.experiment_id.strip()))

    summaries: dict[str, MetricSummary] = {}
    conclusions: list[str] = []

    if is_comparable:
        for m_name in common_metrics_list:
            direction = resolve_metric_direction(m_name, metric_directions)
            asc_pairs = sorted(
                ((_get_metric(r, m_name), r.experiment_id.strip()) for r in filtered),
                key=lambda item: (item[0], item[1]),
            )
            desc_pairs = sorted(
                ((_get_metric(r, m_name), r.experiment_id.strip()) for r in filtered),
                key=lambda item: (-item[0], item[1]),
            )
            min_val, min_id = asc_pairs[0]
            max_val, max_id = desc_pairs[0]
            spread = round(max_val - min_val, 10)

            if direction == "higher":
                best_val, best_id = max_val, max_id
                worst_val, worst_id = min_val, min_id
                ranking = tuple(exp_id for _, exp_id in desc_pairs)
            else:
                best_val, best_id = min_val, min_id
                worst_val, worst_id = max_val, max_id
                ranking = tuple(exp_id for _, exp_id in asc_pairs)

            delta = round(abs(best_val - worst_val), 10)
            summaries[m_name] = MetricSummary(
                metric=m_name,
                direction=direction,
                max_value=max_val,
                max_experiment_id=max_id,
                min_value=min_val,
                min_experiment_id=min_id,
                spread=spread,
                best_experiment_id=best_id,
                best_value=best_val,
                worst_experiment_id=worst_id,
                worst_value=worst_val,
                delta=delta,
                ranking=ranking,
            )

        for m_name, summary in summaries.items():
            if len(filtered) == 1:
                conclusions.append(
                    f"单组实验 {summary.best_experiment_id}（任务={comparability.task}, "
                    f"数据集={comparability.dataset}, 划分={comparability.split}）的 "
                    f"{m_name} 为 {_format_num(summary.best_value)}。"
                )
            elif summary.spread == 0:
                conclusions.append(
                    f"在相同任务（{comparability.task}）、数据集（{comparability.dataset}）、"
                    f"评价划分（{comparability.split}）下，各实验的 {m_name} 均为 {_format_num(summary.best_value)}（无差异）。"
                )
            else:
                cmp_word = "最高" if summary.direction == "higher" else "最低（最优）"
                diff_word = "高" if summary.direction == "higher" else "低"
                conclusions.append(
                    f"在相同任务（{comparability.task}）、数据集（{comparability.dataset}）、"
                    f"评价划分（{comparability.split}）和指标定义的前提下，"
                    f"{summary.best_experiment_id} 的 {m_name} {cmp_word}（{_format_num(summary.best_value)}），"
                    f"比 {summary.worst_experiment_id}（{_format_num(summary.worst_value)}）{diff_word} {_format_num(summary.delta)}。"
                )
    else:
        conclusions.append(
            f"实验不可直接比较（原因：{'; '.join(reasons)}），仅汇总各实验原始记录，不生成跨实验优劣排名结论。"
        )

    all_config_keys: list[str] = []
    for record in filtered:
        for k in record.config:
            if k not in all_config_keys:
                all_config_keys.append(k)

    config_diffs: dict[str, dict[str, Any]] = {}
    if len(filtered) > 1:
        for k in all_config_keys:
            values_by_exp = {r.experiment_id.strip(): r.config.get(k, None) for r in filtered}
            first_val = next(iter(values_by_exp.values()))
            if any(v != first_val for v in values_by_exp.values()):
                config_diffs[k] = values_by_exp

    return AnalysisResult(
        records=sorted_records,
        comparability=comparability,
        metric_summaries=summaries,
        config_diffs=config_diffs,
        conclusions=conclusions,
        sort_by=clean_sort,
    )
