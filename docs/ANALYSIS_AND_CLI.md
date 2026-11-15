# 实验分析、报告与 CLI 模块设计（成员 C）

## 数据流与模块职责

成员 C 负责消费成员 A 导出的统一 `ExperimentRecord` 列表，完成可比性检查、指标对比计算、多格式报告导出以及 CLI 命令行入口：

`list[ExperimentRecord] → analyze_experiments() → AnalysisResult → generate_report() / export_summary_csv() / generate_html_report()`

分析与报告层完全面向 `ExperimentRecord` 编程，不关心底层数据来自内置 CSV 连接器还是独立安装的 JSON 连接器。

## 指标分析接口（`experimentlens.analyzer`）

```python
analyze_experiments(
    records: list[ExperimentRecord],
    *,
    sort_by: str | None = None,
    metric_directions: dict[str, str] | None = None,
    strict_comparability: bool = False,
    filter_dataset: str | None = None,
    filter_model: str | None = None,
    filter_ids: set[str] | list[str] | None = None,
) -> AnalysisResult
```

### 1. 筛选与重复检查
- 对输入 `records` 校验非空且元素均为 `ExperimentRecord`，并校验 `experiment_id` 唯一性；重复时抛出 `DataValidationError`。
- 支持按 `filter_dataset`、`filter_model`、`filter_ids` 筛选目标子集；筛选结果为空时抛出 `DataValidationError`。

### 2. 可比性检查（`ComparabilityReport`）
- 检查筛选后记录的 `dataset`、`task`、`split` 是否唯一一致，以及是否存在所有实验共有的指标（`common_metrics`）。
- 任一项不一致则标记 `is_comparable = False`，并将具体原因写入 `reasons`；若存在部分实验缺失某些指标，将其记入 `warnings`。
- 当 `strict_comparability=True` 且不可比较时，直接抛出 `DataValidationError`；默认模式下保留原始汇总记录并跳过跨实验排名与优劣结论，避免输出误导性比较。

### 3. 优化方向与统计计算（`MetricSummary`）
- 通过 `resolve_metric_direction(metric, overrides)` 确定优化方向：
  - 默认 `loss`、`val_loss`、`test_loss`、`error`、`error_rate`、`mae`、`mse`、`rmse`、`perplexity`、`ppl`、`wer`、`cer`、`latency`、`runtime` 以及以 `_loss` / `_error` 结尾的指标为 `lower`（越小越好）；其余默认为 `higher`（越大越好）。
  - 支持通过 `metric_directions`（或 CLI `--direction METRIC=higher|lower`）显式覆盖，非法方向抛出 `DataValidationError`。
- 当 `is_comparable = True` 时，为每个共有指标计算 `max_value`/`max_experiment_id`、`min_value`/`min_experiment_id`、`spread`（`max - min`）、`best_experiment_id`/`best_value`、`worst_experiment_id`/`worst_value`、`delta` 与 `ranking`。
- 支持按共有指标 `sort_by` 排序（若 `sort_by` 不存在或非共有指标，抛出 `DataValidationError`），并提取跨实验不一致的 `config` 字段生成 `config_diffs`。

## 报告导出接口（`experimentlens.reporter`）

- `generate_report(analysis: AnalysisResult, *, title: str = ...) -> str`：生成包含可比性概览、实验结果汇总表（含 `Config` 与 `Source` 来源路径）、指标统计与比较表、配置差异表与文字结论的 Markdown 报告。
- `export_summary_csv(analysis: AnalysisResult, output_path: str | Path) -> Path`：导出与内置 CSV 格式兼容的标准化汇总 CSV，导出的文件可再次被 `load_experiments()` 导入核验。
- `generate_html_report(analysis: AnalysisResult, *, title: str = ...) -> str`：零外部依赖生成包含汇总表、内联对比柱状图与结论的静态 HTML 报告。

## CLI 命令行入口（`experimentlens.cli`）

安装后可直接运行 `experimentlens`，开发时可通过 `python -m experimentlens` 调用。

### 常用参数
- `paths`（必填，可多个）：待导入的实验文件或目录。
- `-o / --output`：Markdown 报告输出路径（省略时打印至标准输出）。
- `--csv-output`：导出标准化 CSV 汇总文件路径。
- `--html-output`：导出静态 HTML 报告文件路径。
- `--sort-by METRIC`：按指定共有指标排序。
- `--direction METRIC=DIR`：覆盖指标优化方向（`higher` / `lower`，可重复传入）。
- `--disable-connector NAME`：禁用指定连接器（如 `--disable-connector json`，可重复传入）。
- `--filter-dataset` / `--filter-model` / `--filter-id`：按数据集、模型或实验 ID 筛选。
- `--strict-comparability`：遇到不可比较实验时报错退出，不生成折衷汇总。
- `--title`：自定义报告标题。

### 退出码约定
- `0`：导入、分析与报告生成成功。
- `2`：输入路径错误（`InputError`）、数据或参数校验失败（`DataValidationError`）、严格模式可比性校验失败或输出文件写入失败（`OSError`）。
- `3`：连接器相关错误（`ConnectorError` 及其子类，包括插件未找到 `ConnectorNotFoundError`、注册失败或执行异常）。
