from __future__ import annotations


class ProjectError(RuntimeError):
    """Base project error safe to display in the UI."""


class ProjectValidationError(ProjectError):
    pass


class ProjectCreationError(ProjectError):
    pass
