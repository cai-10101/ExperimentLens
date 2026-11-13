"""Public errors raised by the experiment data layer."""


class ExperimentLensError(Exception):
    """Base class for expected import failures."""


class InputError(ExperimentLensError):
    """An input path is missing, unreadable, or unsupported."""


class DataValidationError(ExperimentLensError):
    """An experiment record or source file has invalid data."""


class ConnectorError(ExperimentLensError):
    """Base class for connector registration or execution failures."""


class ConnectorNotFoundError(ConnectorError):
    """No enabled connector supports the input format."""


class ConnectorRegistrationError(ConnectorError):
    """A plugin has an invalid contract or conflicts with another plugin."""


class ConnectorExecutionError(ConnectorError):
    """A connector failed while loading an input."""
