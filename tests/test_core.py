import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experimentlens import (
    ConnectorExecutionError, ConnectorNotFoundError, ConnectorRegistrationError,
    DataValidationError, ExperimentRecord, InputError, load_experiments,
)
from experimentlens.registry import ConnectorRegistry


HEADER = "experiment_id,model,dataset,task,split,metric.f1,config\n"
ROW = 'exp_001,Model_A,Dataset_A,classification,test,0.77,"{""seed"": 42}"\n'


class FakeEntryPoint:
    name = "fake_json"

    def __init__(self, connector_type):
        self.connector_type = connector_type

    def load(self):
        return self.connector_type


class FakeJsonConnector:
    name = "fake_json"
    extensions = (".json",)

    def load(self, source):
        return [ExperimentRecord("json_001", "Model_B", "Dataset_A", "classification",
                                 "test", {"f1": 0.86}, {}, source)]


class FailingJsonConnector(FakeJsonConnector):
    def load(self, source):
        raise RuntimeError("broken plugin")


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_record_validation(self):
        with self.assertRaises(DataValidationError):
            ExperimentRecord("e", "m", "d", "t", "s", {"f1": float("nan")}, {}, "x")
        with self.assertRaises(DataValidationError):
            ExperimentRecord("", "m", "d", "t", "s", {"f1": 0.5}, {}, "x")
        record = ExperimentRecord("e", "m", "d", "t", "s", {"count": 2}, {}, "x")
        self.assertEqual(record.metrics, {"count": 2.0})

    def test_record_strips_identifiers_and_metric_names(self):
        record = ExperimentRecord(" exp_001 ", " Model_A ", " Dataset_A ",
                                  " classification ", " test ", {" f1 ": 0.8}, {}, " data.csv ")
        self.assertEqual((record.experiment_id, record.model, record.dataset,
                          record.task, record.split, record.source),
                         ("exp_001", "Model_A", "Dataset_A", "classification", "test", "data.csv"))
        self.assertEqual(record.metrics, {"f1": 0.8})
        with self.assertRaisesRegex(DataValidationError, "duplicate metric name"):
            ExperimentRecord("e", "m", "d", "t", "s", {"f1": 0.8, " f1 ": 0.9}, {}, "x")

    def test_csv_file_and_recursive_directory(self):
        first = self.write("a.csv", HEADER + ROW)
        self.write("nested/b.csv", HEADER + ROW.replace("exp_001", "exp_002"))
        records = load_experiments([str(first)])
        self.assertEqual(records[0].metrics, {"f1": 0.77})
        self.assertEqual(records[0].config, {"seed": 42})
        self.assertEqual(len(load_experiments([str(self.root)])), 2)

    def test_csv_errors(self):
        for content in ("", HEADER, HEADER + ROW.replace("0.77", "bad"),
                        HEADER.replace("dataset,", "") + ROW,
                        HEADER + ROW.replace("0.77", "nan"),
                        HEADER + ROW.replace('"{""seed"": 42}"', "oops")):
            with self.subTest(content=content):
                path = self.write("bad.csv", content)
                with self.assertRaises(DataValidationError):
                    load_experiments([str(path)])
        with self.assertRaises(InputError):
            load_experiments([str(self.root / "missing.csv")])
        with self.assertRaises(InputError):
            load_experiments([])

    def test_unknown_explicit_file(self):
        path = self.write("result.json", "{}")
        with self.assertRaises(ConnectorNotFoundError):
            load_experiments([str(path)])

    def test_directory_does_not_silently_skip_json(self):
        self.write("nested/data.csv", HEADER + ROW)
        self.write("nested/result.json", "{}")
        self.write("nested/notes.txt", "unrelated")
        with self.assertRaises(ConnectorNotFoundError):
            load_experiments([str(self.root)])
        with self.assertRaises(ConnectorNotFoundError):
            load_experiments([str(self.root)], disabled_connectors={"json"})

    def test_empty_directory_and_unrelated_files(self):
        self.write("notes.txt", "not experiment data")
        with self.assertRaisesRegex(InputError, "no supported experiment files"):
            load_experiments([str(self.root)])

    def test_csv_bom_and_shape_errors(self):
        valid = self.write("bom.csv", "\ufeff" + HEADER + ROW)
        self.assertEqual(load_experiments([str(valid)])[0].experiment_id, "exp_001")
        for content in (HEADER.replace("metric.f1,", "metric.f1,metric.f1,") + ROW,
                        HEADER + ROW.replace(",0.77,", ",0.77,extra,"),
                        HEADER + "exp_001,Model_A,Dataset_A,classification,test\n"):
            with self.subTest(content=content):
                invalid = self.write("shape.csv", content)
                with self.assertRaises(DataValidationError):
                    load_experiments([str(invalid)])

    def test_csv_header_normalization_and_collision(self):
        valid = self.write("headers.csv", HEADER.replace("dataset,", " dataset ,") + ROW)
        self.assertEqual(load_experiments([str(valid)])[0].dataset, "Dataset_A")
        duplicate = self.write("duplicate_headers.csv", HEADER.replace(
            "metric.f1,config", "metric.f1, metric.f1 ,config") +
            ROW.replace("0.77,", "0.77,0.86,"))
        with self.assertRaisesRegex(DataValidationError, "duplicate or blank CSV column"):
            load_experiments([str(duplicate)])
        duplicate_metric = self.write("duplicate_metrics.csv", HEADER.replace(
            "metric.f1,config", "metric.f1,metric. f1,config") +
            ROW.replace("0.77,", "0.77,0.86,"))
        with self.assertRaisesRegex(DataValidationError, "duplicate metric name"):
            load_experiments([str(duplicate_metric)])

    def test_duplicate_experiment_ids_within_and_across_files(self):
        first = self.write("first.csv", HEADER + ROW + ROW.replace("exp_001", " exp_001 "))
        with self.assertRaisesRegex(DataValidationError, "duplicate experiment_id 'exp_001'") as same_file:
            load_experiments([str(first)])
        self.assertIn(str(first), str(same_file.exception))

        first.write_text(HEADER + ROW, encoding="utf-8")
        second = self.write("second.csv", HEADER + ROW.replace("exp_001", " exp_001 "))
        with self.assertRaisesRegex(DataValidationError, "duplicate experiment_id 'exp_001'") as two_files:
            load_experiments([str(first), str(second)])
        self.assertIn(str(first), str(two_files.exception))
        self.assertIn(str(second), str(two_files.exception))

    def test_invalid_utf8(self):
        path = self.root / "bad.csv"
        path.write_bytes(b"\xff\xfe")
        with self.assertRaisesRegex(DataValidationError, "UTF-8"):
            load_experiments([str(path)])

    @patch("experimentlens.registry.entry_points")
    def test_plugin_discovery_and_disable(self, discover):
        discover.return_value = [FakeEntryPoint(FakeJsonConnector)]
        csv_path = self.write("data.csv", HEADER + ROW)
        json_path = self.write("result.json", "{}")
        records = load_experiments([str(csv_path), str(json_path)])
        self.assertEqual([r.experiment_id for r in records], ["exp_001", "json_001"])
        with self.assertRaises(ConnectorNotFoundError):
            load_experiments([str(json_path)], disabled_connectors={"fake_json"})
        self.assertEqual(len(load_experiments([str(csv_path)], disabled_connectors={"fake_json"})), 1)

    @patch("experimentlens.registry.entry_points")
    def test_plugin_failure_and_contract(self, discover):
        discover.return_value = [FakeEntryPoint(FailingJsonConnector)]
        path = self.write("result.json", "{}")
        with self.assertRaisesRegex(ConnectorExecutionError, "broken plugin"):
            load_experiments([str(path)])
        registry = ConnectorRegistry()
        duplicate = type("DuplicateCsv", (), {"name": "other", "extensions": (".csv",),
                                             "load": lambda self, source: []})()
        with self.assertRaises(ConnectorRegistrationError):
            registry.register(duplicate)

    @patch("experimentlens.registry.entry_points")
    def test_bad_plugin_output(self, discover):
        broken = type("BadOutput", (), {"name": "fake_json", "extensions": (".json",),
                                         "load": lambda self, source: []})
        discover.return_value = [FakeEntryPoint(broken)]
        path = self.write("result.json", "{}")
        with self.assertRaisesRegex(ConnectorExecutionError, "non-empty list"):
            load_experiments([str(path)])

    @patch("experimentlens.registry.entry_points")
    def test_broken_plugin_does_not_break_csv(self, discover):
        broken = FakeEntryPoint(FakeJsonConnector)
        broken.load = lambda: (_ for _ in ()).throw(ImportError("package unavailable"))
        discover.return_value = [broken]
        csv_path = self.write("data.csv", HEADER + ROW)
        json_path = self.write("result.json", "{}")
        self.assertEqual(len(load_experiments([str(csv_path)])), 1)
        with self.assertRaisesRegex(ConnectorRegistrationError, "package unavailable"):
            load_experiments([str(json_path)])
        with self.assertRaisesRegex(ConnectorRegistrationError, "package unavailable"):
            load_experiments([str(self.root)])

    @patch("experimentlens.registry.entry_points")
    def test_disabled_connector_is_excluded_and_not_blamed_for_other_failure(self, discover):
        broken = FakeEntryPoint(FakeJsonConnector)
        broken.name = "unrelated"
        broken.load = lambda: (_ for _ in ()).throw(ImportError("unrelated failure"))
        discover.return_value = [broken]
        registry = ConnectorRegistry({"csv"})
        registry.discover()
        self.assertNotIn(".csv", registry.supported_extensions)
        self.assertNotIn("csv", registry.connectors)
        with self.assertRaises(ConnectorNotFoundError):
            registry.for_suffix(".csv")

        registry = ConnectorRegistry({"json"})
        registry.discover()
        with self.assertRaises(ConnectorNotFoundError):
            registry.for_suffix(".json")

        discover.return_value = [FakeEntryPoint(FakeJsonConnector)]
        registry = ConnectorRegistry({"fake_json"})
        registry.discover()
        self.assertEqual(registry.supported_extensions, frozenset({".csv"}))
        with self.assertRaises(ConnectorNotFoundError):
            registry.for_suffix(".json")


if __name__ == "__main__":
    unittest.main()
