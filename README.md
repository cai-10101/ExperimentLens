# ExperimentLens

成员 A 的核心数据层：统一实验记录、CSV 读取，以及可独立安装的连接器接口与发现机制。指标分析、报告和 CLI 由成员 C 开发；独立 JSON 连接器由成员 B 开发。

## 运行

需要 Python 3.10 或更新版本。开发时可在仓库根目录执行：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -c 'from experimentlens import load_experiments; print(load_experiments(["examples/experiments"]))'
```

也可以通过 `python3 -m pip install -e .` 安装核心包。安装后直接 `from experimentlens import ExperimentRecord, ExperimentConnector, load_experiments`。

独立插件安装验证使用 `tests/fixtures/probe_connector/` 中的最小测试包；在虚拟环境依次安装核心包和该包后，运行 `python tests/integration_smoke.py`。GitHub Actions 会对 Python 3.10 和 3.12 自动执行此验证、核心单元测试、语法检查及依赖检查。

## CSV 格式

每行是一条实验记录。必填列：`experiment_id,model,dataset,task,split`；至少有一列 `metric.<名称>`，如 `metric.f1`。可选 `config` 列是 JSON 对象。文件须为 UTF-8，可含 BOM。`source` 由读取器自动填入文件路径，不需 CSV 列。参见 `examples/experiments/`。

`load_experiments(["文件.csv", "目录"])` 会按输入顺序导入，目录递归扫描并按路径排序。目录中的无关文件被忽略；CSV 或 JSON 缺少可用连接器时会报错，避免悄悄漏掉实验。显式指定未知格式也会报错。任一受支持文件无效时，调用整体失败，不返回部分结果。

连接器协议、异常和插件安装方式详见 [核心设计说明](docs/CORE_DESIGN.md)。
