# 核心数据层设计与 B、C 接口约定

## 数据流与边界

`路径 → 注册表选择连接器 → load(source) → list[ExperimentRecord] → C 的分析模块`。A 负责模型、CSV、注册与调度；B 独立发布 JSON 连接器；C 实现可比性判断、指标分析、CLI 和报告。导入层只校验单条记录的数据合法性，不判断不同实验是否可比较。

## 公共数据模型

从 `experimentlens` 导入 `ExperimentRecord`。字段为 `experiment_id: str`、`model: str`、`dataset: str`、`task: str`、`split: str`、`metrics: dict[str, float]`、`config: dict[str, Any]`、`source: str`。前五项及 `source` 必须是非空字符串；`metrics` 至少有一个名称非空的有限数值指标；`config` 是对象，缺省为空对象。连接器创建记录时负责填写实际来源路径。指标是否同名、含义一致及优化方向由 C 确定。

## Connector 契约（交给 B）

公开协议 `ExperimentConnector` 有 `name: str`、`extensions: tuple[str, ...]` 和 `load(source: str) -> list[ExperimentRecord]`。扩展名须为带点号的小写字符串，例如 `(".json",)`；`name` 须与包入口点名称相同。`load` 必须返回非空记录列表；遇到无效数据应抛 `DataValidationError`，不可读取的文件抛 `InputError`。不要让解析失败变成空列表或伪造记录。B 的包只依赖 `experimentlens` 公共导出。

独立包在自己的 `pyproject.toml` 中声明：

```toml
[project.entry-points."experimentlens.connectors"]
json = "b_package.connector:JsonConnector"
```

其中 `JsonConnector` 是无需参数即可实例化的类，`name = "json"`、`extensions = (".json",)`。核心使用 Python 包元数据自动发现，安装插件后不需要修改核心源码。重复名称或扩展名会在注册时报错；插件加载失败会报 `ConnectorRegistrationError`。

## 导入接口（交给 C）

`load_experiments(paths: list[str], *, disabled_connectors: set[str] | None = None) -> list[ExperimentRecord]`。支持文件和递归目录；返回扁平记录列表。`disabled_connectors={"json"}` 可禁用 JSON 插件，独立 CSV 导入仍可运行。若目录包含 JSON，但 JSON 连接器缺失、禁用或损坏，整个导入会报错，以免调用方误以为拿到了完整目录结果；此时可单独指定 CSV 文件或 CSV 专用目录。核心不调用 C 的分析函数，也不输出报告。

公共异常根类是 `ExperimentLensError`。`InputError` 表示路径或文件读取失败；`DataValidationError` 表示内容无效；`ConnectorNotFoundError` 表示文件格式没有可用连接器；`ConnectorRegistrationError` 表示插件契约或发现失败；`ConnectorExecutionError` 表示插件运行异常。调用方可以捕获根类给用户友好反馈，也可以按子类区分处理。任何文件失败都会中止整次导入，避免得到不完整结果。

## 待联调确认

B 应按本契约提交独立 JSON 包及其测试；C 应确认是否还需要额外元数据、指标单位或优化方向。若需要扩展字段，应先共同修订公共契约，再开展联调。最终 JSON 安装、报告闭环与交叉 Review 需要三人协作验收。
