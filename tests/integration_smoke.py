"""Run after installing both the core and the separate probe distribution."""

import tempfile
from importlib.metadata import entry_points
from pathlib import Path

from experimentlens import ConnectorNotFoundError, load_experiments


def main() -> None:
    assert any(ep.name == "probe" for ep in entry_points(group="experimentlens.connectors"))
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        probe = root / "run.probe"
        probe.write_text("installed_plugin_001\n", encoding="utf-8")
        csv = root / "run.csv"
        csv.write_text("experiment_id,model,dataset,task,split,metric.f1\n"
                       "csv_001,Model_A,Dataset_A,classification,test,0.77\n", encoding="utf-8")
        records = load_experiments([str(root)])
        assert {record.experiment_id for record in records} == {"csv_001", "installed_plugin_001"}
        try:
            load_experiments([str(probe)], disabled_connectors={"probe"})
        except ConnectorNotFoundError:
            pass
        else:
            raise AssertionError("disabled probe connector was still available")
        assert len(load_experiments([str(csv)], disabled_connectors={"probe"})) == 1
    print("Independent connector installation, discovery, disable, and CSV fallback: OK")


if __name__ == "__main__":
    main()
