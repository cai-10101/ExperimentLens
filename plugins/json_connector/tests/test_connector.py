"""Public-contract and installed-entry-point regression tests."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experimentlens import (
    ConnectorNotFoundError,
    ConnectorRegistry,
    DataValidationError,
    ExperimentRecord,
    InputError,
    load_experiments,
)
from experimentlens_json import JsonConnector


class JsonConnectorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "results.json"
        self.nested = {
            "run_id": "exp_003", "model_info": {"name": "Model_C"},
            "dataset": "Dataset_A", "task": "classification", "split": "test",
            "results": {"f1_score": 0.86, "recall": 0.82}, "config": {"seed": 42},
        }
        self.unified = {
            "experiment_id": "exp_004", "model": "Model_D",
            "dataset": "Dataset_A", "task": "classification", "split": "test",
            "metrics": {"f1": 0.87},
        }

    def load(self, data):
        self.path.write_text(json.dumps(data), encoding="utf-8")
        return JsonConnector().load(str(self.path))

    def test_nested_mapping_and_source(self):
        record = self.load(self.nested)[0]
        self.assertIsInstance(record, ExperimentRecord)
        self.assertEqual(record.experiment_id, "exp_003")
        self.assertEqual(record.model, "Model_C")
        self.assertEqual(record.dataset, "Dataset_A")
        self.assertEqual(record.task, "classification")
        self.assertEqual(record.split, "test")
        self.assertEqual(record.metrics, {"f1": 0.86, "recall": 0.82})
        self.assertEqual(record.config, {"seed": 42})
        self.assertEqual(record.source, str(self.path))

    def test_unified_record_and_default_config(self):
        record = self.load(self.unified)[0]
        self.assertEqual(record.experiment_id, "exp_004")
        self.assertEqual(record.metrics, {"f1": 0.87})
        self.assertEqual(record.config, {})

    def test_array_and_wrapper_preserve_order(self):
        for data in ([self.nested, self.unified], {"experiments": [self.nested, self.unified]}):
            with self.subTest(data=data):
                self.assertEqual(
                    [record.experiment_id for record in self.load(data)],
                    ["exp_003", "exp_004"],
                )

    def test_missing_required_fields(self):
        for field in self.nested:
            if field == "config":
                continue
            with self.subTest(field=field):
                data = copy.deepcopy(self.nested)
                del data[field]
                with self.assertRaises(DataValidationError):
                    self.load(data)
        for field in ("experiment_id", "model", "dataset", "task", "split", "metrics"):
            with self.subTest(field=field, shape="unified"):
                data = dict(self.unified)
                del data[field]
                with self.assertRaises(DataValidationError):
                    self.load(data)

    def test_invalid_identifiers_model_and_config(self):
        for field, value in (("run_id", " "), ("run_id", 3), ("model_info", []),
                             ("model_info", {}), ("model_info", {"name": False}),
                             ("config", None), ("config", [])):
            with self.subTest(field=field, value=value):
                data = dict(self.nested)
                data[field] = value
                with self.assertRaises(DataValidationError):
                    self.load(data)

    def test_invalid_metrics(self):
        for value in ("0.86", True, None, {}, [], float("nan"), float("inf"),
                      -float("inf"), 10 ** 400):
            with self.subTest(value=value):
                data = dict(self.nested, results={"f1_score": value})
                with self.assertRaises(DataValidationError):
                    self.load(data)
        for metrics in ({}, [], None, {" ": 0.5}, {"f1": 0.5, "f1 ": 0.6}):
            with self.subTest(metrics=metrics):
                with self.assertRaises(DataValidationError):
                    self.load(dict(self.unified, metrics=metrics))

    def test_zero_negative_and_whitespace_normalization(self):
        data = dict(self.nested, run_id=" exp_003 ", results={" loss ": -1, "f1_score": 0})
        record = self.load(data)[0]
        self.assertEqual(record.experiment_id, "exp_003")
        self.assertEqual(record.metrics, {"loss": -1.0, "f1": 0.0})

    def test_invalid_top_level_and_empty_records(self):
        for data in ([], {}, None, 1, "record", [None], {"experiments": []},
                     {"experiments": {}}, {"experiments": [self.nested], "extra": 1}):
            with self.subTest(data=data):
                with self.assertRaises(DataValidationError):
                    self.load(data)

    def test_ambiguous_mapping_is_rejected(self):
        for data in (dict(self.nested, metrics={"f1": 0.9}),
                     dict(self.nested, results={"f1": 0.9, "f1_score": 0.8}),
                     dict(self.nested, results={"f1 ": 0.9, "f1_score": 0.8})):
            with self.subTest(data=data):
                with self.assertRaises(DataValidationError):
                    self.load(data)

    def test_syntax_error_has_path_line_and_column(self):
        self.path.write_text('{\n "run_id": }', encoding="utf-8")
        with self.assertRaises(DataValidationError) as caught:
            JsonConnector().load(str(self.path))
        self.assertIn(f"{self.path}:2:", str(caught.exception))
        self.assertIn("invalid JSON", str(caught.exception))

    def test_empty_file(self):
        self.path.write_text("", encoding="utf-8")
        with self.assertRaises(DataValidationError):
            JsonConnector().load(str(self.path))

    def test_nonstandard_constants_rejected_in_metadata(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value):
                with self.assertRaisesRegex(DataValidationError, "invalid JSON numeric constant"):
                    self.load(dict(self.nested, config={"invalid": value}))

    def test_duplicate_keys_rejected_at_any_depth(self):
        for text in ('{"run_id":"a","run_id":"b"}',
                     '{"results":{"f1":0.8,"f1":0.9}}'):
            with self.subTest(text=text):
                self.path.write_text(text, encoding="utf-8")
                with self.assertRaisesRegex(DataValidationError, "duplicate JSON key"):
                    JsonConnector().load(str(self.path))

    def test_bom_and_unicode(self):
        data = dict(self.nested, model_info={"name": "中文模型"})
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8-sig")
        self.assertEqual(JsonConnector().load(str(self.path))[0].model, "中文模型")

    def test_invalid_encoding(self):
        self.path.write_bytes(b"\xff\xfe\x00")
        with self.assertRaisesRegex(DataValidationError, "expected UTF-8"):
            JsonConnector().load(str(self.path))

    def test_missing_file_and_directory(self):
        for source in (self.path, Path(self.directory.name)):
            with self.subTest(source=source):
                with self.assertRaises(InputError):
                    JsonConnector().load(str(source))

    def test_permission_failure(self):
        with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
            with self.assertRaisesRegex(InputError, "cannot read file"):
                JsonConnector().load(str(self.path))

    def test_deeply_nested_non_record(self):
        self.path.write_text("[" * 2000 + "0" + "]" * 2000, encoding="utf-8")
        with self.assertRaises(DataValidationError):
            JsonConnector().load(str(self.path))

    def test_parser_limits_translated(self):
        self.path.write_text("{}", encoding="utf-8")
        for error in (RecursionError("depth limit"), ValueError("integer length limit")):
            with self.subTest(error=type(error).__name__):
                with patch("experimentlens_json.json.loads", side_effect=error):
                    with self.assertRaisesRegex(DataValidationError, "parser limits"):
                        JsonConnector().load(str(self.path))

    def test_bad_second_record_reports_index_and_aborts(self):
        with self.assertRaises(DataValidationError) as caught:
            self.load([self.nested, dict(self.unified, metrics={"f1": "bad"})])
        self.assertIn(str(self.path), str(caught.exception))
        self.assertIn("record 2", str(caught.exception))

    def test_contract_and_real_entry_point_discovery(self):
        registry = ConnectorRegistry()
        registry.discover()
        self.assertEqual(registry.discovery_errors, {})
        connector = registry.for_suffix(".json")
        self.assertIsInstance(connector, JsonConnector)
        self.assertEqual(connector.name, "json")
        self.assertEqual(connector.extensions, (".json",))
        self.load(self.nested)
        self.assertEqual(load_experiments([str(self.path)])[0].metrics["f1"], 0.86)

    def test_mixed_directory_and_disabled_csv_fallback(self):
        self.load(self.nested)
        csv = Path(self.directory.name) / "metrics.csv"
        csv.write_text(
            "experiment_id,model,dataset,task,split,metric.f1\n"
            "csv_001,Model_A,Dataset_A,classification,test,0.77\n", encoding="utf-8",
        )
        records = load_experiments([self.directory.name])
        self.assertEqual({record.experiment_id for record in records}, {"exp_003", "csv_001"})
        with self.assertRaises(ConnectorNotFoundError):
            load_experiments([self.directory.name], disabled_connectors={"json"})
        records = load_experiments([str(csv)], disabled_connectors={"json"})
        self.assertEqual(records[0].experiment_id, "csv_001")

    def test_duplicate_ids_delegated_to_core(self):
        self.load([self.nested, self.nested])
        with self.assertRaises(DataValidationError):
            load_experiments([str(self.path)])


if __name__ == "__main__":
    unittest.main()
