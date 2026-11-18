# ExperimentLens

面向多轮实验管理与结果对比的可扩展分析工具：成员 A 负责核心数据层（统一实验记录、CSV 读取、连接器接口与发现机制）；成员 B 负责独立安装的 JSON 连接器；成员 C 负责实验可比性检查、指标分析、报告导出与 CLI。

## 运行

需要 Python 3.10 或更新版本。开发时可在仓库根目录执行：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -c 'from experimentlens import load_experiments; print(load_experiments(["examples/experiments"]))'
PYTHONPATH=src python3 -m experimentlens examples/experiments --sort-by f1
```

也可以通过 `python3 -m pip install -e .` 安装核心包。安装后可直接导入公共 API 或使用 `experimentlens` 命令：

```bash
experimentlens examples/experiments --sort-by f1 -o report.md
experimentlens examples/experiments --sort-by f1 --csv-output summary.csv --html-output report.html
```

禁用连接器示例（如禁用可选 JSON 插件，仅处理明确指定的 CSV 文件）：

```bash
experimentlens examples/experiments/exp_001/metrics.csv examples/experiments/exp_002/metrics.csv --disable-connector json
```

独立插件安装验证使用 `tests/fixtures/probe_connector/` 中的最小测试包；在虚拟环境依次安装核心包和该包后，运行 `python tests/integration_smoke.py`。GitHub Actions 会对 Python 3.10 和 3.12 自动执行此验证、核心与分析单元测试、CLI 验证、语法检查及依赖检查。

## CSV 格式

每行是一条实验记录。必填列：`experiment_id,model,dataset,task,split`；至少有一列 `metric.<名称>`，如 `metric.f1`。可选 `config` 列是 JSON 对象。文件须为 UTF-8，可含 BOM。`source` 由读取器自动填入文件路径，不需 CSV 列。参见 `examples/experiments/`。

`load_experiments(["文件.csv", "目录"])` 会按输入顺序导入，目录递归扫描并按路径排序。目录中的无关文件被忽略；CSV 或 JSON 缺少可用连接器时会报错，避免悄悄漏掉实验。显式指定未知格式也会报错。任一受支持文件无效时，调用整体失败，不返回部分结果。

## JSON 连接器（成员 B）

项目提供 `experimentlens-json` 独立插件包，支持嵌套 JSON 与统一记录 JSON，转换为核心公共类型 `ExperimentRecord`，并通过 `experimentlens.connectors` 包入口点自动注册。

| 路径 | 内容 |
| --- | --- |
| `plugins/json_connector/src/experimentlens_json/` | JSON 解析、字段映射和错误定位 |
| `plugins/json_connector/examples/` | 嵌套记录与统一记录示例 |
| `plugins/json_connector/tests/` | 公共契约测试与安装、卸载验证 |
| `.github/workflows/json-connector.yml` | Python 3.10 / 3.12 构建及插件集成验证 |

### 插件安装与验证

在仓库根目录执行以下 PowerShell 命令，创建独立环境并安装当前 checkout 的核心包和 JSON 插件。

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m pip install -e plugins/json_connector
python -m unittest discover -s plugins/json_connector/tests -v
python plugins/json_connector/tests/installation_smoke.py installed
python -m pip check
```

插件 CI 仍固定 A 的公共接口基线进行复现。wheel 构建、安装及卸载验证流程见插件使用说明。核心测试包含插件缺失场景，应在安装 JSON 插件前运行核心测试，或使用独立虚拟环境。

```python
from experimentlens import load_experiments

records = load_experiments(["plugins/json_connector/examples/nested.json"])
print(records[0].experiment_id, records[0].metrics)
# exp_003 {'precision': 0.9, 'recall': 0.82, 'f1': 0.86}
```

## 文档

- [核心设计说明](docs/CORE_DESIGN.md)包含统一模型、连接器契约、异常体系和导入规则。
- [分析与 CLI 说明](docs/ANALYSIS_AND_CLI.md)包含可比性规则、指标分析、报告导出和 CLI 参数。
- [JSON 插件使用说明](plugins/json_connector/README.md)包含格式映射、异常约定、构建与卸载步骤。
- [JSON 连接器设计与联调说明](docs/JSON_CONNECTOR.md)包含公共接口、模块职责、测试覆盖和 A、C 对接方式。
