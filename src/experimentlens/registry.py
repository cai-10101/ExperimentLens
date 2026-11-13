"""Discover connector packages via Python distribution entry points."""

from importlib.metadata import entry_points

from .connectors import CsvConnector, ExperimentConnector
from .errors import ConnectorNotFoundError, ConnectorRegistrationError

ENTRY_POINT_GROUP = "experimentlens.connectors"


class ConnectorRegistry:
    def __init__(self, disabled: set[str] | None = None) -> None:
        self.disabled = set(disabled or ())
        self._connectors: dict[str, ExperimentConnector] = {}
        self.discovery_errors: dict[str, str] = {}
        self.register(CsvConnector())

    def register(self, connector: ExperimentConnector) -> None:
        name = getattr(connector, "name", None)
        extensions = getattr(connector, "extensions", None)
        if (not isinstance(name, str) or not name or not isinstance(extensions, tuple)
                or not extensions or not callable(getattr(connector, "load", None))
                or any(not isinstance(e, str) or not e.startswith(".") or e != e.lower()
                       for e in extensions)):
            raise ConnectorRegistrationError("connector requires name, lowercase extensions, and load(source)")
        if name in self._connectors:
            raise ConnectorRegistrationError(f"duplicate connector name: {name}")
        existing = {e for item in self._connectors.values() for e in item.extensions}
        overlap = existing.intersection(extensions)
        if overlap:
            raise ConnectorRegistrationError(f"extension already registered: {', '.join(sorted(overlap))}")
        self._connectors[name] = connector

    def discover(self) -> None:
        for ep in entry_points(group=ENTRY_POINT_GROUP):
            if ep.name in self.disabled:
                continue
            try:
                factory = ep.load()
                connector = factory()
                if connector.name != ep.name:
                    raise ConnectorRegistrationError(f"entry point {ep.name!r} must match connector name")
                self.register(connector)
            except Exception as exc:
                self.discovery_errors[ep.name] = str(exc)

    def for_suffix(self, suffix: str) -> ExperimentConnector:
        for connector in self._connectors.values():
            if connector.name not in self.disabled and suffix.lower() in connector.extensions:
                return connector
        if self.discovery_errors:
            problems = "; ".join(f"{name}: {error}" for name, error in self.discovery_errors.items())
            raise ConnectorRegistrationError(f"no connector for {suffix}; plugin discovery failed: {problems}")
        raise ConnectorNotFoundError(f"no enabled connector for {suffix or 'extensionless file'}")

    @property
    def connectors(self) -> tuple[str, ...]:
        return tuple(name for name in self._connectors if name not in self.disabled)

    @property
    def supported_extensions(self) -> frozenset[str]:
        return frozenset(ext for connector in self._connectors.values()
                         for ext in connector.extensions)
