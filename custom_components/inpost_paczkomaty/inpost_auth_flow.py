"""
InPost Authentication Module for Home Assistant.

This module handles the OAuth2 authentication flow for InPost services.
It includes an HTTP client and authentication workflow management.
"""

import asyncio
import base64
import binascii
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import aiohttp
from aiohttp.resolver import ThreadedResolver

_LOGGER = logging.getLogger(__name__)


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


class PhoneNumberAlreadyRegisteredError(InPostApiError):
    """Raised when the phone number is already registered."""

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


# Mapping of detail types to specific exception classes
DETAIL_TYPE_ERROR_MAP = {
    "IdentityAdditionLimitReached": IdentityAdditionLimitReachedError,
    "PhoneNumberAlreadyRegistered": PhoneNumberAlreadyRegisteredError,
    "InvalidVerificationCode": InvalidOtpCodeError,
    "VerificationCodeExpired": InvalidOtpCodeError,
    "TooManyRequests": RateLimitError,
}

# Mapping of HTTP status codes to specific exception classes
HTTP_STATUS_ERROR_MAP = {
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


@dataclass
class HttpResponse:
    """HTTP response data container."""

    body: Any
    status: int
    cookies: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)

    @property
    def is_error(self) -> bool:
        """Check if response indicates an error."""
        return self.status >= 400

    def raise_for_error(self) -> None:
        """
        Raise an InPostApiError if the response contains an error.

        Raises:
            InPostApiError: If the response body contains error information.
        """
        error = parse_api_error(self.body, self.status)
        if error:
            raise error


@dataclass
class AuthTokens:
    """OAuth2 token data container."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 7199
    scope: str = "openid"
    id_token: Optional[str] = None


@dataclass
class AuthStep:
    """Authentication step status container."""

    step: str
    raw_response: dict = field(default_factory=dict)

    @property
    def is_onboarded(self) -> bool:
        """Check if user has completed onboarding."""
        return self.step == "ONBOARDED"

    @property
    def requires_phone(self) -> bool:
        """Check if phone number input is required."""
        return self.step == "PROVIDE_PHONE_NUMBER_FOR_LOGIN"

    @property
    def requires_otp(self) -> bool:
        """Check if OTP code input is required."""
        return self.step == "PROVIDE_PHONE_CODE"

    @property
    def requires_email(self) -> tuple[bool, Optional[str]]:
        """Check if email confirmation is required and return hashed email."""
        if self.step == "PROVIDE_EXISTING_EMAIL_ADDRESS":
            return True, self.raw_response.get("hashedEmail", "")
        return False, None


class HttpClient:
    """
    Async HTTP client for making API requests.

    Handles session management, headers, and cookies for HTTP requests.
    """

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
        )
    }

    def __init__(
        self,
        auth_type: Optional[str] = None,
        auth_value: Optional[str] = None,
        custom_headers: Optional[dict] = None,
    ) -> None:
        """
        Initialize the HTTP client with optional authentication.

        Args:
            auth_type: Type of authentication (e.g., "Bearer").
            auth_value: Authentication token value.
            custom_headers: Additional headers to include in requests.
        """
        self.headers = self._build_headers(auth_type, auth_value, custom_headers)
        self.session: Optional[aiohttp.ClientSession] = None

    def _build_headers(
        self,
        auth_type: Optional[str],
        auth_value: Optional[str],
        custom_headers: Optional[dict],
    ) -> dict:
        """
        Build the headers dictionary for requests.

        Args:
            auth_type: Type of authentication.
            auth_value: Authentication token value.
            custom_headers: Additional custom headers.

        Returns:
            Dictionary containing all headers.
        """
        headers = {**self.DEFAULT_HEADERS}

        if custom_headers:
            headers.update(custom_headers)

        if auth_type and auth_value:
            headers["Authorization"] = f"{auth_type} {auth_value}"

        return headers

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """
        Ensure an active aiohttp session exists.

        Returns:
            Active ClientSession instance.
        """
        if self.session is None or self.session.closed:
            connector = aiohttp.TCPConnector(resolver=ThreadedResolver())
            self.session = aiohttp.ClientSession(
                headers=self.headers, connector=connector
            )
        return self.session

    def update_headers(self, headers: dict) -> None:
        """
        Update the session headers with new values.

        Args:
            headers: Dictionary of headers to add/update.
        """
        self.headers.update(headers)
        if self.session and not self.session.closed:
            self.session.headers.update(headers)

    def update_cookies(self, cookies: dict) -> None:
        """
        Update the session cookies.

        Args:
            cookies: Dictionary of cookies to add/update.
        """
        if self.session and not self.session.closed:
            self.session.cookie_jar.update_cookies(cookies)

    async def _request(
        self,
        method: str,
        url: str,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
        data: Optional[dict] = None,
        timeout: Optional[int] = 30,
    ) -> HttpResponse:
        """
        Execute an HTTP request.

        Args:
            method: HTTP method (GET, POST, etc.).
            url: Request URL.
            params: Query parameters.
            json: JSON body data.
            data: Form data.

        Returns:
            HttpResponse dataclass with response data.
        """
        session = await self._ensure_session()
        _LOGGER.debug("Making %s request to %s", method, url)

        try:
            async with asyncio.timeout(timeout):
                async with session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json,
                    data=data,
                    allow_redirects=False,
                ) as response:
                    try:
                        body = await response.json()
                    except Exception:
                        body = await response.text()

                    _LOGGER.debug("Response status: %d", response.status)
                    return HttpResponse(
                        body=body,
                        status=response.status,
                        cookies=response.cookies,
                        headers=response.headers,
                    )
        except TimeoutError as e:
            _LOGGER.warning("Request timed out")
            raise InPostApiError("Request timed out") from e
        except Exception as e:
            _LOGGER.error("Error making request: %s", e)
            raise e

    async def get(self, url: str, params: Optional[dict] = None) -> HttpResponse:
        """
        Execute a GET request.

        Args:
            url: Request URL.
            params: Query parameters.

        Returns:
            HttpResponse dataclass with response data.
        """
        return await self._request("GET", url, params=params)

    async def post(
        self, url: str, json: Optional[dict] = None, data: Optional[dict] = None
    ) -> HttpResponse:
        """
        Execute a POST request.

        Args:
            url: Request URL.
            json: JSON body data.
            data: Form data.

        Returns:
            HttpResponse dataclass with response data.
        """
        return await self._request("POST", url, json=json, data=data)

    async def close(self) -> None:
        """Close the HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()
            _LOGGER.debug("HTTP session closed")


class InpostAuth:
    """
    InPost OAuth2 Authentication Handler.

    Manages the complete authentication flow including:
    - OAuth2 initialization with PKCE
    - Phone number verification via OTP
    - Email confirmation
    - Token retrieval
    """

    # Base URLs for InPost services
    OAUTH_BASE_URL = "https://account.inpost-group.com"
    API_BASE_URL = "https://api-inmobile-pl.easypack24.net"

    # OAuth2 client configuration
    CLIENT_ID = "inpost-mobile"
    REDIRECT_URI = "https://account.inpost-group.com/callback"

    def __init__(self, language: str = "pl") -> None:
        """Initialize the InPost authentication handler."""
        self._http_client = HttpClient(
            custom_headers={"Accept-Language": "pl-PL" if language == "pl" else "en-US"}
        )
        self._flow_state = self._generate_random_hex(8)
        self._language = language
        self._code_verifier = self._generate_code_verifier()
        _LOGGER.debug("InpostAuth initialized with flow state: %s", self._flow_state)

    @staticmethod
    def _generate_random_hex(length: int) -> str:
        """
        Generate a random hexadecimal string.

        Args:
            length: Number of random bytes to generate.

        Returns:
            Hexadecimal string representation.
        """
        return binascii.hexlify(os.urandom(length)).decode("utf-8")

    @staticmethod
    def _generate_code_verifier() -> str:
        """
        Generate a PKCE code verifier.

        Returns:
            URL-safe code verifier string.
        """
        verifier = base64.urlsafe_b64encode(os.urandom(39)).decode("utf-8")
        # Remove non-alphanumeric characters for URL safety
        return re.sub(r"[^a-zA-Z0-9]+", "", verifier)

    def _generate_code_challenge(self) -> str:
        """
        Generate a PKCE code challenge from the code verifier.

        Returns:
            Base64 URL-safe encoded SHA256 hash of the code verifier.
        """
        digest = hashlib.sha256(self._code_verifier.encode("utf-8")).digest()
        challenge = base64.urlsafe_b64encode(digest).decode("utf-8")
        # Remove padding characters per PKCE spec
        return challenge.replace("=", "")

    def _build_oauth_params(self) -> dict:
        """
        Build OAuth2 authorization request parameters.

        Returns:
            Dictionary of OAuth2 parameters.
        """
        return {
            "response_type": "code",
            "client_id": self.CLIENT_ID,
            "redirect_uri": self.REDIRECT_URI,
            "scope": "openid",
            "code_challenge": self._generate_code_challenge(),
            "code_challenge_method": "S256",
            "theme": "light",
            "state": self._flow_state,
            "nonce": self._generate_random_hex(8),
            "lang": self._language,
            "response_mode": "query",
        }

    async def initialize_session(self) -> HttpResponse:
        """
        Step 1: Initialize OAuth session and get cookies.

        Makes initial request to OAuth2 authorize endpoint to establish
        session cookies required for the authentication flow.

        Returns:
            HttpResponse with session initialization result.
        """
        _LOGGER.info("Initializing OAuth session")
        url = f"{self.OAUTH_BASE_URL}/oauth2/authorize"
        response = await self._http_client.get(
            url=url, params=self._build_oauth_params()
        )
        _LOGGER.debug("Session initialized with status: %d", response.status)
        return response

    async def fetch_xsrf_token(self) -> AuthStep:
        """
        Step 2: Fetch and set the XSRF token.

        Retrieves the XSRF token from the onboarding steps endpoint
        and updates the HTTP client headers with it.

        Returns:
            AuthStep with current onboarding step status.
        """
        _LOGGER.info("Fetching XSRF token")
        url = f"{self.OAUTH_BASE_URL}/api/auth/onboarding/steps"
        response = await self._http_client.get(url=url)

        # Extract and set XSRF token from cookies
        xsrf_cookie = response.cookies.get("XSRF-TOKEN")
        if xsrf_cookie:
            self._http_client.update_headers({"X-XSRF-TOKEN": xsrf_cookie.value})
            _LOGGER.debug("XSRF token set successfully")

        # Set locale cookie for Polish language
        self._http_client.update_cookies({"NEXT_LOCALE": "pl-PL"})

        step = response.body.get("step", "") if isinstance(response.body, dict) else ""
        _LOGGER.info("Current step: %s", step)
        return AuthStep(step=step, raw_response=response.body)

    async def get_current_step(self) -> AuthStep:
        """
        Get the current onboarding step status.

        Returns:
            AuthStep with current step information.
        """
        url = f"{self.OAUTH_BASE_URL}/api/auth/onboarding/steps"
        response = await self._http_client.get(url=url)
        step = response.body.get("step", "") if isinstance(response.body, dict) else ""
        _LOGGER.debug("Current step: %s", step)
        return AuthStep(step=step, raw_response=response.body)

    async def submit_phone_number(self, phone_number: str) -> AuthStep:
        """
        Step 3: Submit phone number to receive OTP code.

        Args:
            phone_number: Phone number with country code (e.g., "+48123456789").

        Returns:
            AuthStep with next step information.

        Raises:
            IdentityAdditionLimitReachedError: When identity addition limit reached.
            PhoneNumberAlreadyRegisteredError: When phone is already registered.
            InPostApiError: For other API errors.
        """
        _LOGGER.info("Submitting phone number")
        url = f"{self.OAUTH_BASE_URL}/api/auth/onboarding/steps/phoneNumber"
        response = await self._http_client.post(
            url=url, json={"phoneNumber": phone_number}
        )

        # Check for API errors
        response.raise_for_error()

        step = response.body.get("step", "") if isinstance(response.body, dict) else ""
        _LOGGER.debug("Phone submission result step: %s", step)
        return AuthStep(step=step, raw_response=response.body)

    async def submit_otp_code(self, code: str) -> AuthStep:
        """
        Step 4: Submit OTP verification code.

        Args:
            code: The OTP code received via SMS.

        Returns:
            AuthStep with next step information.

        Raises:
            InvalidOtpCodeError: When OTP code is invalid or expired.
            InPostApiError: For other API errors.
        """
        _LOGGER.info("Submitting OTP code")
        url = f"{self.OAUTH_BASE_URL}/api/auth/onboarding/steps/phoneVerificationCode"
        response = await self._http_client.post(url=url, json={"code": code})

        # Check for API errors
        response.raise_for_error()

        step = response.body.get("step", "") if isinstance(response.body, dict) else ""
        _LOGGER.debug("OTP submission result step: %s", step)
        return AuthStep(step=step, raw_response=response.body)

    async def request_email_confirmation(self) -> HttpResponse:
        """
        Step 5: Request email confirmation to be sent.

        Called when step is PROVIDE_EXISTING_EMAIL_ADDRESS.

        Returns:
            HttpResponse with confirmation request status.

        Raises:
            InPostApiError: For API errors.
        """
        _LOGGER.info("Requesting email confirmation")
        url = f"{self.OAUTH_BASE_URL}/api/auth/onboarding/steps/sendAuthenticationCodeToExistingEmail"
        response = await self._http_client.post(
            url=url, json={"openEmailButtonVisible": True}
        )

        # Check for API errors
        response.raise_for_error()

        _LOGGER.debug("Email confirmation request sent")
        return response

    async def wait_for_email_confirmation(
        self, poll_interval: float = 2.0, timeout: float = 300.0
    ) -> bool:
        """
        Step 6: Poll until user confirms email.

        Continuously checks the onboarding status until the user
        confirms their email (step becomes ONBOARDED).

        Args:
            poll_interval: Seconds between status checks.
            timeout: Maximum seconds to wait for confirmation.

        Returns:
            True if email was confirmed, False if timeout occurred.
        """
        _LOGGER.info("Waiting for email confirmation (timeout: %ds)", timeout)
        start_time = time.time()

        while (time.time() - start_time) < timeout:
            auth_step = await self.get_current_step()

            if auth_step.is_onboarded:
                _LOGGER.info("Email confirmed successfully")
                return True

            _LOGGER.debug(
                "Still waiting for email confirmation, step: %s", auth_step.step
            )
            await asyncio.sleep(poll_interval)

        _LOGGER.warning("Email confirmation timeout after %ds", timeout)
        return False

    async def fetch_authorization_code(self) -> str:
        """
        Fetch the OAuth2 authorization code after onboarding.

        Makes a request to the authorize endpoint to get the
        authorization code from the redirect location.

        Returns:
            OAuth2 authorization code.

        Raises:
            ValueError: If authorization code cannot be extracted.
        """
        _LOGGER.info("Fetching authorization code")
        url = f"{self.OAUTH_BASE_URL}/oauth2/authorize"
        response = await self._http_client.get(
            url=url, params=self._build_oauth_params()
        )

        # Extract authorization code from redirect location
        location = response.headers.get("Location", "")
        if "code=" not in location:
            _LOGGER.error("Authorization code not found in redirect location")
            raise ValueError("Authorization code not found in redirect location")

        code = location.split("code=")[1].split("&")[0]
        _LOGGER.debug("Authorization code obtained")
        return code

    async def exchange_code_for_tokens(self, authorization_code: str) -> AuthTokens:
        """
        Step 7: Exchange authorization code for access and refresh tokens.

        Args:
            authorization_code: The OAuth2 authorization code.

        Returns:
            AuthTokens dataclass with token data.

        Raises:
            InPostApiError: If token exchange fails with API error.
            ValueError: If token exchange fails for other reasons.
        """
        _LOGGER.info("Exchanging authorization code for tokens")
        url = f"{self.API_BASE_URL}/global/oauth2/token"
        response = await self._http_client.post(
            url=url,
            data={
                "client_id": self.CLIENT_ID,
                "code": authorization_code,
                "code_verifier": self._code_verifier,
                "grant_type": "authorization_code",
                "redirect_uri": self.REDIRECT_URI,
            },
        )

        # Check for API errors
        response.raise_for_error()

        if not isinstance(response.body, dict) or "access_token" not in response.body:
            _LOGGER.error("Token exchange failed: %s", response.body)
            raise ValueError(f"Token exchange failed: {response.body}")

        _LOGGER.info("Tokens obtained successfully")
        return AuthTokens(
            access_token=response.body["access_token"],
            refresh_token=response.body["refresh_token"],
            token_type=response.body.get("token_type", "Bearer"),
            expires_in=response.body.get("expires_in", 7199),
            scope=response.body.get("scope", "openid"),
            id_token=response.body.get("id_token"),
        )

    async def close(self) -> None:
        """Close the HTTP client session."""
        await self._http_client.close()
        _LOGGER.debug("InpostAuth session closed")


async def main() -> None:
    """
    Manual authentication flow for testing.

    This function demonstrates the complete InPost authentication process
    and can be run standalone for testing purposes.
    """
    # Configure logging for standalone execution
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    auth = InpostAuth()

    try:
        # Step 1: Initialize session
        _LOGGER.info("Step 1: Initializing OAuth session")
        await auth.initialize_session()

        # Step 2: Get XSRF token
        _LOGGER.info("Step 2: Fetching XSRF token")
        auth_step = await auth.fetch_xsrf_token()
        _LOGGER.info("Current step: %s", auth_step.step)

        # Step 3: Submit phone number
        phone_number = input(
            "Enter phone number (with country code, e.g. +48123456789): "
        )
        _LOGGER.info("Step 3: Submitting phone number")
        auth_step = await auth.submit_phone_number(phone_number)
        _LOGGER.info("Result: %s", auth_step.raw_response)

        # Step 4: Submit OTP code
        otp_code = input("Enter OTP code from SMS: ")
        _LOGGER.info("Step 4: Submitting OTP code")
        auth_step = await auth.submit_otp_code(otp_code)
        _LOGGER.info("Result: %s", auth_step.raw_response)

        # Check current step
        auth_step = await auth.get_current_step()

        # Step 5: Handle email confirmation if required
        requires_email, hashed_email = auth_step.requires_email
        if requires_email:
            _LOGGER.info(
                f"Step 5: Email confirmation required, sending request to {hashed_email}"
            )
            response = await auth.request_email_confirmation()
            _LOGGER.info("Response: %s", response.body)
            if response.status != 200:
                _LOGGER.error("Failed to request email confirmation")
                return

            # Step 6: Wait for email confirmation
            _LOGGER.info("Step 6: Waiting for email confirmation (check your email)")
            confirmed = await auth.wait_for_email_confirmation()

            if not confirmed:
                _LOGGER.error("Email confirmation timeout!")
                return

        # Step 7: Get tokens
        _LOGGER.info("Step 7: Fetching authorization code")
        auth_code = await auth.fetch_authorization_code()
        _LOGGER.info("Authorization code: %s", auth_code)

        _LOGGER.info("Exchanging code for tokens")
        tokens = await auth.exchange_code_for_tokens(auth_code)
        _LOGGER.info("Access token: %s...", tokens.access_token[:50])
        _LOGGER.info("Refresh token: %s...", tokens.refresh_token[:20])
        _LOGGER.info("Expires in: %d seconds", tokens.expires_in)

    except ForbiddenError as e:
        _LOGGER.error(
            "Access forbidden (403): XSRF token may be missing or session expired. "
            "Try restarting the authentication flow. Details: %s",
            e,
        )
    except UnauthorizedError as e:
        _LOGGER.error(
            "Unauthorized (401): Session expired or invalid. "
            "Please restart the authentication flow. Details: %s",
            e,
        )
    except RateLimitError as e:
        _LOGGER.error(
            "Rate limit exceeded (429): Too many requests. "
            "Please wait before trying again. Details: %s",
            e,
        )
    except InvalidOtpCodeError as e:
        _LOGGER.error(
            "Invalid OTP code: The code is incorrect or has expired. "
            "Please request a new code. Details: %s",
            e,
        )
    except IdentityAdditionLimitReachedError as e:
        _LOGGER.error(
            "Identity limit reached: You have reached the maximum number of "
            "device registrations. Details: %s",
            e,
        )
    except PhoneNumberAlreadyRegisteredError as e:
        _LOGGER.error(
            "Phone number already registered: This phone number is already "
            "associated with another account. Details: %s",
            e,
        )
    except InPostApiError as e:
        _LOGGER.error(
            "InPost API error: %s | Status: %s | Type: %s", e, e.status, e.error_type
        )
        if e.raw_response:
            _LOGGER.debug("Raw response: %s", e.raw_response)
    except ValueError as e:
        _LOGGER.error("Validation error: %s", e)
    except Exception as e:
        _LOGGER.exception("Unexpected error during authentication: %s", e)

    finally:
        await auth.close()


if __name__ == "__main__":
    asyncio.run(main())
