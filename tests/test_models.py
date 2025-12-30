"""Unit tests for InPost data models."""

import pytest

from custom_components.inpost_paczkomaty.exceptions import InPostApiError
from custom_components.inpost_paczkomaty.models import (
    AuthStep,
    AuthTokens,
    HttpResponse,
)


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
