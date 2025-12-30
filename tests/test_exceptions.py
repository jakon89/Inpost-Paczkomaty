"""Unit tests for InPost API exceptions module."""

import json

import pytest

from custom_components.inpost_paczkomaty.exceptions import (
    DETAIL_TYPE_ERROR_MAP,
    HTTP_STATUS_ERROR_MAP,
    ApiClientError,
    ForbiddenError,
    IdentityAdditionLimitReachedError,
    InPostApiError,
    InvalidOtpCodeError,
    RateLimitedError,
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


# =============================================================================
# Specific Exception Subclasses Tests
# =============================================================================


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

    def test_api_client_error(self):
        """Test ApiClientError."""
        error = ApiClientError("Client error")
        assert isinstance(error, Exception)
        assert str(error) == "Client error"

    def test_rate_limited_error(self):
        """Test RateLimitedError inherits from ApiClientError."""
        error = RateLimitedError("Rate limited")
        assert isinstance(error, ApiClientError)
        assert isinstance(error, Exception)
        assert str(error) == "Rate limited"


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

    def test_non_dict_response_with_mapped_status_code(self):
        """Test non-dict response with status code in HTTP_STATUS_ERROR_MAP."""
        # Test 401 - should return UnauthorizedError
        result = parse_api_error("Unauthorized access", 401)
        assert isinstance(result, UnauthorizedError)
        assert result.status == 401

        # Test 403 - should return ForbiddenError
        result = parse_api_error("Access denied", 403)
        assert isinstance(result, ForbiddenError)
        assert result.status == 403

        # Test 500 - should return ServerError
        result = parse_api_error("<html>Server Error</html>", 500)
        assert isinstance(result, ServerError)
        assert result.status == 500

    def test_maps_error_type_to_specific_error(self):
        """Test mapping error_type field to specific exception class."""
        # When error_type matches a key in DETAIL_TYPE_ERROR_MAP
        response = {
            "type": "IdentityAdditionLimitReached",
            "status": 422,
            "title": "Error",
        }

        result = parse_api_error(response, 422)

        assert isinstance(result, IdentityAdditionLimitReachedError)
        assert result.error_type == "IdentityAdditionLimitReached"


# =============================================================================
# Error Mapping Verification Tests
# =============================================================================


class TestErrorMappings:
    """Verify error mapping dictionaries are correct."""

    def test_detail_type_error_map_completeness(self):
        """Test DETAIL_TYPE_ERROR_MAP has expected entries."""
        expected_mappings = {
            "IdentityAdditionLimitReached": IdentityAdditionLimitReachedError,
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
