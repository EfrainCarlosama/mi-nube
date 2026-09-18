class DocumentError(RuntimeError):
    """Safe user-facing document workflow error."""


class DocumentValidationError(DocumentError):
    pass
