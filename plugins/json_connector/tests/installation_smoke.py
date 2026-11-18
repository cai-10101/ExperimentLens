"""Run after installing or uninstalling the plugin in an isolated environment."""

import sys
from pathlib import Path
import tempfile

from experimentlens import ConnectorNotFoundError, ConnectorRegistry, load_experiments


def main():
    mode = sys.argv[1]
    if mode not in {"installed", "absent"}:
        raise ValueError("expected installed or absent")
    registry = ConnectorRegistry()
    registry.discover()
    assert not registry.discovery_errors, registry.discovery_errors
    with tempfile.TemporaryDirectory() as directory:
        csv = Path(directory) / "metrics.csv"
        csv.write_text(
            "experiment_id,model,dataset,task,split,metric.f1\n"
            "csv_001,Model_A,Dataset_A,classification,test,0.77\n", encoding="utf-8",
        )
        assert load_experiments([str(csv)])[0].metrics["f1"] == 0.77
        if mode == "installed":
            assert registry.for_suffix(".json").name == "json"
            example = Path(__file__).resolve().parents[1] / "examples" / "nested.json"
            assert load_experiments([str(example)])[0].metrics["f1"] == 0.86
        else:
            assert "json" not in registry.connectors
            try:
                registry.for_suffix(".json")
            except ConnectorNotFoundError:
                pass
            else:
                raise AssertionError("JSON remains available after uninstall")
    print(f"{mode}: entry-point discovery and CSV import passed")


if __name__ == "__main__":
    main()
