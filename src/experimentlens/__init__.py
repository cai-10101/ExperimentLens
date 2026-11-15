"""Stable public API for ExperimentLens data producers and consumers."""

from .analyzer import (
    AnalysisResult,
    ComparabilityReport,
    MetricSummary,
    analyze_experiments,
    resolve_metric_direction,
)
from .connectors import ExperimentConnector
from .errors import (
    ConnectorError,
    ConnectorExecutionError,
    ConnectorNotFoundError,
    ConnectorRegistrationError,
    DataValidationError,
    ExperimentLensError,
    InputError,
)
from .importer import load_experiments
from .model import ExperimentRecord
from .registry import ConnectorRegistry
from .reporter import export_summary_csv, generate_html_report, generate_report

__all__ = [
    "ExperimentRecord",
    "ExperimentConnector",
    "ConnectorRegistry",
    "load_experiments",
    "AnalysisResult",
    "ComparabilityReport",
    "MetricSummary",
    "analyze_experiments",
    "resolve_metric_direction",
    "generate_report",
    "export_summary_csv",
    "generate_html_report",
    "ExperimentLensError",
    "InputError",
    "DataValidationError",
    "ConnectorError",
    "ConnectorNotFoundError",
    "ConnectorRegistrationError",
    "ConnectorExecutionError",
]
