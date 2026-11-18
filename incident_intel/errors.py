"""Application errors. Every error carries a stable machine-readable code and an HTTP status."""


class AppError(Exception):


    """Base class for errors that are safe to show to API clients."""
    status = 500
    code = "internal_error"

    def __init__(self, message, *, code=None, status=None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status:
            self.status = status


class ValidationError(AppError):
    status = 400
    code = "validation_error"


class NotFoundError(AppError):
    status = 404
    code = "not_found"


class ProviderError(AppError):
    """Failure talking to an AI provider. Never silently replaced by demo output."""

    status = 502
    code = "provider_error"


class ProviderNotConfigured(ProviderError):
    status = 400
    code = "provider_not_configured"


class InvalidCredentials(ProviderError):
    code = "invalid_credentials"


class RateLimited(ProviderError):
    status = 429
    code = "rate_limited"


class ModelUnavailable(ProviderError):
    code = "model_unavailable"


class ProviderUnavailable(ProviderError):
    status = 503
    code = "provider_unavailable"


class InvalidProviderResponse(ProviderError):
    code = "invalid_provider_response"
