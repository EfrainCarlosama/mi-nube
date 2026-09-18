class AuthenticationError(RuntimeError):
    """Base error for authentication failures safe to present to the UI."""


class AuthenticationCancelled(AuthenticationError):
    """The interactive browser flow was cancelled by the user."""


class AuthenticationConfigurationError(AuthenticationError):
    """The local Microsoft Entra application configuration is missing or invalid."""


class ReauthenticationRequired(AuthenticationError):
    """No valid silent token can be acquired for the current account."""
