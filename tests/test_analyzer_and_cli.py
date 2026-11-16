import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from experimentlens import (
    DataValidationError,
    ExperimentRecord,
    InputError,
    analyze_experiments,
    export_summary_csv,
    generate_html_report,
    generate_report,
    load_experiments,
)
from experimentlens.cli import main as cli_main


class FakeJsonEntryPoint:
    name = "json"

    def __init__(self, connector_cls):
        self.connector_cls = connector_cls

    def load(self):
        return self.connector_cls


class FakeJsonConnector:
    name = "json"
    extensions = (".json",)

    def load(self, source: str) -> list[ExperimentRecord]:
        return [
            ExperimentRecord(
                experiment_id="exp_003",
                model="Model_C",
                dataset="Dataset_A",
                task="classification",
                split="test",
                metrics={"precision": 0.90, "recall": 0.82, "f1": 0.86},
                config={"seed": 44, "lr": 0.001},
                source=source,
            )
        ]


class AnalyzerAndCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, rel_path: str, content: str) -> Path:
        target = self.root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def _sample_records(self) -> list[ExperimentRecord]:
        return [
            ExperimentRecord(
                experiment_id="exp_001",
                model="Model_A",
                dataset="Dataset_A",
                task="classification",
                split="test",
                metrics={"precision": 0.85, "recall": 0.70, "f1": 0.77},
                config={"seed": 42, "lr": 0.01},
                source="examples/experiments/exp_001/metrics.csv",
            ),
            ExperimentRecord(
                experiment_id="exp_002",
                model="Model_B",
                dataset="Dataset_A",
                task="classification",
                split="test",
                metrics={"precision": 0.88, "recall": 0.75, "f1": 0.81},
                config={"seed": 43, "lr": 0.01},
                source="examples/experiments/exp_002/metrics.csv",
            ),
            ExperimentRecord(
                experiment_id="exp_003",
                model="Model_C",
                dataset="Dataset_A",
                task="classification",
                split="test",
                metrics={"precision": 0.90, "recall": 0.82, "f1": 0.86},
                config={"seed": 44, "lr": 0.001},
                source="examples/experiments/exp_003/results.json",
            ),
        ]

    def test_comparable_metrics_and_sorting(self) -> None:
        records = self._sample_records()
        result = analyze_experiments(records, sort_by="f1")

        self.assertTrue(result.comparability.is_comparable)
        self.assertEqual(result.comparability.dataset, "Dataset_A")
        self.assertEqual(result.comparability.task, "classification")
        self.assertEqual(result.comparability.split, "test")
        self.assertEqual([r.experiment_id for r in result.records], ["exp_003", "exp_002", "exp_001"])

        f1_summary = result.metric_summaries["f1"]
        self.assertEqual(f1_summary.best_experiment_id, "exp_003")
        self.assertAlmostEqual(f1_summary.best_value, 0.86)
        self.assertEqual(f1_summary.worst_experiment_id, "exp_001")
        self.assertAlmostEqual(f1_summary.worst_value, 0.77)
        self.assertAlmostEqual(f1_summary.spread, 0.09)
        self.assertAlmostEqual(f1_summary.delta, 0.09)
        self.assertEqual(f1_summary.ranking, ("exp_003", "exp_002", "exp_001"))

        self.assertIn("seed", result.config_diffs)
        self.assertIn("lr", result.config_diffs)
        self.assertTrue(any("exp_003" in c and "0.86" in c and "0.09" in c for c in result.conclusions))

    def test_lower_is_better_direction(self) -> None:
        records = [
            ExperimentRecord("exp_1", "M1", "D1", "regression", "test", {"loss": 0.45, "latency": 120.0}, {}, "a.csv"),
            ExperimentRecord("exp_2", "M2", "D1", "regression", "test", {"loss": 0.18, "latency": 200.0}, {}, "b.csv"),
        ]
        result = analyze_experiments(
            records,
            sort_by="loss",
            metric_directions={"latency": "lower"},
        )
        loss_sum = result.metric_summaries["loss"]
        self.assertEqual(loss_sum.direction, "lower")
        self.assertEqual(loss_sum.best_experiment_id, "exp_2")
        self.assertAlmostEqual(loss_sum.best_value, 0.18)
        self.assertEqual(loss_sum.worst_experiment_id, "exp_1")
        self.assertAlmostEqual(loss_sum.delta, 0.27)
        self.assertEqual([r.experiment_id for r in result.records], ["exp_2", "exp_1"])

    def test_tiny_non_zero_spread_not_misjudged_as_no_difference(self) -> None:
        records = [
            ExperimentRecord("exp_1", "M1", "D1", "cls", "test", {"loss": 0.8}, {}, "a.csv"),
            ExperimentRecord("exp_2", "M2", "D1", "cls", "test", {"loss": 0.80000000001}, {}, "b.csv"),
        ]
        result = analyze_experiments(records, sort_by="loss")
        self.assertTrue(result.comparability.is_comparable)
        summary = result.metric_summaries["loss"]
        self.assertGreater(summary.spread, 0.0)
        self.assertGreater(summary.delta, 0.0)
        self.assertEqual(summary.best_experiment_id, "exp_1")
        self.assertEqual(summary.worst_experiment_id, "exp_2")
        # Conclusion must NOT state "无差异"
        self.assertFalse(any("无差异" in c for c in result.conclusions))
        self.assertTrue(any("exp_1" in c and "低" in c for c in result.conclusions))

        # Test true equality produces "无差异"
        equal_records = [
            ExperimentRecord("exp_1", "M1", "D1", "cls", "test", {"acc": 0.95}, {}, "a.csv"),
            ExperimentRecord("exp_2", "M2", "D1", "cls", "test", {"acc": 0.95}, {}, "b.csv"),
        ]
        eq_result = analyze_experiments(equal_records)
        self.assertTrue(any("无差异" in c for c in eq_result.conclusions))

    def test_non_comparable_experiments_and_strict_mode(self) -> None:
        records = [
            ExperimentRecord("exp_1", "M1", "Dataset_A", "classification", "test", {"f1": 0.80}, {}, "a.csv"),
            ExperimentRecord("exp_2", "M2", "Dataset_B", "classification", "val", {"f1": 0.92}, {}, "b.csv"),
        ]
        result = analyze_experiments(records)
        self.assertFalse(result.comparability.is_comparable)
        self.assertEqual(result.metric_summaries, {})
        self.assertTrue(any("dataset mismatch" in r for r in result.comparability.reasons))
        self.assertTrue(any("split mismatch" in r for r in result.comparability.reasons))
        self.assertTrue(any("不可直接比较" in c for c in result.conclusions))

        with self.assertRaisesRegex(DataValidationError, "not comparable"):
            analyze_experiments(records, strict_comparability=True)

        filtered_result = analyze_experiments(records, filter_dataset="Dataset_A")
        self.assertTrue(filtered_result.comparability.is_comparable)
        self.assertEqual(len(filtered_result.records), 1)

    def test_partial_metrics_and_strict_comparability(self) -> None:
        records = [
            ExperimentRecord("exp_1", "M1", "D1", "classification", "test", {"f1": 0.80, "auc": 0.91}, {}, "a.csv"),
            ExperimentRecord("exp_2", "M2", "D1", "classification", "test", {"f1": 0.85}, {}, "b.csv"),
        ]
        # In default mode, common metrics can still be analyzed while missing metrics trigger warnings
        result = analyze_experiments(records)
        self.assertTrue(result.comparability.is_comparable)
        self.assertEqual(result.comparability.common_metrics, ("f1",))
        self.assertEqual(result.comparability.all_metrics, ("f1", "auc"))
        self.assertTrue(any("auc" in w and "exp_2" in w for w in result.comparability.warnings))
        self.assertIn("f1", result.metric_summaries)

        # In strict mode, missing metrics must be rejected
        with self.assertRaisesRegex(DataValidationError, "not comparable.*missing in: exp_2"):
            analyze_experiments(records, strict_comparability=True)

        with self.assertRaisesRegex(DataValidationError, "not present in all experiments"):
            analyze_experiments(records, sort_by="auc")

        with self.assertRaisesRegex(DataValidationError, "unknown sort_by metric"):
            analyze_experiments(records, sort_by="nonexistent")

        with self.assertRaisesRegex(DataValidationError, "invalid optimization direction"):
            analyze_experiments(records, metric_directions={"f1": "sideways"})

        dup_records = [records[0], records[0]]
        with self.assertRaisesRegex(DataValidationError, "duplicate experiment_id"):
            analyze_experiments(dup_records)

    def test_markdown_csv_and_html_reports(self) -> None:
        result = analyze_experiments(self._sample_records(), sort_by="f1")
        md = generate_report(result)
        self.assertIn("可比较 (Comparable)", md)
        self.assertIn("| exp_003 | Model_C | Dataset_A | classification | test |", md)
        self.assertIn("examples/experiments/exp_003/results.json", md)
        self.assertIn("exp_003 > exp_002 > exp_001", md)

        csv_out = self.root / "out" / "summary.csv"
        export_summary_csv(result, csv_out)
        self.assertTrue(csv_out.is_file())
        reloaded = load_experiments([str(csv_out)])
        self.assertEqual([r.experiment_id for r in reloaded], ["exp_003", "exp_002", "exp_001"])

        html_out = generate_html_report(result)
        self.assertIn("<!DOCTYPE html>", html_out)
        self.assertIn("指标图表：f1", html_out)

    def test_csv_export_preserves_high_precision(self) -> None:
        records = [
            ExperimentRecord("exp_1", "M1", "D1", "cls", "test", {"loss": 0.123456}, {}, "a.csv"),
            ExperimentRecord("exp_2", "M2", "D1", "cls", "test", {"loss": 0.123457}, {}, "b.csv"),
        ]
        result = analyze_experiments(records)
        csv_file = self.root / "precision.csv"
        export_summary_csv(result, csv_file)

        # Reload exported CSV and verify that precision differences are preserved
        reloaded = load_experiments([str(csv_file)])
        self.assertEqual(len(reloaded), 2)
        self.assertEqual(reloaded[0].metrics["loss"], 0.123456)
        self.assertEqual(reloaded[1].metrics["loss"], 0.123457)
        self.assertNotEqual(reloaded[0].metrics["loss"], reloaded[1].metrics["loss"])

    @patch("experimentlens.registry.entry_points")
    def test_cli_end_to_end_with_csv_and_json_plugin(self, mock_eps) -> None:
        mock_eps.return_value = [FakeJsonEntryPoint(FakeJsonConnector)]
        exp_dir = self.root / "experiments"
        self.write(
            "experiments/exp_001/metrics.csv",
            'experiment_id,model,dataset,task,split,metric.precision,metric.recall,metric.f1,config\n'
            'exp_001,Model_A,Dataset_A,classification,test,0.85,0.70,0.77,"{""seed"": 42}"\n',
        )
        self.write(
            "experiments/exp_002/metrics.csv",
            'experiment_id,model,dataset,task,split,metric.precision,metric.recall,metric.f1,config\n'
            'exp_002,Model_B,Dataset_A,classification,test,0.88,0.75,0.81,"{""seed"": 43}"\n',
        )
        self.write("experiments/exp_003/results.json", '{"run_id": "exp_003"}')

        md_file = self.root / "report.md"
        csv_file = self.root / "summary.csv"
        html_file = self.root / "report.html"

        code = cli_main([
            str(exp_dir),
            "--sort-by", "f1",
            "-o", str(md_file),
            "--csv-output", str(csv_file),
            "--html-output", str(html_file),
        ])
        self.assertEqual(code, 0)
        report_text = md_file.read_text(encoding="utf-8")
        self.assertIn("exp_003", report_text)
        self.assertIn("0.86", report_text)
        self.assertIn("0.09", report_text)
        self.assertTrue(csv_file.is_file())
        self.assertTrue(html_file.is_file())

        stderr_buf = io.StringIO()
        with redirect_stderr(stderr_buf):
            err_code = cli_main([str(exp_dir), "--disable-connector", "json"])
        self.assertEqual(err_code, 3)
        self.assertIn("ConnectorNotFoundError", stderr_buf.getvalue())

        stdout_buf = io.StringIO()
        with redirect_stdout(stdout_buf):
            csv_only_code = cli_main([
                str(self.root / "experiments/exp_001/metrics.csv"),
                str(self.root / "experiments/exp_002/metrics.csv"),
                "--disable-connector", "json",
            ])
        self.assertEqual(csv_only_code, 0)
        self.assertIn("exp_002", stdout_buf.getvalue())

    def test_cli_prevents_overwriting_input_file(self) -> None:
        input_csv = self.write(
            "data.csv",
            'experiment_id,model,dataset,task,split,metric.f1\n'
            'exp_001,Model_A,Dataset_A,classification,test,0.77\n',
        )
        original_content = input_csv.read_text(encoding="utf-8")

        stderr_buf = io.StringIO()
        with redirect_stderr(stderr_buf):
            code = cli_main([str(input_csv), "-o", str(input_csv)])
        self.assertEqual(code, 2)
        self.assertIn("InputError", stderr_buf.getvalue())
        self.assertIn("conflicts with input data file", stderr_buf.getvalue())
        # Verify that original input file is completely untouched
        self.assertEqual(input_csv.read_text(encoding="utf-8"), original_content)

        # Also verify collision between two output flags
        out_csv = self.root / "output.csv"
        with redirect_stderr(stderr_buf):
            col_code = cli_main([str(input_csv), "-o", str(out_csv), "--csv-output", str(out_csv)])
        self.assertEqual(col_code, 2)
        self.assertIn("conflicts with", stderr_buf.getvalue())

    def test_cli_error_exit_codes(self) -> None:
        stderr_buf = io.StringIO()
        with redirect_stderr(stderr_buf):
            code = cli_main([str(self.root / "missing.csv")])
        self.assertEqual(code, 2)
        self.assertIn("InputError", stderr_buf.getvalue())


if __name__ == "__main__":
    unittest.main()
