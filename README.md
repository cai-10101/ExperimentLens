# ExperimentLens

仓库地址：[cai-10101/ExperimentLens](https://github.com/cai-10101/ExperimentLens)。面向需要整理多轮模型实验的开发者和研究人员：选择本地实验文件或目录，系统统一导入 CSV 与可选 JSON 数据，检查可比性，计算指标排名，并输出可核对的 Markdown、CSV 或静态 HTML 报告。

## 用户场景与范围

核心包内置 CSV 读取、统一 `ExperimentRecord`、连接器发现和调度、指标分析及 CLI。独立的 `experimentlens-json` 包通过公开入口点增加嵌套 JSON 和统一 JSON 读取能力，不需要修改核心源码。未安装插件时，CSV 导入、比较和报告仍可运行。项目提供静态 HTML 报告供浏览器查看；没有交互式网页或桌面输入界面。

本次不实现真实模型训练、超参数搜索、数据库、云端实验管理、用户账户、插件市场、热加载和复杂 Web 后台。CLI 读取本地文件，不连接外部服务，也不需要 API Key。

## 快速开始

以下 macOS/Linux 命令均在仓库根目录执行，需要 Python 3.10 或更新版本：

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
mkdir -p /tmp/experimentlens-demo
experimentlens examples/experiments --sort-by f1 \
  -o /tmp/experimentlens-demo/csv-report.md \
  --csv-output /tmp/experimentlens-demo/csv-summary.csv \
  --html-output /tmp/experimentlens-demo/csv-report.html
```

Windows PowerShell 的环境激活命令为 `.venv\Scripts\Activate.ps1`；其余命令中的 `python3.10` 可换为 `py -3.10`，报告路径可换成本机目录。两份内置 CSV 的 `f1` 分别为 `exp_001=0.77`、`exp_002=0.81`，报告应将 `exp_002` 排在前面。浏览器打开生成的 HTML 文件即可查看表格、柱状图与结论。开发时也可用 `PYTHONPATH=src python3.10 -m experimentlens examples/experiments --sort-by f1`，此方式不安装包。

### 接入独立 JSON 扩展

在同一个虚拟环境中执行：

```bash
python -m pip install -e plugins/json_connector
experimentlens examples/experiments plugins/json_connector/examples/nested.json \
  --sort-by f1 --strict-comparability \
  -o /tmp/experimentlens-demo/mixed-report.md \
  --csv-output /tmp/experimentlens-demo/mixed-summary.csv \
  --html-output /tmp/experimentlens-demo/mixed-report.html
```

混合报告应有三条记录，`f1` 排名为 `exp_003=0.86 > exp_002=0.81 > exp_001=0.77`，最高与最低相差 `0.09`。安装插件前后无需改动 `src/experimentlens/`；CLI 每次运行都会重新发现已安装的入口点。对于长期运行的 Python 进程，安装或卸载插件后应重启进程。禁用 JSON 时仍可明确指定 CSV 文件：

```bash
experimentlens examples/experiments/exp_001/metrics.csv \
  examples/experiments/exp_002/metrics.csv --disable-connector json
```

禁用后若仍输入 JSON 文件或包含 JSON 的目录，会得到连接器缺失错误，而不会静默遗漏记录。插件自身可独立构建：先执行 `python -m pip install build`，再执行 `python -m build plugins/json_connector`；核心包可用 `python -m build .` 构建。发行物的实际安装命令和摘要记录在最终提交 ZIP 的 `release/RELEASE.md`。

## 输入格式与错误反馈

CSV 每行是一条实验记录，必填列为 `experiment_id,model,dataset,task,split`，另需至少一列 `metric.<名称>`；可选 `config` 列是 JSON 对象。JSON 插件支持单条对象、非空数组和 `experiments` 数组包装对象。嵌套格式将 `run_id` 映射到 `experiment_id`、`model_info.name` 映射到 `model`、`results.f1_score` 映射到 `metrics.f1`。UTF-8 与 UTF-8 BOM 均可，`source` 由读取器填写。目录递归扫描，支持格式的文件一旦无效就终止整次导入，不返回部分结果。

输入路径、内容或严格可比性失败时 CLI 退出码为 `2`；连接器缺失、注册或执行失败时为 `3`；成功时为 `0`。错误写入标准错误流，包含类型及适用的路径、行列或记录序号。CLI 会阻止报告输出覆盖实际导入文件，包括符号链接和硬链接指向的同一文件。更多参数及边界见[分析与 CLI 说明](docs/ANALYSIS_AND_CLI.md)。

## 构建、测试与质量检查

以下顺序可重复验证插件安装前后的差异。测试在仓库根目录执行，先运行核心测试，再安装 JSON 插件：

```bash
python -m pip install -e tests/fixtures/probe_connector
python -m compileall -q src tests plugins/json_connector/src plugins/json_connector/tests
python -m unittest discover -s tests -p 'test_*.py' -v
python tests/integration_smoke.py
python plugins/json_connector/tests/installation_smoke.py absent
python -m pip install -e plugins/json_connector
python -m unittest discover -s plugins/json_connector/tests -v
python plugins/json_connector/tests/installation_smoke.py installed
python -m pip check
```

核心测试断言模型与 CSV 校验、插件注册/禁用/失败、可比性、排名、报告和 CLI 输出保护；JSON 契约测试断言多种输入结构、字段映射、无效数据、别名冲突和入口点接入。`tests/integration_smoke.py` 验证独立测试插件安装后可发现、禁用及 CSV 回退。`compileall` 是语法检查，`pip check` 是依赖一致性检查。CI 位于 [Core checks](.github/workflows/core.yml) 和 [JSON connector](.github/workflows/json-connector.yml)，在 Python 3.10、3.12 构建与测试；[核心成功记录](https://github.com/cai-10101/ExperimentLens/actions/runs/44216230179)和[插件成功记录](https://github.com/cai-10101/ExperimentLens/actions/runs/44216230195)均来自已合并的主线提交 `2c59823`。

测试敏感性示例：运行 `python scripts/test_sensitivity.py`。脚本只在临时副本中把有限数值检查改错，确认 `test_record_validation` 失败；随后恢复代码，确认同一测试通过。脚本不会修改当前工作区，也不需要提交故障日志。

## 扩展契约与设计

`ExperimentConnector` 公开 `name`、带点号的小写 `extensions` 和 `load(source: str) -> list[ExperimentRecord]`。独立包通过 `experimentlens.connectors` 入口点注册；`load` 返回非空的统一记录列表，并按约定抛出输入、数据或插件错误。核心仅调用公开接口，不导入 JSON 包的内部代码。接口兼容范围当前为核心 `0.1.x` 与插件 `0.1.x`；变更公共字段或异常约定时先更新契约、连接器和测试，再决定是否提升版本。详情见[系统设计文档](docs/DESIGN.docx)、[核心设计说明](docs/CORE_DESIGN.md)与[JSON 连接器设计说明](docs/JSON_CONNECTOR.md)。

## 协作与贡献

发现问题可在 GitHub Issue 或 PR 中描述输入、实际结果、预期结果和复现方法。常规改动从独立分支提交 PR，由另一位成员检查程序行为、边界与测试；作者修订或有依据地回应，审查人复核新提交后由有写入权限的成员合并。代表性记录：[A 的 PR #1](https://github.com/cai-10101/ExperimentLens/pull/1)由 C 提出核心错误处理意见并在修订后批准；[C 的 PR #2](https://github.com/cai-10101/ExperimentLens/pull/2)由 B 提出输出覆盖、浮点精度等问题并在修订后于 PR 评论给出批准结论；[B 的 PR #3](https://github.com/cai-10101/ExperimentLens/pull/3)由 A 指出指标别名归一化问题，B 修复后 A 再次复核并批准。发布材料的直接提交由项目成员明确决定，不改变上述已有审查记录。

### 成员贡献与 AI 核验

| 成员账号 | 本人实质改动 | 审查他人的改动及结果 | 关键建议、采用情况与本人验证 |
| --- | --- | --- | --- |
| A：`muer298` | [PR #1](https://github.com/cai-10101/ExperimentLens/pull/1)：统一模型、CSV、插件注册与导入测试 | [PR #3](https://github.com/cai-10101/ExperimentLens/pull/3)：提出 JSON 别名边界并复核修复 | Codex 辅助发现先映射后去空白造成 `f1` 不一致；采用该测试输入，在修订前复现失败、修订后验证映射、冲突报错与混合报告。 |
| B：`Megabytes-MB` | [PR #3](https://github.com/cai-10101/ExperimentLens/pull/3)：独立 JSON 包与契约测试 | [PR #2](https://github.com/cai-10101/ExperimentLens/pull/2)：提出输出保护与精度问题，复核新提交后在评论中批准 | 使用 Codex 辅助实现 JSON 插件、编写契约测试，并复现 C 模块的输出覆盖、CSV 精度丢失及极小差值误判问题；本人核对审查意见与修订结果，在 PR #2 留下具体意见及最终复核结论。采纳 A 在 PR #3 提出的别名归一化意见，将处理顺序修正为先去空白、再映射 `f1_score → f1`、最后检查重名，提交 `8d6a43c` 并回复处理依据；新增 3 项回归测试，修复前失败、修复后通过。Codex 辅助执行的主线 26 项测试、插件 26 项测试、wheel 安装、入口点发现及跨文件严格比较通过，Python 3.10 / 3.12 CI 通过，修订经 A 复核批准。 |
| C：蔡昕升 / 2024312111466（`cai-10101`） | [PR #2](https://github.com/cai-10101/ExperimentLens/pull/2)：分析、报告、CLI 与测试 | [PR #1](https://github.com/cai-10101/ExperimentLens/pull/1)：提出核心异常与接口意见，复核后批准 | AI 辅助编写分析与导出初版时建议对 `spread` 做 10 位四舍五入并对 CSV 指标格式化截断；结合 PR #2 审查复现了极小非零差值误判“无差异”与精度丢失问题，拒绝该舍入方案，改为精确差值与完整浮点导出，并通过 `test_tiny_non_zero_spread_not_misjudged_as_no_difference` 和 `test_csv_export_preserves_high_precision` 验证往返精度与结论一致。 |

## 许可与已知限制

项目采用 [MIT 许可证](LICENSE)：规则简明，允许使用、修改和再分发，但分发时需保留版权及许可声明。独立 JSON 包也包含同一许可文本。运行时只使用 Python 标准库；`setuptools` 是构建依赖，`build` 仅用于手动构建，CI 使用 GitHub 官方 Actions。本项目不打包第三方源码。三位贡献者应在最终发布前确认共同采用此许可。

已知限制：`f1_score` 仅在 JSON 嵌套 `results` 中映射为 `f1`；其他指标名称与优化方向须由使用者约定，常见损失指标默认越低越好，其余默认越高越好；不同数据集、任务或划分不会得到跨实验结论。HTML 是本地静态报告，不能在页面内导入数据。当前无数据库、服务端 API 或远程数据源。
