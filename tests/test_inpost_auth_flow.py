"""Unit tests for InPost authentication flow module."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.inpost_paczkomaty.inpost_auth_flow import (
    AuthStep,
    AuthTokens,
    DETAIL_TYPE_ERROR_MAP,
    ForbiddenError,
    HTTP_STATUS_ERROR_MAP,
    HttpClient,
    HttpResponse,
    IdentityAdditionLimitReachedError,
    InPostApiError,
    InpostAuth,
    InvalidOtpCodeError,
    PhoneNumberAlreadyRegisteredError,
    RateLimitError,
    ServerError,
    SessionExpiredError,
    UnauthorizedError,
    parse_api_error,
)


# =============================================================================
# InPostApiError Tests
# =============================================================================


class TestInPostApiError:
    """Tests for InPostApiError exception class."""

    def test_init_with_all_parameters(self):
        """Test initialization with all parameters."""
        error = InPostApiError(
            message="Test error",
            error_type="TestError",
            status=400,
            detail="Some detail",
            detail_type="DetailType",
            instance="/api/test",
            raw_response={"key": "value"},
        )

        assert "Test error" in str(error)
        assert error.error_type == "TestError"
        assert error.status == 400
        assert error.detail == "Some detail"
        assert error.detail_type == "DetailType"
        assert error.instance == "/api/test"
        assert error.raw_response == {"key": "value"}

    def test_init_with_minimal_parameters(self):
        """Test initialization with only message."""
        error = InPostApiError("Simple error")

        assert str(error) == "Simple error"
        assert error.error_type is None
        assert error.status is None
        assert error.detail is None
        assert error.detail_type is None
        assert error.instance is None
        assert error.raw_response is None

    def test_str_representation_full(self):
        """Test __str__ with all fields populated."""
        error = InPostApiError(
            message="Error message",
            error_type="ErrorType",
            status=422,
            detail_type="ValidationError",
        )

        result = str(error)
        assert "Error message" in result
        assert "type=ErrorType" in result
        assert "status=422" in result
        assert "detail_type=ValidationError" in result

    def test_str_representation_minimal(self):
        """Test __str__ with minimal fields."""
        error = InPostApiError("Just message")
        assert str(error) == "Just message"

    def test_repr(self):
        """Test __repr__ for debugging."""
        error = InPostApiError(
            message="Test",
            error_type="Type",
            status=500,
            detail_type="Detail",
        )

        repr_str = repr(error)
        assert "InPostApiError" in repr_str
        assert "message='Test'" in repr_str
        assert "status=500" in repr_str
        assert "error_type='Type'" in repr_str
        assert "detail_type='Detail'" in repr_str

    def test_from_response_dict_response(self):
        """Test from_response with dict response body."""
        response_body = {
            "type": "ValidationError",
            "status": 422,
            "title": "Validation Failed",
            "detail": "Invalid phone number",
            "instance": "/api/phone",
        }

        error = InPostApiError.from_response(response_body, 422)

        assert error.error_type == "ValidationError"
        assert error.status == 422
        assert "Validation Failed" in error.args[0]
        assert error.instance == "/api/phone"

    def test_from_response_with_nested_json_detail(self):
        """Test from_response parses nested JSON in detail field."""
        nested_detail = json.dumps({"type": "NestedErrorType", "info": "extra"})
        response_body = {
            "type": "ParentError",
            "status": 400,
            "title": "Bad Request",
            "detail": nested_detail,
        }

        error = InPostApiError.from_response(response_body, 400)

        assert error.detail_type == "NestedErrorType"
        assert "NestedErrorType" in error.args[0]

    def test_from_response_with_plain_text_detail(self):
        """Test from_response with plain text detail."""
        response_body = {
            "type": "Error",
            "status": 400,
            "title": "Bad Request",
            "detail": "Something went wrong",
        }

        error = InPostApiError.from_response(response_body, 400)

        assert "Something went wrong" in error.args[0]
        assert error.detail_type is None

    def test_from_response_non_dict_response(self):
        """Test from_response with non-dict response (e.g., HTML)."""
        html_response = "<html><body>Error page</body></html>"

        error = InPostApiError.from_response(html_response, 500)

        assert error.error_type == "HttpError"
        assert error.status == 500
        assert "Internal Server Error" in error.args[0]

    def test_from_response_empty_response(self):
        """Test from_response with empty/None response."""
        error = InPostApiError.from_response(None, 404)

        assert error.error_type == "HttpError"
        assert error.status == 404

    @pytest.mark.parametrize(
        "status_code,expected_message",
        [
            (400, "Bad Request"),
            (401, "Unauthorized"),
            (403, "Forbidden"),
            (404, "Not Found"),
            (422, "Unprocessable Entity"),
            (429, "Too Many Requests"),
            (500, "Internal Server Error"),
            (502, "Bad Gateway"),
            (503, "Service Unavailable"),
            (418, "HTTP Error 418"),
        ],
    )
    def test_get_http_status_message(self, status_code, expected_message):
        """Test HTTP status code to message mapping."""
        result = InPostApiError._get_http_status_message(status_code)
        assert expected_message in result


class TestSpecificExceptions:
    """Tests for specific exception subclasses."""

    def test_session_expired_error_is_inpost_api_error(self):
        """Test SessionExpiredError inherits from InPostApiError."""
        error = SessionExpiredError("Session expired")
        assert isinstance(error, InPostApiError)

    def test_forbidden_error_is_inpost_api_error(self):
        """Test ForbiddenError inherits from InPostApiError."""
        error = ForbiddenError("Forbidden")
        assert isinstance(error, InPostApiError)

    def test_unauthorized_error_is_inpost_api_error(self):
        """Test UnauthorizedError inherits from InPostApiError."""
        error = UnauthorizedError("Unauthorized")
        assert isinstance(error, InPostApiError)

    def test_identity_addition_limit_reached_error(self):
        """Test IdentityAdditionLimitReachedError."""
        error = IdentityAdditionLimitReachedError("Limit reached")
        assert isinstance(error, InPostApiError)

    def test_phone_number_already_registered_error(self):
        """Test PhoneNumberAlreadyRegisteredError."""
        error = PhoneNumberAlreadyRegisteredError("Already registered")
        assert isinstance(error, InPostApiError)

    def test_invalid_otp_code_error(self):
        """Test InvalidOtpCodeError."""
        error = InvalidOtpCodeError("Invalid code")
        assert isinstance(error, InPostApiError)

    def test_rate_limit_error(self):
        """Test RateLimitError."""
        error = RateLimitError("Too many requests")
        assert isinstance(error, InPostApiError)

    def test_server_error(self):
        """Test ServerError."""
        error = ServerError("Server error")
        assert isinstance(error, InPostApiError)


# =============================================================================
# parse_api_error Tests
# =============================================================================


class TestParseApiError:
    """Tests for parse_api_error function."""

    def test_returns_none_for_success_response(self):
        """Test returns None for successful (non-error) responses."""
        result = parse_api_error({"data": "success"}, 200)
        assert result is None

    def test_returns_none_for_non_dict_success(self):
        """Test returns None for non-dict successful response."""
        result = parse_api_error("OK", 200)
        assert result is None

    def test_returns_error_for_http_error_status(self):
        """Test returns error for HTTP error status codes."""
        result = parse_api_error("Not found", 404)
        assert result is not None
        assert result.status == 404

    def test_maps_detail_type_to_specific_error(self):
        """Test mapping detail_type to specific exception class."""
        nested_detail = json.dumps({"type": "IdentityAdditionLimitReached"})
        response = {
            "type": "Error",
            "status": 422,
            "title": "Error",
            "detail": nested_detail,
        }

        result = parse_api_error(response, 422)

        assert isinstance(result, IdentityAdditionLimitReachedError)

    def test_maps_phone_number_already_registered(self):
        """Test mapping PhoneNumberAlreadyRegistered detail type."""
        nested_detail = json.dumps({"type": "PhoneNumberAlreadyRegistered"})
        response = {
            "type": "Error",
            "status": 422,
            "detail": nested_detail,
        }

        result = parse_api_error(response, 422)

        assert isinstance(result, PhoneNumberAlreadyRegisteredError)

    def test_maps_invalid_verification_code(self):
        """Test mapping InvalidVerificationCode detail type."""
        nested_detail = json.dumps({"type": "InvalidVerificationCode"})
        response = {
            "type": "Error",
            "status": 422,
            "detail": nested_detail,
        }

        result = parse_api_error(response, 422)

        assert isinstance(result, InvalidOtpCodeError)

    def test_maps_verification_code_expired(self):
        """Test mapping VerificationCodeExpired detail type."""
        nested_detail = json.dumps({"type": "VerificationCodeExpired"})
        response = {
            "type": "Error",
            "status": 422,
            "detail": nested_detail,
        }

        result = parse_api_error(response, 422)

        assert isinstance(result, InvalidOtpCodeError)

    def test_maps_too_many_requests_detail_type(self):
        """Test mapping TooManyRequests detail type."""
        nested_detail = json.dumps({"type": "TooManyRequests"})
        response = {
            "type": "Error",
            "status": 429,
            "detail": nested_detail,
        }

        result = parse_api_error(response, 429)

        assert isinstance(result, RateLimitError)

    @pytest.mark.parametrize(
        "status_code,expected_class",
        [
            (401, UnauthorizedError),
            (403, ForbiddenError),
            (429, RateLimitError),
            (500, ServerError),
            (502, ServerError),
            (503, ServerError),
        ],
    )
    def test_maps_http_status_to_specific_error(self, status_code, expected_class):
        """Test mapping HTTP status codes to specific exception classes."""
        result = parse_api_error({"title": "Error"}, status_code)
        assert isinstance(result, expected_class)

    def test_returns_base_error_for_unmapped_status(self):
        """Test returns base InPostApiError for unmapped status codes."""
        result = parse_api_error({"type": "SomeError", "status": 418}, 418)
        assert isinstance(result, InPostApiError)
        assert not isinstance(
            result, (UnauthorizedError, ForbiddenError, RateLimitError, ServerError)
        )

    def test_priority_detail_type_over_status(self):
        """Test detail_type mapping takes priority over status code mapping."""
        nested_detail = json.dumps({"type": "IdentityAdditionLimitReached"})
        response = {
            "type": "Error",
            "status": 500,
            "detail": nested_detail,
        }

        result = parse_api_error(response, 500)

        # Should be IdentityAdditionLimitReached, not ServerError
        assert isinstance(result, IdentityAdditionLimitReachedError)


# =============================================================================
# HttpResponse Tests
# =============================================================================


class TestHttpResponse:
    """Tests for HttpResponse dataclass."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        response = HttpResponse(body={"data": "test"}, status=200)

        assert response.body == {"data": "test"}
        assert response.status == 200
        assert response.cookies == {}
        assert response.headers == {}

    def test_init_with_all_values(self):
        """Test initialization with all values."""
        response = HttpResponse(
            body="content",
            status=201,
            cookies={"session": "abc123"},
            headers={"Content-Type": "application/json"},
        )

        assert response.body == "content"
        assert response.status == 201
        assert response.cookies == {"session": "abc123"}
        assert response.headers == {"Content-Type": "application/json"}

    def test_is_error_false_for_success(self):
        """Test is_error returns False for success status codes."""
        response = HttpResponse(body={}, status=200)
        assert response.is_error is False

        response = HttpResponse(body={}, status=201)
        assert response.is_error is False

        response = HttpResponse(body={}, status=302)
        assert response.is_error is False

    def test_is_error_true_for_client_errors(self):
        """Test is_error returns True for 4xx status codes."""
        response = HttpResponse(body={}, status=400)
        assert response.is_error is True

        response = HttpResponse(body={}, status=404)
        assert response.is_error is True

        response = HttpResponse(body={}, status=422)
        assert response.is_error is True

    def test_is_error_true_for_server_errors(self):
        """Test is_error returns True for 5xx status codes."""
        response = HttpResponse(body={}, status=500)
        assert response.is_error is True

        response = HttpResponse(body={}, status=503)
        assert response.is_error is True

    def test_raise_for_error_no_error(self):
        """Test raise_for_error does nothing for success response."""
        response = HttpResponse(body={"success": True}, status=200)
        response.raise_for_error()  # Should not raise

    def test_raise_for_error_raises_for_error(self):
        """Test raise_for_error raises InPostApiError for error response."""
        response = HttpResponse(
            body={"type": "Error", "status": 400, "title": "Bad Request"},
            status=400,
        )

        with pytest.raises(InPostApiError):
            response.raise_for_error()


# =============================================================================
# AuthTokens Tests
# =============================================================================


class TestAuthTokens:
    """Tests for AuthTokens dataclass."""

    def test_init_with_required_fields(self):
        """Test initialization with required fields only."""
        tokens = AuthTokens(
            access_token="access123",
            refresh_token="refresh456",
        )

        assert tokens.access_token == "access123"
        assert tokens.refresh_token == "refresh456"
        assert tokens.token_type == "Bearer"
        assert tokens.expires_in == 7199
        assert tokens.scope == "openid"
        assert tokens.id_token is None

    def test_init_with_all_fields(self):
        """Test initialization with all fields."""
        tokens = AuthTokens(
            access_token="access123",
            refresh_token="refresh456",
            token_type="CustomType",
            expires_in=3600,
            scope="custom_scope",
            id_token="id_token_value",
        )

        assert tokens.token_type == "CustomType"
        assert tokens.expires_in == 3600
        assert tokens.scope == "custom_scope"
        assert tokens.id_token == "id_token_value"


# =============================================================================
# AuthStep Tests
# =============================================================================


class TestAuthStep:
    """Tests for AuthStep dataclass."""

    def test_init_with_defaults(self):
        """Test initialization with defaults."""
        step = AuthStep(step="TEST_STEP")

        assert step.step == "TEST_STEP"
        assert step.raw_response == {}

    def test_is_onboarded_true(self):
        """Test is_onboarded returns True for ONBOARDED step."""
        step = AuthStep(step="ONBOARDED")
        assert step.is_onboarded is True

    def test_is_onboarded_false(self):
        """Test is_onboarded returns False for other steps."""
        step = AuthStep(step="PROVIDE_PHONE_NUMBER_FOR_LOGIN")
        assert step.is_onboarded is False

    def test_requires_phone_true(self):
        """Test requires_phone returns True for PROVIDE_PHONE_NUMBER_FOR_LOGIN."""
        step = AuthStep(step="PROVIDE_PHONE_NUMBER_FOR_LOGIN")
        assert step.requires_phone is True

    def test_requires_phone_false(self):
        """Test requires_phone returns False for other steps."""
        step = AuthStep(step="ONBOARDED")
        assert step.requires_phone is False

    def test_requires_otp_true(self):
        """Test requires_otp returns True for PROVIDE_PHONE_CODE."""
        step = AuthStep(step="PROVIDE_PHONE_CODE")
        assert step.requires_otp is True

    def test_requires_otp_false(self):
        """Test requires_otp returns False for other steps."""
        step = AuthStep(step="ONBOARDED")
        assert step.requires_otp is False

    def test_requires_email_true_with_hashed_email(self):
        """Test requires_email returns tuple with True and hashed email."""
        step = AuthStep(
            step="PROVIDE_EXISTING_EMAIL_ADDRESS",
            raw_response={"hashedEmail": "abc***@example.com"},
        )

        requires, hashed = step.requires_email
        assert requires is True
        assert hashed == "abc***@example.com"

    def test_requires_email_false(self):
        """Test requires_email returns tuple with False and None."""
        step = AuthStep(step="ONBOARDED")

        requires, hashed = step.requires_email
        assert requires is False
        assert hashed is None


# =============================================================================
# HttpClient Tests
# =============================================================================


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

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"success": True})
        mock_response.cookies = {}
        mock_response.headers = {}

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = HttpResponse(
                body={"success": True},
                status=200,
            )

            response = await client.get(
                "https://api.example.com/test", params={"key": "value"}
            )

            mock_request.assert_called_once_with(
                "GET", "https://api.example.com/test", params={"key": "value"}
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


# =============================================================================
# InpostAuth Tests
# =============================================================================


class TestInpostAuth:
    """Tests for InpostAuth class."""

    def test_init_default_language(self):
        """Test initialization with default language."""
        auth = InpostAuth()

        assert auth._language == "pl"
        assert "pl-PL" in auth._http_client.headers["Accept-Language"]

    def test_init_english_language(self):
        """Test initialization with English language."""
        auth = InpostAuth(language="en")

        assert auth._language == "en"
        assert "en-US" in auth._http_client.headers["Accept-Language"]

    def test_generate_random_hex(self):
        """Test random hex generation."""
        result = InpostAuth._generate_random_hex(8)

        assert len(result) == 16  # 8 bytes = 16 hex chars
        assert all(c in "0123456789abcdef" for c in result)

    def test_generate_random_hex_different_each_time(self):
        """Test random hex generates different values."""
        result1 = InpostAuth._generate_random_hex(8)
        result2 = InpostAuth._generate_random_hex(8)

        assert result1 != result2

    def test_generate_code_verifier(self):
        """Test code verifier generation."""
        result = InpostAuth._generate_code_verifier()

        # Should only contain alphanumeric characters
        assert result.isalnum()
        assert len(result) > 0

    def test_generate_code_challenge(self):
        """Test code challenge generation from verifier."""
        auth = InpostAuth()

        challenge = auth._generate_code_challenge()

        # Challenge should be base64 URL-safe without padding
        assert "=" not in challenge
        assert len(challenge) > 0

    def test_build_oauth_params(self):
        """Test OAuth parameter building."""
        auth = InpostAuth()

        params = auth._build_oauth_params()

        assert params["response_type"] == "code"
        assert params["client_id"] == "inpost-mobile"
        assert params["redirect_uri"] == "https://account.inpost-group.com/callback"
        assert params["scope"] == "openid"
        assert params["code_challenge_method"] == "S256"
        assert "code_challenge" in params
        assert "state" in params
        assert "nonce" in params

    @pytest.mark.asyncio
    async def test_initialize_session(self):
        """Test session initialization."""
        auth = InpostAuth()

        with patch.object(auth._http_client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = HttpResponse(body={}, status=200)

            response = await auth.initialize_session()

            assert mock_get.called
            call_args = mock_get.call_args
            assert "oauth2/authorize" in call_args.kwargs["url"]

        await auth.close()

    @pytest.mark.asyncio
    async def test_fetch_xsrf_token(self):
        """Test XSRF token fetching."""
        auth = InpostAuth()

        mock_cookie = MagicMock()
        mock_cookie.value = "xsrf_token_value"

        with patch.object(auth._http_client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = HttpResponse(
                body={"step": "PROVIDE_PHONE_NUMBER_FOR_LOGIN"},
                status=200,
                cookies={"XSRF-TOKEN": mock_cookie},
            )

            result = await auth.fetch_xsrf_token()

            assert result.step == "PROVIDE_PHONE_NUMBER_FOR_LOGIN"
            assert auth._http_client.headers["X-XSRF-TOKEN"] == "xsrf_token_value"

        await auth.close()

    @pytest.mark.asyncio
    async def test_fetch_xsrf_token_no_cookie(self):
        """Test XSRF token fetching when no cookie present."""
        auth = InpostAuth()

        with patch.object(auth._http_client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = HttpResponse(
                body={"step": "SOME_STEP"},
                status=200,
                cookies={},
            )

            result = await auth.fetch_xsrf_token()

            assert result.step == "SOME_STEP"
            assert "X-XSRF-TOKEN" not in auth._http_client.headers

        await auth.close()

    @pytest.mark.asyncio
    async def test_get_current_step(self):
        """Test getting current step."""
        auth = InpostAuth()

        with patch.object(auth._http_client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = HttpResponse(
                body={"step": "ONBOARDED"},
                status=200,
            )

            result = await auth.get_current_step()

            assert result.step == "ONBOARDED"
            assert result.is_onboarded is True

        await auth.close()

    @pytest.mark.asyncio
    async def test_submit_phone_number_success(self):
        """Test successful phone number submission."""
        auth = InpostAuth()

        with patch.object(
            auth._http_client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = HttpResponse(
                body={"step": "PROVIDE_PHONE_CODE"},
                status=200,
            )

            result = await auth.submit_phone_number("+48123456789")

            assert result.step == "PROVIDE_PHONE_CODE"
            assert result.requires_otp is True

            call_args = mock_post.call_args
            assert call_args.kwargs["json"] == {"phoneNumber": "+48123456789"}

        await auth.close()

    @pytest.mark.asyncio
    async def test_submit_phone_number_limit_reached(self):
        """Test phone number submission with identity limit reached."""
        auth = InpostAuth()

        nested_detail = json.dumps({"type": "IdentityAdditionLimitReached"})

        with patch.object(
            auth._http_client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = HttpResponse(
                body={
                    "type": "UserCatalogueBusinessFailure",
                    "status": 422,
                    "title": "Unprocessable Entity",
                    "detail": nested_detail,
                },
                status=422,
            )

            with pytest.raises(IdentityAdditionLimitReachedError):
                await auth.submit_phone_number("+48123456789")

        await auth.close()

    @pytest.mark.asyncio
    async def test_submit_otp_code_success(self):
        """Test successful OTP code submission."""
        auth = InpostAuth()

        with patch.object(
            auth._http_client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = HttpResponse(
                body={"step": "ONBOARDED"},
                status=200,
            )

            result = await auth.submit_otp_code("123456")

            assert result.step == "ONBOARDED"

            call_args = mock_post.call_args
            assert call_args.kwargs["json"] == {"code": "123456"}

        await auth.close()

    @pytest.mark.asyncio
    async def test_submit_otp_code_invalid(self):
        """Test OTP submission with invalid code."""
        auth = InpostAuth()

        nested_detail = json.dumps({"type": "InvalidVerificationCode"})

        with patch.object(
            auth._http_client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = HttpResponse(
                body={
                    "type": "Error",
                    "status": 422,
                    "detail": nested_detail,
                },
                status=422,
            )

            with pytest.raises(InvalidOtpCodeError):
                await auth.submit_otp_code("000000")

        await auth.close()

    @pytest.mark.asyncio
    async def test_request_email_confirmation(self):
        """Test email confirmation request."""
        auth = InpostAuth()

        with patch.object(
            auth._http_client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = HttpResponse(body={}, status=200)

            response = await auth.request_email_confirmation()

            assert response.status == 200
            call_args = mock_post.call_args
            assert call_args.kwargs["json"] == {"openEmailButtonVisible": True}

        await auth.close()

    @pytest.mark.asyncio
    async def test_wait_for_email_confirmation_success(self):
        """Test waiting for email confirmation - success case."""
        auth = InpostAuth()

        call_count = 0

        async def mock_get_step():
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                return AuthStep(step="ONBOARDED")
            return AuthStep(step="WAITING_FOR_EMAIL")

        with patch.object(auth, "get_current_step", side_effect=mock_get_step):
            result = await auth.wait_for_email_confirmation(
                poll_interval=0.01,
                timeout=1.0,
            )

            assert result is True
            assert call_count >= 3

        await auth.close()

    @pytest.mark.asyncio
    async def test_wait_for_email_confirmation_timeout(self):
        """Test waiting for email confirmation - timeout case."""
        auth = InpostAuth()

        with patch.object(auth, "get_current_step", new_callable=AsyncMock) as mock:
            mock.return_value = AuthStep(step="WAITING_FOR_EMAIL")

            result = await auth.wait_for_email_confirmation(
                poll_interval=0.01,
                timeout=0.05,
            )

            assert result is False

        await auth.close()

    @pytest.mark.asyncio
    async def test_fetch_authorization_code_success(self):
        """Test fetching authorization code."""
        auth = InpostAuth()

        with patch.object(auth._http_client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = HttpResponse(
                body={},
                status=302,
                headers={
                    "Location": "https://example.com/callback?code=auth_code_123&state=xyz"
                },
            )

            code = await auth.fetch_authorization_code()

            assert code == "auth_code_123"

        await auth.close()

    @pytest.mark.asyncio
    async def test_fetch_authorization_code_no_code(self):
        """Test fetching authorization code when not present."""
        auth = InpostAuth()

        with patch.object(auth._http_client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = HttpResponse(
                body={},
                status=302,
                headers={
                    "Location": "https://example.com/callback?error=access_denied"
                },
            )

            with pytest.raises(ValueError, match="Authorization code not found"):
                await auth.fetch_authorization_code()

        await auth.close()

    @pytest.mark.asyncio
    async def test_exchange_code_for_tokens_success(self):
        """Test exchanging authorization code for tokens."""
        auth = InpostAuth()

        with patch.object(
            auth._http_client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = HttpResponse(
                body={
                    "access_token": "access_123",
                    "refresh_token": "refresh_456",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "scope": "openid",
                    "id_token": "id_789",
                },
                status=200,
            )

            tokens = await auth.exchange_code_for_tokens("auth_code")

            assert tokens.access_token == "access_123"
            assert tokens.refresh_token == "refresh_456"
            assert tokens.token_type == "Bearer"
            assert tokens.expires_in == 3600
            assert tokens.id_token == "id_789"

        await auth.close()

    @pytest.mark.asyncio
    async def test_exchange_code_for_tokens_failure(self):
        """Test token exchange failure."""
        auth = InpostAuth()

        with patch.object(
            auth._http_client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = HttpResponse(
                body={"error": "invalid_grant"},
                status=400,
            )

            with pytest.raises((InPostApiError, ValueError)):
                await auth.exchange_code_for_tokens("invalid_code")

        await auth.close()

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing the auth handler."""
        auth = InpostAuth()

        with patch.object(
            auth._http_client, "close", new_callable=AsyncMock
        ) as mock_close:
            await auth.close()
            mock_close.assert_called_once()


# =============================================================================
# Integration Tests
# =============================================================================


class TestAuthFlowIntegration:
    """Integration tests for the complete auth flow."""

    @pytest.mark.asyncio
    async def test_complete_phone_auth_flow(self):
        """Test complete phone authentication flow (mocked)."""
        auth = InpostAuth()

        xsrf_cookie = MagicMock()
        xsrf_cookie.value = "xsrf_token"

        with (
            patch.object(auth._http_client, "get", new_callable=AsyncMock) as mock_get,
            patch.object(
                auth._http_client, "post", new_callable=AsyncMock
            ) as mock_post,
        ):
            # Step 1: Initialize session
            mock_get.return_value = HttpResponse(body={}, status=200)
            await auth.initialize_session()

            # Step 2: Fetch XSRF token
            mock_get.return_value = HttpResponse(
                body={"step": "PROVIDE_PHONE_NUMBER_FOR_LOGIN"},
                status=200,
                cookies={"XSRF-TOKEN": xsrf_cookie},
            )
            step = await auth.fetch_xsrf_token()
            assert step.requires_phone is True

            # Step 3: Submit phone number
            mock_post.return_value = HttpResponse(
                body={"step": "PROVIDE_PHONE_CODE"},
                status=200,
            )
            step = await auth.submit_phone_number("+48123456789")
            assert step.requires_otp is True

            # Step 4: Submit OTP
            mock_post.return_value = HttpResponse(
                body={"step": "ONBOARDED"},
                status=200,
            )
            step = await auth.submit_otp_code("123456")
            assert step.is_onboarded is True

            # Step 5: Get authorization code
            mock_get.return_value = HttpResponse(
                body={},
                status=302,
                headers={"Location": "https://callback?code=auth_code_123"},
            )
            code = await auth.fetch_authorization_code()
            assert code == "auth_code_123"

            # Step 6: Exchange for tokens
            mock_post.return_value = HttpResponse(
                body={
                    "access_token": "access_token_value",
                    "refresh_token": "refresh_token_value",
                },
                status=200,
            )
            tokens = await auth.exchange_code_for_tokens(code)
            assert tokens.access_token == "access_token_value"

        await auth.close()

    @pytest.mark.asyncio
    async def test_email_confirmation_flow(self):
        """Test authentication flow with email confirmation."""
        auth = InpostAuth()

        with (
            patch.object(auth._http_client, "get", new_callable=AsyncMock) as mock_get,
            patch.object(
                auth._http_client, "post", new_callable=AsyncMock
            ) as mock_post,
        ):
            # After OTP, user needs email confirmation
            mock_get.return_value = HttpResponse(
                body={
                    "step": "PROVIDE_EXISTING_EMAIL_ADDRESS",
                    "hashedEmail": "t***@example.com",
                },
                status=200,
            )

            step = await auth.get_current_step()
            requires_email, hashed = step.requires_email
            assert requires_email is True
            assert "***" in hashed

            # Request email confirmation
            mock_post.return_value = HttpResponse(body={}, status=200)
            await auth.request_email_confirmation()

            # Simulate email confirmation complete
            mock_get.return_value = HttpResponse(
                body={"step": "ONBOARDED"},
                status=200,
            )
            step = await auth.get_current_step()
            assert step.is_onboarded is True

        await auth.close()


# =============================================================================
# Error Mapping Verification Tests
# =============================================================================


class TestErrorMappings:
    """Verify error mapping dictionaries are correct."""

    def test_detail_type_error_map_completeness(self):
        """Test DETAIL_TYPE_ERROR_MAP has expected entries."""
        expected_mappings = {
            "IdentityAdditionLimitReached": IdentityAdditionLimitReachedError,
            "PhoneNumberAlreadyRegistered": PhoneNumberAlreadyRegisteredError,
            "InvalidVerificationCode": InvalidOtpCodeError,
            "VerificationCodeExpired": InvalidOtpCodeError,
            "TooManyRequests": RateLimitError,
        }

        for key, expected_class in expected_mappings.items():
            assert key in DETAIL_TYPE_ERROR_MAP
            assert DETAIL_TYPE_ERROR_MAP[key] is expected_class

    def test_http_status_error_map_completeness(self):
        """Test HTTP_STATUS_ERROR_MAP has expected entries."""
        expected_mappings = {
            401: UnauthorizedError,
            403: ForbiddenError,
            429: RateLimitError,
            500: ServerError,
            502: ServerError,
            503: ServerError,
        }

        for status, expected_class in expected_mappings.items():
            assert status in HTTP_STATUS_ERROR_MAP
            assert HTTP_STATUS_ERROR_MAP[status] is expected_class
