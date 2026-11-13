"""Public file and directory import function."""

from pathlib import Path

from .errors import ConnectorExecutionError, ExperimentLensError, InputError
from .model import ExperimentRecord
from .registry import ConnectorRegistry

# JSON is a required project format supplied by an optional package. A directory
# containing JSON must not quietly produce a CSV-only, incomplete result.
PROJECT_EXTENSIONS = frozenset({".csv", ".json"})


def load_experiments(paths: list[str], *, disabled_connectors: set[str] | None = None) -> list[ExperimentRecord]:
    """Import supported files in input order, recursively expanding directories.

    Directory contents are sorted. Unrelated files inside directories are ignored;
    known project formats without a working connector raise an error.
    an explicitly named unknown file raises ConnectorNotFoundError. Any invalid
    supported input aborts the import, so callers never receive partial results.
    """
    if not paths:
        raise InputError("at least one input path is required")
    registry = ConnectorRegistry(disabled_connectors)
    registry.discover()
    records: list[ExperimentRecord] = []
    extensions = registry.supported_extensions | PROJECT_EXTENSIONS
    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            raise InputError(f"input does not exist: {raw_path}")
        if path.is_dir():
            files = sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in extensions)
            if not files:
                raise InputError(f"no supported experiment files in directory: {raw_path}")
        elif path.is_file():
            files = [path]
        else:
            raise InputError(f"not a regular file or directory: {raw_path}")
        for file in files:
            connector = registry.for_suffix(file.suffix)
            try:
                loaded = connector.load(str(file))
                if not isinstance(loaded, list) or not loaded or any(
                    not isinstance(item, ExperimentRecord) for item in loaded
                ):
                    raise ConnectorExecutionError(f"{connector.name}: load must return a non-empty list of ExperimentRecord")
                records.extend(loaded)
            except ExperimentLensError:
                raise
            except Exception as exc:
                raise ConnectorExecutionError(f"{connector.name} failed for {file}: {exc}") from exc
    return records
