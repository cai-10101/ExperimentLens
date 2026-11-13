"""Shared record type consumed by connectors and analysis code."""

from dataclasses import dataclass, field
import math
from typing import Any

from .errors import DataValidationError


@dataclass
class ExperimentRecord:
    experiment_id: str
    model: str
    dataset: str
    task: str
    split: str
    metrics: dict[str, float]
    config: dict[str, Any] = field(default_factory=dict)
    source: str = ""

    def __post_init__(self) -> None:
        for name in ("experiment_id", "model", "dataset", "task", "split", "source"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise DataValidationError(f"{name} must be a non-empty string")
        if not isinstance(self.metrics, dict) or not self.metrics:
            raise DataValidationError("metrics must be a non-empty mapping")
        normalized_metrics = {}
        for name, value in self.metrics.items():
            if not isinstance(name, str) or not name.strip():
                raise DataValidationError("metric names must be non-empty strings")
            try:
                number = float(value) if not isinstance(value, bool) and isinstance(value, (int, float)) else float("nan")
            except OverflowError:
                number = float("nan")
            if not math.isfinite(number):
                raise DataValidationError(f"metric {name!r} must be a finite number")
            normalized_metrics[name] = number
        self.metrics = normalized_metrics
        if not isinstance(self.config, dict):
            raise DataValidationError("config must be a mapping")
