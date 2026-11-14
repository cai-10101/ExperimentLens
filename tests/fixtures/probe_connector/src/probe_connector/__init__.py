"""Separate test distribution proving public connector installation works."""

from pathlib import Path

from experimentlens import DataValidationError, ExperimentRecord


class ProbeConnector:
    name = "probe"
    extensions = (".probe",)

    def load(self, source: str) -> list[ExperimentRecord]:
        experiment_id = Path(source).read_text(encoding="utf-8").strip()
        if not experiment_id:
            raise DataValidationError(f"{source}: experiment ID is empty")
        return [ExperimentRecord(experiment_id, "ProbeModel", "ProbeData", "classification",
                                 "test", {"f1": 0.5}, {}, source)]
