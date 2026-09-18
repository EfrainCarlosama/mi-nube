from __future__ import annotations


class GraphError(RuntimeError):
    """Base error safe to surface as a concise user-facing message."""


class GraphNetworkError(GraphError):
    pass


class GraphAuthenticationError(GraphError):
    pass


class GraphPermissionError(GraphError):
    pass


class GraphNotFoundError(GraphError):
    pass


class GraphConflictError(GraphError):
    pass


class GraphThrottledError(GraphError):
    pass


class GraphServiceError(GraphError):
    pass


class GraphValidationError(GraphError):
    pass


class GraphUploadCancelled(GraphError):
    """Raised when the user cancels an active upload."""


class GraphDeltaResetRequired(GraphError):
    """Raised when Microsoft Graph invalidates a stored delta cursor."""
