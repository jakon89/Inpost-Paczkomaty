"""
InPost Authentication Module for Home Assistant.

This module handles the OAuth2 authentication flow for InPost services.
"""

import asyncio
import base64
import binascii
import hashlib
import logging
import os
import re
import time

from .const import (
    API_BASE_URL,
    OAUTH_BASE_URL,
    OAUTH_CLIENT_ID,
    OAUTH_REDIRECT_URI,
)
from .http_client import HttpClient
from .models import AuthStep, AuthTokens, HttpResponse
from .utils import get_language_code

_LOGGER = logging.getLogger(__name__)


class InpostAuth:
    """
    InPost OAuth2 Authentication Handler.

    Manages the complete authentication flow including:
    - OAuth2 initialization with PKCE
    - Phone number verification via OTP
    - Email confirmation
    - Token retrieval
    """

    # Use constants from const.py
    OAUTH_BASE_URL = OAUTH_BASE_URL
    API_BASE_URL = API_BASE_URL
    CLIENT_ID = OAUTH_CLIENT_ID
    REDIRECT_URI = OAUTH_REDIRECT_URI

    def __init__(self, language: str = "pl") -> None:
        """Initialize the InPost authentication handler."""
        self._language = language
        self._language_code = get_language_code(language)
        self._http_client = HttpClient(
            custom_headers={"Accept-Language": self._language_code}
        )
        self._flow_state = self._generate_random_hex(8)
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
        self._http_client.update_cookies({"NEXT_LOCALE": self._language_code})

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
