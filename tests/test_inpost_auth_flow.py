"""Unit tests for InPost authentication flow module."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.inpost_paczkomaty.exceptions import (
    IdentityAdditionLimitReachedError,
    InPostApiError,
    InvalidOtpCodeError,
)
from custom_components.inpost_paczkomaty.inpost_auth_flow import InpostAuth
from custom_components.inpost_paczkomaty.models import AuthStep, HttpResponse


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

            await auth.initialize_session()

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
    async def test_exchange_code_for_tokens_missing_access_token(self):
        """Test token exchange with missing access_token in response."""
        auth = InpostAuth()

        with patch.object(
            auth._http_client, "post", new_callable=AsyncMock
        ) as mock_post:
            # Response is successful but doesn't contain access_token
            mock_post.return_value = HttpResponse(
                body={"refresh_token": "refresh_456"},
                status=200,
            )

            with pytest.raises(ValueError, match="Token exchange failed"):
                await auth.exchange_code_for_tokens("auth_code")

        await auth.close()

    @pytest.mark.asyncio
    async def test_exchange_code_for_tokens_non_dict_response(self):
        """Test token exchange with non-dict response body."""
        auth = InpostAuth()

        with patch.object(
            auth._http_client, "post", new_callable=AsyncMock
        ) as mock_post:
            # Response is successful but body is not a dict
            mock_post.return_value = HttpResponse(
                body="Invalid response",
                status=200,
            )

            with pytest.raises(ValueError, match="Token exchange failed"):
                await auth.exchange_code_for_tokens("auth_code")

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
