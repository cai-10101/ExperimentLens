# ExperimentLens JSON Connector

成员 B 的独立插件包，提供 JSON 读取、标准化、异常处理和公共契约测试。通过 `experimentlens.connectors` 入口点接入，仅导入 `experimentlens` 的公共导出。

## 依赖与当前联调基线

需要 Python 3.10+，依赖 `experimentlens>=0.1,<0.2`。当前 `main` 尚无核心实现，联调使用 A 的 PR #1 提交 `4b7b5b8c25e7f1faab30b0d10c9e7f4b6c4f7a35`。CI 固定该提交以便复现插件契约测试。B 分支从 `main` 创建，只提交插件及其 CI。PR #1 合并后才具备完整主线运行条件，后续公共契约变化需重新联调。

## JSON 格式与映射

支持三种顶层结构。单条实验对象、非空实验对象数组，以及只含 `experiments` 非空数组的包装对象。数组允许混用以下两类记录，保持输入顺序。

| 嵌套记录字段 | 统一字段 | 规则 |
| --- | --- | --- |
| `run_id` | `experiment_id` | 必填非空字符串 |
| `model_info.name` | `model` | 必填非空字符串 |
| `dataset`、`task`、`split` | 同名字段 | 必填非空字符串 |
| `results.f1_score` | `metrics.f1` | 有限数值 |
| `results` 中其他键 | `metrics` 中同名键 | 有限数值，至少一个指标 |
| `config` | `config` | JSON 对象，缺省 `{}` |
| 实际文件路径 | `source` | 由插件填写 |

统一记录直接使用 `experiment_id`、`model`、`dataset`、`task`、`split`、`metrics` 和可选 `config`。示例见 [嵌套记录](examples/nested.json) 与 [统一记录包装](examples/unified.json)。

记录出现 `run_id`、`model_info` 或 `results` 任一字段时采用嵌套格式，同时出现统一格式的 `experiment_id`、`model`、`metrics` 将报错。`results.f1_score` 与 `results.f1` 同时出现也报错，以避免覆盖指标。除上述冲突字段外，额外记录字段忽略。`results` 内每个键均作为指标，因此耗时、备注等非指标元数据应放入 `config`。

标识和指标名的首尾空白由公共模型归一化，归一化后指标重名报错。指标允许零和负数，具体指标的取值区间及可比性由下游约定。布尔值、数值字符串、`null`、非有限数值和不可转换为有限浮点数的整数均报错。文件使用 UTF-8，可含 BOM，重复 JSON 对象键在任意层级均报错。

## 异常与导入边界

- 不存在、无权限及目录路径等读取失败抛出公共 `InputError`。
- JSON 语法、编码、结构、字段或指标错误抛出公共 `DataValidationError`。语法错误包含文件、行和列，记录校验错误包含文件和从 1 开始的记录序号。
- 任一记录失败会使整次 `load` 失败。跨文件和同一文件的实验 ID 唯一性由核心 `load_experiments` 检查。
- 禁用或卸载插件后，明确指定 CSV 文件仍可导入。含 JSON 的混合目录会因缺少连接器报错，应按需选择 CSV 文件或 CSV 专用目录。

## 构建、安装和测试

以下命令在仓库根目录执行，环境中需先安装核心包。Windows 可使用 `py -3` 代替 `python`。建议先创建并激活独立虚拟环境。

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install build
# PR #1 合并前，从其固定提交安装核心依赖
python -m pip install "experimentlens @ git+https://github.com/cai-10101/ExperimentLens.git@4b7b5b8c25e7f1faab30b0d10c9e7f4b6c4f7a35"
# PR #1 合并后，也可在含核心实现的主线中执行 python -m pip install .
python plugins/json_connector/tests/installation_smoke.py absent
python -m build plugins/json_connector
python -m pip install plugins/json_connector/dist/experimentlens_json-0.1.0-py3-none-any.whl
python -m unittest discover -s plugins/json_connector/tests -v
python plugins/json_connector/tests/installation_smoke.py installed
python -m pip check
```

开发时可以 `python -m pip install -e plugins/json_connector` 替代 wheel 安装。正式接入验收应执行 wheel 安装流程，验证实际包元数据发现。

```python
from experimentlens import load_experiments

records = load_experiments(["plugins/json_connector/examples/nested.json"])
print(records[0].experiment_id, records[0].metrics)
# exp_003 {'precision': 0.9, 'recall': 0.82, 'f1': 0.86}

csv_records = load_experiments(
    ["examples/experiments/exp_001/metrics.csv"],
    disabled_connectors={"json"},
)
```

卸载后验证 CSV 基础能力和 JSON 连接器缺失行为。

```powershell
python -m pip uninstall -y experimentlens-json
python plugins/json_connector/tests/installation_smoke.py absent
python -m pip check
```

CI 在 Python 3.10 / 3.12 上独立构建 wheel 和 sdist，并依次验证未安装、安装、禁用和卸载场景。A 的核心测试在插件未安装时执行，其中两项测试以 JSON 连接器缺失为前提。测试中的无权限异常使用模拟，文件不存在与目录读取使用真实文件系统。CI 的远程执行结果以 GitHub Actions 实际记录为准。

## 交叉审查

B 的 PR 由 A 实际审查，重点为字段映射冲突、错误类型及定位、独立 wheel 的入口点发现和禁用后 CSV 行为。作者根据实际意见在同一 B 分支追加提交或给出依据，A 复核后再合并。B 对 C 的审查应检查真实提交中的指标计算、结论和边界行为，意见与复核由 B 本人确认并发布。
