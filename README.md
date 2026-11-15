# ExperimentLens

面向多轮实验管理与结果对比的可扩展分析工具。成员 A 负责统一实验记录、CSV 读取和连接器发现；成员 B 负责独立安装的 JSON 连接器；成员 C 负责可比性检查、指标分析、报告导出和 CLI。

## B 分支交付内容

当前分支提供 `experimentlens-json` 独立插件包，支持嵌套 JSON 与统一记录 JSON，转换为核心公共类型 `ExperimentRecord`，并通过 `experimentlens.connectors` 包入口点自动注册。

| 路径 | 内容 |
| --- | --- |
| `plugins/json_connector/src/experimentlens_json/` | JSON 解析、字段映射和错误定位 |
| `plugins/json_connector/examples/` | 嵌套记录与统一记录示例 |
| `plugins/json_connector/tests/` | 公共契约测试与安装、卸载验证 |
| `.github/workflows/json-connector.yml` | Python 3.10 / 3.12 构建及插件集成验证 |

## 安装与运行

需要 Python 3.10 或更新版本。在仓库根目录执行以下 PowerShell 命令，创建独立环境并安装核心依赖和 B 插件。核心依赖固定为 A 的接口基线提交，与当前插件 CI 使用的版本一致。

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install "experimentlens @ git+https://github.com/cai-10101/ExperimentLens.git@4b7b5b8c25e7f1faab30b0d10c9e7f4b6c4f7a35"
python -m pip install -e plugins/json_connector
python -m unittest discover -s plugins/json_connector/tests -v
python plugins/json_connector/tests/installation_smoke.py installed
python -m pip check
```

安装核心依赖的命令需要 Git 和网络访问。合并了核心实现的主线 checkout 也支持通过 `python -m pip install .` 安装核心包。B 当前 checkout 的安装入口为 `plugins/json_connector`。

```python
from experimentlens import load_experiments

records = load_experiments(["plugins/json_connector/examples/nested.json"])
print(records[0].experiment_id, records[0].metrics)
# exp_003 {'precision': 0.9, 'recall': 0.82, 'f1': 0.86}
```

## 文档

- [JSON 插件使用说明](plugins/json_connector/README.md)包含格式映射、异常约定、构建与卸载步骤。
- [JSON 连接器设计与联调说明](docs/JSON_CONNECTOR.md)包含公共接口、模块职责、测试覆盖和 A、C 对接方式。

A 分支提供 `docs/CORE_DESIGN.md`，说明核心模型、连接器契约和导入规则。C 分支继承该文档，并新增 `docs/ANALYSIS_AND_CLI.md`，说明分析接口、报告格式和 CLI 参数。这两份文档随对应模块交付。
