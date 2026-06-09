class Bd1Error(Exception):
    """Base exception for controlled bd-1 failures."""


class DirtyRepositoryError(Bd1Error):
    """Raised when bd-1 refuses to start from a dirty base repository."""


class GitError(Bd1Error):
    """Raised when a git command fails."""


class WorkspaceConfigError(Bd1Error):
    """Raised when workspace configuration is invalid."""


class RunBlockedError(Bd1Error):
    """Raised when a run cannot continue without human action."""


class PrError(Bd1Error):
    """Raised when PR publishing or monitoring fails."""
