class Bd1Error(Exception):
    """Base exception for controlled bd-1 failures."""


class DirtyRepositoryError(Bd1Error):
    """Raised when bd-1 refuses to start from a dirty base repository."""


class GitError(Bd1Error):
    """Raised when a git command fails."""


class CommandStartError(Bd1Error):
    """Raised when a subprocess cannot be started."""


class IllegalTransitionError(Bd1Error):
    """Raised when a run attempts a transition the state machine forbids."""


class UnknownRunError(Bd1Error):
    """Raised when a run id cannot be resolved to a run record."""


class WorkspaceConfigError(Bd1Error):
    """Raised when workspace configuration is invalid."""


class RunBlockedError(Bd1Error):
    """Raised when a run cannot continue without human action."""


class PrError(Bd1Error):
    """Raised when PR publishing or monitoring fails."""


class ReasoningOutputError(Bd1Error):
    """Raised when a DSPy reasoning program returns empty or malformed output."""
