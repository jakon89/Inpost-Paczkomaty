"""Unit tests for HttpClient module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.inpost_paczkomaty.exceptions import InPostApiError
from custom_components.inpost_paczkomaty.http_client import HttpClient
from custom_components.inpost_paczkomaty.models import HttpResponse


class TestHttpClient:
    """Tests for HttpClient class."""

    def test_init_default_headers(self):
        """Test initialization sets default headers."""
        client = HttpClient()

        assert "User-Agent" in client.headers
        assert "Mozilla" in client.headers["User-Agent"]

    def test_init_with_auth(self):
        """Test initialization with authentication."""
        client = HttpClient(auth_type="Bearer", auth_value="token123")

        assert client.headers["Authorization"] == "Bearer token123"

    def test_init_with_custom_headers(self):
        """Test initialization with custom headers."""
        client = HttpClient(custom_headers={"X-Custom": "value"})

        assert client.headers["X-Custom"] == "value"
        assert "User-Agent" in client.headers

    def test_init_custom_headers_override_defaults(self):
        """Test custom headers can override defaults."""
        custom_ua = "CustomUserAgent/1.0"
        client = HttpClient(custom_headers={"User-Agent": custom_ua})

        assert client.headers["User-Agent"] == custom_ua

    def test_update_headers(self):
        """Test update_headers method."""
        client = HttpClient()
        client.update_headers({"X-New-Header": "new_value"})

        assert client.headers["X-New-Header"] == "new_value"

    @pytest.mark.asyncio
    async def test_ensure_session_creates_session(self):
        """Test _ensure_session creates a new session."""
        client = HttpClient()

        session = await client._ensure_session()

        assert session is not None
        assert isinstance(session, aiohttp.ClientSession)
        assert not session.closed

        await client.close()

    @pytest.mark.asyncio
    async def test_ensure_session_reuses_existing(self):
        """Test _ensure_session reuses existing session."""
        client = HttpClient()

        session1 = await client._ensure_session()
        session2 = await client._ensure_session()

        assert session1 is session2

        await client.close()

    @pytest.mark.asyncio
    async def test_close_session(self):
        """Test close method closes the session."""
        client = HttpClient()
        await client._ensure_session()

        await client.close()

        assert client.session.closed

    @pytest.mark.asyncio
    async def test_close_no_session(self):
        """Test close does nothing if no session exists."""
        client = HttpClient()
        await client.close()  # Should not raise

    @pytest.mark.asyncio
    async def test_get_request(self):
        """Test GET request method."""
        client = HttpClient()

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = HttpResponse(
                body={"success": True},
                status=200,
            )

            response = await client.get(
                "https://api.example.com/test", params={"key": "value"}
            )

            mock_request.assert_called_once_with(
                "GET",
                "https://api.example.com/test",
                params={"key": "value"},
                custom_headers=None,
            )
            assert response.status == 200

        await client.close()

    @pytest.mark.asyncio
    async def test_post_request_json(self):
        """Test POST request with JSON body."""
        client = HttpClient()

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = HttpResponse(
                body={"created": True},
                status=201,
            )

            response = await client.post(
                "https://api.example.com/create",
                json={"name": "test"},
            )

            mock_request.assert_called_once_with(
                "POST",
                "https://api.example.com/create",
                json={"name": "test"},
                data=None,
                custom_headers=None,
            )
            assert response.status == 201

        await client.close()

    @pytest.mark.asyncio
    async def test_post_request_form_data(self):
        """Test POST request with form data."""
        client = HttpClient()

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = HttpResponse(body={}, status=200)

            await client.post(
                "https://api.example.com/form",
                data={"field": "value"},
            )

            mock_request.assert_called_once_with(
                "POST",
                "https://api.example.com/form",
                json=None,
                data={"field": "value"},
                custom_headers=None,
            )

        await client.close()

    @pytest.mark.asyncio
    async def test_request_timeout(self):
        """Test request timeout raises InPostApiError."""
        client = HttpClient()

        async def slow_request(*args, **kwargs):
            await asyncio.sleep(10)

        with patch.object(
            client, "_ensure_session", new_callable=AsyncMock
        ) as mock_session:
            mock_session_instance = MagicMock()
            mock_context = MagicMock()
            mock_context.__aenter__ = slow_request
            mock_session_instance.request.return_value = mock_context
            mock_session.return_value = mock_session_instance

            with pytest.raises(InPostApiError, match="timed out"):
                await client._request("GET", "https://api.example.com", timeout=0)

        await client.close()

    @pytest.mark.asyncio
    async def test_update_headers_with_active_session(self):
        """Test update_headers updates active session headers."""
        client = HttpClient()

        # Create a session first
        await client._ensure_session()

        # Update headers
        client.update_headers({"X-New": "value"})

        # Check both client and session headers are updated
        assert client.headers["X-New"] == "value"
        assert client.session.headers["X-New"] == "value"

        await client.close()

    @pytest.mark.asyncio
    async def test_update_cookies_with_active_session(self):
        """Test update_cookies updates active session cookies."""
        client = HttpClient()

        # Create a session first
        await client._ensure_session()

        # Update cookies
        client.update_cookies({"test_cookie": "test_value"})

        # The cookies should be in the cookie jar
        # Note: aiohttp's SimpleCookieJar doesn't have a simple dict interface
        # so we just verify the method doesn't raise
        await client.close()

    @pytest.mark.asyncio
    async def test_update_cookies_without_session(self):
        """Test update_cookies does nothing without active session."""
        client = HttpClient()

        # This should not raise even without a session
        client.update_cookies({"test_cookie": "test_value"})

        await client.close()

    def test_build_headers_with_all_params(self):
        """Test _build_headers with all parameters."""
        client = HttpClient()

        headers = client._build_headers(
            auth_type="Bearer",
            auth_value="my_token",
            custom_headers={"X-Custom": "custom_value"},
        )

        assert "User-Agent" in headers
        assert headers["Authorization"] == "Bearer my_token"
        assert headers["X-Custom"] == "custom_value"

    def test_build_headers_no_auth(self):
        """Test _build_headers without authentication."""
        client = HttpClient()

        headers = client._build_headers(
            auth_type=None,
            auth_value=None,
            custom_headers=None,
        )

        assert "User-Agent" in headers
        assert "Authorization" not in headers

    def test_build_headers_partial_auth(self):
        """Test _build_headers with partial auth (only type or value)."""
        client = HttpClient()

        # Only auth_type provided
        headers = client._build_headers(
            auth_type="Bearer",
            auth_value=None,
            custom_headers=None,
        )
        assert "Authorization" not in headers

        # Only auth_value provided
        headers = client._build_headers(
            auth_type=None,
            auth_value="token",
            custom_headers=None,
        )
        assert "Authorization" not in headers

    @pytest.mark.asyncio
    async def test_request_returns_text_when_json_fails(self):
        """Test that _request returns text body when JSON parsing fails."""
        client = HttpClient()

        # Create a mock response that fails JSON parsing
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.cookies = {}
        mock_response.headers = {}

        async def raise_json_error():
            raise ValueError("Invalid JSON")

        async def return_text():
            return "<html>Not JSON</html>"

        mock_response.json = raise_json_error
        mock_response.text = return_text

        # Create async context manager
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.request = MagicMock(return_value=mock_context)

        with patch.object(
            client, "_ensure_session", new_callable=AsyncMock
        ) as mock_ensure:
            mock_ensure.return_value = mock_session

            response = await client._request("GET", "https://example.com")

            assert response.body == "<html>Not JSON</html>"
            assert response.status == 200

        await client.close()

    @pytest.mark.asyncio
    async def test_request_raises_generic_exception(self):
        """Test that _request re-raises generic exceptions."""
        client = HttpClient()

        # Create a mock context manager that raises during __aenter__
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(
            side_effect=ConnectionError("Connection refused")
        )
        mock_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.request = MagicMock(return_value=mock_context)

        with patch.object(
            client, "_ensure_session", new_callable=AsyncMock
        ) as mock_ensure:
            mock_ensure.return_value = mock_session

            with pytest.raises(ConnectionError, match="Connection refused"):
                await client._request("GET", "https://example.com")

        await client.close()
