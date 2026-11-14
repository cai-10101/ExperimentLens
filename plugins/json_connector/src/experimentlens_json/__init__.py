"""JSON connector using only the public ExperimentLens contract."""

import json
from pathlib import Path

from experimentlens import DataValidationError, ExperimentRecord, InputError

__all__ = ["JsonConnector"]


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise DataValidationError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise DataValidationError(f"invalid JSON numeric constant: {value}")


def _record(item: object, source: str) -> ExperimentRecord:
    if not isinstance(item, dict):
        raise DataValidationError("record must be an object")
    nested = "run_id" in item or "model_info" in item or "results" in item
    if nested:
        if "experiment_id" in item or "model" in item or "metrics" in item:
            raise DataValidationError("mixed nested and unified record fields")
        model_info = item.get("model_info")
        if not isinstance(model_info, dict):
            raise DataValidationError("model_info must be an object with a name")
        metrics = item.get("results")
        if not isinstance(metrics, dict):
            raise DataValidationError("results must be a non-empty object")
        metrics = dict(metrics)
        if "f1_score" in metrics:
            if "f1" in metrics:
                raise DataValidationError("results contains both f1 and f1_score")
            metrics["f1"] = metrics.pop("f1_score")
        experiment_id = item.get("run_id")
        model = model_info.get("name")
    else:
        experiment_id = item.get("experiment_id")
        model = item.get("model")
        metrics = item.get("metrics")
    return ExperimentRecord(
        experiment_id=experiment_id,
        model=model,
        dataset=item.get("dataset"),
        task=item.get("task"),
        split=item.get("split"),
        metrics=metrics,
        config=item.get("config", {}),
        source=source,
    )


class JsonConnector:
    """Load one record, an array, or an object containing an experiments array."""

    name = "json"
    extensions = (".json",)

    def load(self, source: str) -> list[ExperimentRecord]:
        path = Path(source)
        try:
            content = path.read_text(encoding="utf-8-sig")
        except UnicodeError as exc:
            raise DataValidationError(f"{source}: expected UTF-8 JSON") from exc
        except OSError as exc:
            raise InputError(f"{source}: cannot read file: {exc.strerror or exc}") from exc
        try:
            data = json.loads(
                content, object_pairs_hook=_unique_object, parse_constant=_reject_constant,
            )
            if isinstance(data, dict) and "experiments" in data:
                if len(data) != 1:
                    raise DataValidationError("experiments wrapper must contain only experiments")
                items = data["experiments"]
                if not isinstance(items, list):
                    raise DataValidationError("experiments must be an array")
            else:
                items = data if isinstance(data, list) else [data]
            if not items:
                raise DataValidationError("JSON contains no experiment records")
            records = []
            for index, item in enumerate(items, start=1):
                try:
                    records.append(_record(item, source))
                except DataValidationError as exc:
                    raise DataValidationError(f"record {index}: {exc}") from exc
            return records
        except json.JSONDecodeError as exc:
            raise DataValidationError(
                f"{source}:{exc.lineno}:{exc.colno}: invalid JSON: {exc.msg}"
            ) from exc
        except DataValidationError as exc:
            raise DataValidationError(f"{source}: {exc}") from exc
        except (ValueError, RecursionError) as exc:
            raise DataValidationError(f"{source}: JSON exceeds parser limits") from exc
