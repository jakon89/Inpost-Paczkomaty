"""
Exception classes for InPost API errors.

This module provides a hierarchy of exceptions for handling various
InPost API error scenarios including authentication, rate limiting,
and validation errors.
"""

import json
from typing import Any, Optional


class InPostApiError(Exception):
    """Base exception for InPost API errors."""

    def __init__(
        self,
        message: str,
        error_type: Optional[str] = None,
        status: Optional[int] = None,
        detail: Optional[str] = None,
        detail_type: Optional[str] = None,
        instance: Optional[str] = None,
        raw_response: Optional[Any] = None,
    ) -> None:
        """
        Initialize InPost API error.

        Args:
            message: Human-readable error message.
            error_type: API error type (e.g., "UserCatalogueBusinessFailure").
            status: HTTP status code.
            detail: Error detail string (may contain nested JSON).
            detail_type: Parsed error type from detail JSON.
            instance: API endpoint that produced the error.
            raw_response: Original API response (dict or string).
        """
        super().__init__(message)
        self.error_type = error_type
        self.status = status
        self.detail = detail
        self.detail_type = detail_type
        self.instance = instance
        self.raw_response = raw_response

    @classmethod
    def from_response(cls, response_body: Any, status_code: int) -> "InPostApiError":
        """
        Create an InPostApiError from an API response.

        Args:
            response_body: The API response body (dict or string).
            status_code: HTTP status code.

        Returns:
            InPostApiError instance with parsed error information.
        """
        # Handle non-dict responses (HTML, plain text, etc.)
        if not isinstance(response_body, dict):
            return cls(
                message=cls._get_http_status_message(status_code),
                error_type="HttpError",
                status=status_code,
                detail=str(response_body)[:500] if response_body else None,
                raw_response=response_body,
            )

        error_type = response_body.get("type", "UnknownError")
        status = response_body.get("status", status_code)
        title = response_body.get("title", cls._get_http_status_message(status_code))
        detail = response_body.get("detail", "")
        instance = response_body.get("instance", "")

        # Parse nested JSON in detail field
        detail_type = None
        if detail:
            try:
                detail_parsed = json.loads(detail)
                if isinstance(detail_parsed, dict):
                    detail_type = detail_parsed.get("type")
            except (json.JSONDecodeError, TypeError):
                pass

        # Build human-readable message
        message = title
        if detail_type:
            message = f"{title}: {detail_type}"
        elif detail and not detail.startswith("{"):
            message = f"{title}: {detail}"

        return cls(
            message=message,
            error_type=error_type,
            status=status,
            detail=detail,
            detail_type=detail_type,
            instance=instance,
            raw_response=response_body,
        )

    @staticmethod
    def _get_http_status_message(status_code: int) -> str:
        """
        Get human-readable message for HTTP status code.

        Args:
            status_code: HTTP status code.

        Returns:
            Human-readable status message.
        """
        messages = {
            400: "Bad Request - Invalid request parameters",
            401: "Unauthorized - Authentication required or session expired",
            403: "Forbidden - Access denied, XSRF token may be missing or invalid",
            404: "Not Found - Resource does not exist",
            422: "Unprocessable Entity - Validation failed",
            429: "Too Many Requests - Rate limit exceeded",
            500: "Internal Server Error - Server encountered an error",
            502: "Bad Gateway - Server received invalid response",
            503: "Service Unavailable - Server is temporarily unavailable",
        }
        return messages.get(status_code, f"HTTP Error {status_code}")

    def __str__(self) -> str:
        """Return string representation of the error."""
        parts = [super().__str__()]
        if self.error_type:
            parts.append(f"type={self.error_type}")
        if self.status:
            parts.append(f"status={self.status}")
        if self.detail_type:
            parts.append(f"detail_type={self.detail_type}")
        return " | ".join(parts)

    def __repr__(self) -> str:
        """Return detailed representation for debugging."""
        return (
            f"{self.__class__.__name__}("
            f"message={self.args[0]!r}, "
            f"status={self.status}, "
            f"error_type={self.error_type!r}, "
            f"detail_type={self.detail_type!r})"
        )


class SessionExpiredError(InPostApiError):
    """Raised when the session has expired or is invalid."""

    pass


class ForbiddenError(InPostApiError):
    """Raised when access is forbidden (XSRF token missing/invalid)."""

    pass


class UnauthorizedError(InPostApiError):
    """Raised when authentication is required."""

    pass


class IdentityAdditionLimitReachedError(InPostApiError):
    """Raised when the identity addition limit has been reached."""

    pass


class InvalidOtpCodeError(InPostApiError):
    """Raised when the OTP code is invalid or expired."""

    pass


class RateLimitError(InPostApiError):
    """Raised when too many requests have been made."""

    pass


class ServerError(InPostApiError):
    """Raised when server encounters an error."""

    pass


class ApiClientError(Exception):
    """Exception to indicate a general API client error."""

    pass


class RateLimitedError(ApiClientError):
    """Raised when API returns HTTP 429 (rate limited)."""

    pass


# Mapping of detail types to specific exception classes
DETAIL_TYPE_ERROR_MAP: dict[str, type[InPostApiError]] = {
    "IdentityAdditionLimitReached": IdentityAdditionLimitReachedError,
    "InvalidVerificationCode": InvalidOtpCodeError,
    "VerificationCodeExpired": InvalidOtpCodeError,
    "TooManyRequests": RateLimitError,
}

# Mapping of HTTP status codes to specific exception classes
HTTP_STATUS_ERROR_MAP: dict[int, type[InPostApiError]] = {
    401: UnauthorizedError,
    403: ForbiddenError,
    429: RateLimitError,
    500: ServerError,
    502: ServerError,
    503: ServerError,
}


def parse_api_error(response_body: Any, status_code: int) -> Optional[InPostApiError]:
    """
    Parse an API response and return an appropriate error if present.

    Args:
        response_body: The API response body (dict, string, or other).
        status_code: HTTP status code from the response.

    Returns:
        InPostApiError subclass if error detected, None otherwise.
    """
    # Check if this is an error response based on status code
    is_http_error = status_code >= 400

    # For non-dict responses with error status, create error from status code
    if not isinstance(response_body, dict):
        if is_http_error:
            base_error = InPostApiError.from_response(response_body, status_code)
            # Map to specific exception based on status code
            if status_code in HTTP_STATUS_ERROR_MAP:
                error_class = HTTP_STATUS_ERROR_MAP[status_code]
                return error_class(
                    message=base_error.args[0],
                    error_type=base_error.error_type,
                    status=status_code,
                    detail=base_error.detail,
                    raw_response=response_body,
                )
            return base_error
        return None

    # Check for error indicators in dict response
    error_type = response_body.get("type")
    has_error_status = response_body.get("status", 200) >= 400
    has_error_title = response_body.get("title") in (
        "Unprocessable Entity",
        "Bad Request",
        "Unauthorized",
        "Forbidden",
        "Not Found",
        "Too Many Requests",
        "Internal Server Error",
    )

    if not (error_type or has_error_status or has_error_title or is_http_error):
        return None

    # Parse the error response
    base_error = InPostApiError.from_response(response_body, status_code)

    # Priority 1: Map by detail_type (most specific)
    if base_error.detail_type and base_error.detail_type in DETAIL_TYPE_ERROR_MAP:
        error_class = DETAIL_TYPE_ERROR_MAP[base_error.detail_type]
        return error_class(
            message=base_error.args[0],
            error_type=base_error.error_type,
            status=base_error.status,
            detail=base_error.detail,
            detail_type=base_error.detail_type,
            instance=base_error.instance,
            raw_response=base_error.raw_response,
        )

    # Priority 2: Map by error_type from response
    if base_error.error_type and base_error.error_type in DETAIL_TYPE_ERROR_MAP:
        error_class = DETAIL_TYPE_ERROR_MAP[base_error.error_type]
        return error_class(
            message=base_error.args[0],
            error_type=base_error.error_type,
            status=base_error.status,
            detail=base_error.detail,
            detail_type=base_error.detail_type,
            instance=base_error.instance,
            raw_response=base_error.raw_response,
        )

    # Priority 3: Map by HTTP status code
    effective_status = base_error.status or status_code
    if effective_status in HTTP_STATUS_ERROR_MAP:
        error_class = HTTP_STATUS_ERROR_MAP[effective_status]
        return error_class(
            message=base_error.args[0],
            error_type=base_error.error_type,
            status=effective_status,
            detail=base_error.detail,
            detail_type=base_error.detail_type,
            instance=base_error.instance,
            raw_response=base_error.raw_response,
        )

    return base_error
