"""Public connector contract and built-in CSV connector."""

import csv
import json
from pathlib import Path
from typing import Protocol

from .errors import DataValidationError, InputError
from .model import ExperimentRecord


class ExperimentConnector(Protocol):
    """An independently installed connector implements these three members.

    ``extensions`` contains lowercase suffixes including the leading dot.
    ``load`` returns records or raises an ExperimentLensError subclass.
    """

    name: str
    extensions: tuple[str, ...]

    def load(self, source: str) -> list[ExperimentRecord]: ...


class CsvConnector:
    name = "csv"
    extensions = (".csv",)
    required_columns = ("experiment_id", "model", "dataset", "task", "split")

    def load(self, source: str) -> list[ExperimentRecord]:
        path = Path(source)
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream, strict=True)
                columns = reader.fieldnames
                if not columns:
                    raise DataValidationError(f"{source}: CSV is empty or has no header")
                if len(columns) != len(set(columns)) or any(not c or not c.strip() for c in columns):
                    raise DataValidationError(f"{source}: duplicate or blank CSV column")
                missing = set(self.required_columns) - set(columns)
                if missing:
                    raise DataValidationError(f"{source}: missing columns: {', '.join(sorted(missing))}")
                metric_columns = [c for c in columns if c.startswith("metric.")]
                if not metric_columns or any(c == "metric." for c in metric_columns):
                    raise DataValidationError(f"{source}: at least one named metric.<name> column is required")
                records = []
                for line, row in enumerate(reader, start=2):
                    if None in row or any(value is None for value in row.values()):
                        raise DataValidationError(f"{source}:{line}: wrong number of columns")
                    metrics = {}
                    for column in metric_columns:
                        try:
                            metrics[column[7:]] = float(row[column])
                        except ValueError as exc:
                            raise DataValidationError(f"{source}:{line}: {column} must be numeric") from exc
                    raw_config = row.get("config", "")
                    try:
                        config = json.loads(raw_config) if raw_config.strip() else {}
                    except json.JSONDecodeError as exc:
                        raise DataValidationError(f"{source}:{line}: invalid config JSON") from exc
                    try:
                        records.append(ExperimentRecord(
                            **{name: row[name] for name in self.required_columns},
                            metrics=metrics, config=config, source=source,
                        ))
                    except DataValidationError as exc:
                        raise DataValidationError(f"{source}:{line}: {exc}") from exc
                if not records:
                    raise DataValidationError(f"{source}: CSV has no data rows")
                return records
        except UnicodeError as exc:
            raise DataValidationError(f"{source}: expected UTF-8 CSV") from exc
        except csv.Error as exc:
            raise DataValidationError(f"{source}: malformed CSV: {exc}") from exc
        except OSError as exc:
            raise InputError(f"{source}: cannot read file: {exc.strerror or exc}") from exc
