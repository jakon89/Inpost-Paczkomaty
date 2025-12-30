"""
HTTP client for InPost API requests.

This module provides an async HTTP client with session management,
custom headers, and cookie handling.
"""

import asyncio
import logging
from typing import Optional

import aiohttp
from aiohttp.resolver import ThreadedResolver

from .exceptions import InPostApiError
from .models import HttpResponse

_LOGGER = logging.getLogger(__name__)


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
        custom_headers: Optional[dict] = None,
    ) -> HttpResponse:
        """
        Execute an HTTP request.

        Args:
            method: HTTP method (GET, POST, etc.).
            url: Request URL.
            params: Query parameters.
            json: JSON body data.
            data: Form data.
            timeout: Request timeout in seconds.

        Returns:
            HttpResponse dataclass with response data.

        Raises:
            InPostApiError: If request times out or fails.
        """
        session = await self._ensure_session()
        _LOGGER.debug("Making %s request to %s", method, url)
        headers = {**self.headers, **(custom_headers or {})}
        _LOGGER.debug("Headers: %s", headers)
        try:
            async with asyncio.timeout(timeout):
                async with session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json,
                    data=data,
                    allow_redirects=False,
                    headers=headers,
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

    async def get(
        self,
        url: str,
        params: Optional[dict] = None,
        custom_headers: Optional[dict] = None,
    ) -> HttpResponse:
        """
        Execute a GET request.

        Args:
            url: Request URL.
            params: Query parameters.

        Returns:
            HttpResponse dataclass with response data.
        """
        return await self._request(
            "GET", url, params=params, custom_headers=custom_headers
        )

    async def post(
        self,
        url: str,
        json: Optional[dict] = None,
        data: Optional[dict] = None,
        custom_headers: Optional[dict] = None,
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
        return await self._request(
            "POST", url, json=json, data=data, custom_headers=custom_headers
        )

    async def close(self) -> None:
        """Close the HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()
            _LOGGER.debug("HTTP session closed")
