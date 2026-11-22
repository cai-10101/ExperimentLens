# JSON 连接器设计与联调说明（成员 B）

## 数据流与模块职责

`JSON 文件 → JsonConnector.load(source) → JSON 结构识别 → 字段映射 → ExperimentRecord 校验 → list[ExperimentRecord]`

A 的 `load_experiments` 通过注册表选择连接器，负责递归目录遍历与实验 ID 唯一性检查。B 负责 JSON 文件读取、结构识别、字段映射和解析错误定位。C 消费统一记录，负责可比性检查、指标优化方向、分析与报告。

## 公共接口与独立包

插件发布名为 `experimentlens-json`，版本为 `0.1.0`，需要 Python 3.10+ 与 `experimentlens>=0.1,<0.2`。公开类为 `experimentlens_json.JsonConnector`，可无参数实例化。

```python
class JsonConnector:
    name = "json"
    extensions = (".json",)

    def load(self, source: str) -> list[ExperimentRecord]:
        ...
```

包元数据声明如下，安装后的核心通过入口点发现插件。

```toml
[project.entry-points."experimentlens.connectors"]
json = "experimentlens_json:JsonConnector"
```

实现从 `experimentlens` 公共导出中使用 `ExperimentRecord`、`InputError` 和 `DataValidationError`。完整构建与安装步骤见[插件使用说明](../plugins/json_connector/README.md)。

## 输入结构与映射规则

支持单个记录对象、非空记录数组，以及仅含 `experiments` 非空数组的包装对象。数组保持输入顺序，允许包含嵌套记录和统一记录。

| 嵌套字段 | 统一字段 |
| --- | --- |
| `run_id` | `experiment_id` |
| `model_info.name` | `model` |
| `dataset`、`task`、`split` | 同名字段 |
| `results.f1_score` | `metrics.f1` |
| `results` 中其他键 | `metrics` 中同名键 |
| 可选 `config` | `config`，缺省 `{}` |
| 实际输入路径 | `source` |

统一记录直接提供 `experiment_id`、`model`、`dataset`、`task`、`split`、`metrics` 和可选 `config`。出现 `run_id`、`model_info` 或 `results` 任一字段时进入嵌套映射，混入 `experiment_id`、`model` 或 `metrics` 会报错。`f1_score` 与 `f1` 同时出现会报错。

必填标识为非空字符串，指标至少一个且值为有限数值，`config` 必须为对象。嵌套记录的 `results` 指标名先去除首尾空白，再将 `f1_score` 映射为 `f1`，映射后重名抛出 `DataValidationError`。因此 `" f1_score "` 同样映射为 `f1`，与 `f1_score` 或 `f1` 同时出现均报错。公共模型继续执行标识及指标合法性检查与浮点数转换。记录中的额外字段忽略，`results` 内所有键均按指标处理。指标范围、语义和优化方向由下游约定。

## 错误与失败边界

- 文件以 UTF-8 读取，支持 BOM。路径不存在、目录读取或权限等文件系统错误转换为 `InputError`。
- 编码、JSON 语法、结构、字段或指标校验失败转换为 `DataValidationError`。语法错误包含路径、行和列，记录校验错误包含路径和从 1 开始的记录序号。
- 任意层级的重复 JSON 对象键、非标准 `NaN` / `Infinity` 常量和超出解析器限制的内容会报错。
- 任一记录失败会使本次 `load` 抛出异常。核心负责在完整导入范围内检查重复实验 ID。
- 通过 `disabled_connectors={"json"}` 禁用后，显式 CSV 文件仍可导入。含 JSON 的目录会触发核心的连接器缺失错误。

## 测试与验收方式

`tests/test_connector.py` 当前包含 26 个测试方法，覆盖字段映射、三种顶层结构、顺序、缺失字段、非法指标、映射冲突、编码、重复键、解析限制、错误定位、入口点发现、混合目录、禁用后 CSV 导入及重复 ID 检查。新增回归测试验证带空白别名的映射、两步归一化后的重名拒绝（含键顺序反转），以及跨文件指标名一致性。

`tests/installation_smoke.py` 在 `absent` 与 `installed` 两种模式下检查实际包元数据发现和 CSV 导入，安装模式额外验证 JSON 示例。CI 在 Python 3.10 / 3.12 上构建核心及插件分发包，依次执行插件安装前检查、wheel 安装后的契约测试及禁用场景、卸载后检查和依赖检查。权限异常测试使用模拟。

上述内容描述测试覆盖和验收流程。每次变更的实际通过情况以当次运行输出和 GitHub Actions 记录为准。

## A、C 联调与当前主线验证

插件 CI 从当前 checkout 分别构建核心与独立 JSON 包，先验证未安装插件时的 CSV 基础能力，再安装 JSON wheel 运行契约测试与混合 CSV / JSON 报告闭环，最后卸载插件并再次验证 CSV。这样每次主线或 PR 修改都会与对应版本的公共接口联调。C 的 `docs/ANALYSIS_AND_CLI.md` 说明 `analyze_experiments`、报告导出和 CLI 的行为。
