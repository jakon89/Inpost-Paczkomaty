"""Unit tests for InPost data models."""

import pytest

from custom_components.inpost_paczkomaty.exceptions import InPostApiError
from custom_components.inpost_paczkomaty.models import (
    AuthStep,
    AuthTokens,
    HttpResponse,
    InPostParcelLocker,
    InPostParcelLockerPointCoordinates,
    ParcelLockerListResponse,
    ProfileDelivery,
    ProfileDeliveryPoint,
    ProfileDeliveryPoints,
    UserProfile,
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


# =============================================================================
# ProfileDeliveryPoint Tests
# =============================================================================


class TestProfileDeliveryPoint:
    """Tests for ProfileDeliveryPoint dataclass."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        point = ProfileDeliveryPoint(name="GDA117M")

        assert point.name == "GDA117M"
        assert point.type == "PL"
        assert point.address_lines == []
        assert point.active is True
        assert point.preferred is False

    def test_init_with_all_values(self):
        """Test initialization with all values."""
        point = ProfileDeliveryPoint(
            name="GDA117M",
            type="PL",
            address_lines=["Wieżycka 8", "obiekt mieszkalny", "80-180 Gdańsk"],
            active=True,
            preferred=True,
        )

        assert point.name == "GDA117M"
        assert point.type == "PL"
        assert len(point.address_lines) == 3
        assert point.active is True
        assert point.preferred is True

    def test_description_property(self):
        """Test description property joins address lines."""
        point = ProfileDeliveryPoint(
            name="GDA117M",
            address_lines=["Wieżycka 8", "obiekt mieszkalny", "80-180 Gdańsk"],
        )

        assert point.description == "Wieżycka 8, obiekt mieszkalny, 80-180 Gdańsk"

    def test_description_empty_address_lines(self):
        """Test description returns empty string for empty address lines."""
        point = ProfileDeliveryPoint(name="GDA117M")
        assert point.description == ""


# =============================================================================
# UserProfile Tests
# =============================================================================


class TestUserProfile:
    """Tests for UserProfile dataclass."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        profile = UserProfile()

        assert profile.personal is None
        assert profile.delivery is None
        assert profile.shopping_active is False

    def test_get_favorite_locker_codes_empty(self):
        """Test get_favorite_locker_codes returns empty list when no delivery."""
        profile = UserProfile()
        assert profile.get_favorite_locker_codes() == []

    def test_get_favorite_locker_codes_no_points(self):
        """Test get_favorite_locker_codes with delivery but no points."""
        profile = UserProfile(delivery=ProfileDelivery())
        assert profile.get_favorite_locker_codes() == []

    def test_get_favorite_locker_codes_active_only(self):
        """Test get_favorite_locker_codes returns only active lockers."""
        points = ProfileDeliveryPoints(
            items=[
                ProfileDeliveryPoint(name="GDA117M", active=True),
                ProfileDeliveryPoint(name="GDA03B", active=False),
                ProfileDeliveryPoint(name="GDA145M", active=True),
            ]
        )
        profile = UserProfile(delivery=ProfileDelivery(points=points))

        result = profile.get_favorite_locker_codes()

        assert len(result) == 2
        assert "GDA117M" in result
        assert "GDA145M" in result
        assert "GDA03B" not in result

    def test_get_favorite_locker_codes_preferred_first(self):
        """Test get_favorite_locker_codes puts preferred lockers first."""
        points = ProfileDeliveryPoints(
            items=[
                ProfileDeliveryPoint(name="GDA145M", active=True, preferred=False),
                ProfileDeliveryPoint(name="GDA03B", active=True, preferred=False),
                ProfileDeliveryPoint(name="GDA117M", active=True, preferred=True),
            ]
        )
        profile = UserProfile(delivery=ProfileDelivery(points=points))

        result = profile.get_favorite_locker_codes()

        assert len(result) == 3
        # Preferred should be first
        assert result[0] == "GDA117M"

    def test_get_favorite_locker_codes_full_scenario(self):
        """Test get_favorite_locker_codes with realistic data."""
        points = ProfileDeliveryPoints(
            items=[
                ProfileDeliveryPoint(
                    name="GDA145M",
                    type="PL",
                    address_lines=[
                        "Rakoczego 13",
                        "Przy sklepie Netto",
                        "80-288 Gdańsk",
                    ],
                    active=True,
                    preferred=False,
                ),
                ProfileDeliveryPoint(
                    name="GDA03B",
                    type="PL",
                    address_lines=["Rakoczego 15", "Stacja paliw BP", "80-288 Gdańsk"],
                    active=False,
                    preferred=False,
                ),
                ProfileDeliveryPoint(
                    name="GDA117M",
                    type="PL",
                    address_lines=["Wieżycka 8", "obiekt mieszkalny", "80-180 Gdańsk"],
                    active=True,
                    preferred=True,
                ),
            ]
        )
        profile = UserProfile(delivery=ProfileDelivery(points=points))

        result = profile.get_favorite_locker_codes()

        # Should have 2 active lockers, with preferred first
        assert result == ["GDA117M", "GDA145M"]


# =============================================================================
# ParcelLockerListResponse Tests
# =============================================================================


class TestParcelLockerListResponse:
    """Tests for ParcelLockerListResponse dataclass."""

    def test_init_with_all_fields(self):
        """Test initialization with all fields."""
        locker = InPostParcelLocker(
            n="GDA117M",
            t=1,
            d="obiekt mieszkalny",
            m="Gdańsk",
            q=0,
            f="24/7",
            c="80-180",
            g="pomorskie",
            e="PL",
            r="Wieżycka",
            o="8",
            b="",
            h="",
            i="",
            l=InPostParcelLockerPointCoordinates(a=54.3188, o=18.58508),
            p=1,
            s=1,
        )

        response = ParcelLockerListResponse(
            date="2025-01-01",
            page=1,
            total_pages=1,
            items=[locker],
        )

        assert response.date == "2025-01-01"
        assert response.page == 1
        assert response.total_pages == 1
        assert len(response.items) == 1
        assert response.items[0].n == "GDA117M"
        assert response.items[0].d == "obiekt mieszkalny"

    def test_empty_items(self):
        """Test response with empty items list."""
        response = ParcelLockerListResponse(
            date="2025-01-01",
            page=1,
            total_pages=0,
            items=[],
        )

        assert response.items == []
        assert response.total_pages == 0
