"""Unit tests for InPost data models."""

import pytest

from custom_components.inpost_paczkomaty.exceptions import InPostApiError
from custom_components.inpost_paczkomaty.models import (
    ApiCarbonFootprint,
    ApiParcel,
    ApiPickUpPoint,
    AuthStep,
    AuthTokens,
    CarbonFootprintStats,
    DailyCarbonFootprint,
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


# =============================================================================
# ApiCarbonFootprint Tests
# =============================================================================


class TestApiCarbonFootprint:
    """Tests for ApiCarbonFootprint dataclass."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        carbon = ApiCarbonFootprint()

        assert carbon.box_machine_delivery is None
        assert carbon.address_delivery is None
        assert carbon.change_delivery_type_percent is None
        assert carbon.change_delivery_type_value is None
        assert carbon.redirection_url is None

    def test_init_with_all_values(self):
        """Test initialization with all values."""
        carbon = ApiCarbonFootprint(
            box_machine_delivery="0.012",
            address_delivery="0.320",
            change_delivery_type_percent="96.1",
            change_delivery_type_value="0.308",
            redirection_url="https://inpost.pl/slad-weglowy",
        )

        assert carbon.box_machine_delivery == "0.012"
        assert carbon.address_delivery == "0.320"
        assert carbon.change_delivery_type_percent == "96.1"
        assert carbon.change_delivery_type_value == "0.308"
        assert carbon.redirection_url == "https://inpost.pl/slad-weglowy"


# =============================================================================
# ApiPickUpPoint Tests
# =============================================================================


class TestApiPickUpPoint:
    """Tests for ApiPickUpPoint dataclass."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        point = ApiPickUpPoint(name="GDA117M")

        assert point.name == "GDA117M"
        assert point.location is None
        assert point.type is None
        assert point.easy_access_zone is False

    def test_is_parcel_locker_true(self):
        """Test is_parcel_locker returns True for parcel_locker type."""
        point = ApiPickUpPoint(name="GDA117M", type=["parcel_locker"])
        assert point.is_parcel_locker is True

    def test_is_parcel_locker_true_with_multiple_types(self):
        """Test is_parcel_locker returns True when parcel_locker is in type list."""
        point = ApiPickUpPoint(
            name="GDA117M", type=["parcel_locker", "parcel_locker_superpop"]
        )
        assert point.is_parcel_locker is True

    def test_is_parcel_locker_false_for_other_type(self):
        """Test is_parcel_locker returns False for non-parcel_locker types."""
        point = ApiPickUpPoint(name="WAW001", type=["pop"])
        assert point.is_parcel_locker is False

    def test_is_parcel_locker_false_when_type_none(self):
        """Test is_parcel_locker returns False when type is None."""
        point = ApiPickUpPoint(name="GDA117M", type=None)
        assert point.is_parcel_locker is False

    def test_is_parcel_locker_false_when_type_empty(self):
        """Test is_parcel_locker returns False when type is empty list."""
        point = ApiPickUpPoint(name="GDA117M", type=[])
        assert point.is_parcel_locker is False


# =============================================================================
# ApiParcel Carbon Footprint Tests
# =============================================================================


class TestApiParcelCarbonFootprint:
    """Tests for ApiParcel carbon footprint related properties."""

    def test_effective_carbon_footprint_parcel_locker(self):
        """Test effective_carbon_footprint uses boxMachineDelivery for parcel lockers."""
        parcel = ApiParcel(
            shipment_number="123",
            status="DELIVERED",
            pick_up_point=ApiPickUpPoint(name="GDA117M", type=["parcel_locker"]),
            carbon_footprint=ApiCarbonFootprint(
                box_machine_delivery="0.012",
                address_delivery="0.320",
            ),
        )

        assert parcel.effective_carbon_footprint == 0.012

    def test_effective_carbon_footprint_courier(self):
        """Test effective_carbon_footprint uses addressDelivery for courier delivery."""
        parcel = ApiParcel(
            shipment_number="123",
            status="DELIVERED",
            pick_up_point=ApiPickUpPoint(name="WAW001", type=["pop"]),
            carbon_footprint=ApiCarbonFootprint(
                box_machine_delivery="0.012",
                address_delivery="0.320",
            ),
        )

        assert parcel.effective_carbon_footprint == 0.320

    def test_effective_carbon_footprint_no_pickup_point(self):
        """Test effective_carbon_footprint uses addressDelivery when no pickup point."""
        parcel = ApiParcel(
            shipment_number="123",
            status="DELIVERED",
            pick_up_point=None,
            carbon_footprint=ApiCarbonFootprint(
                box_machine_delivery="0.012",
                address_delivery="0.320",
            ),
        )

        assert parcel.effective_carbon_footprint == 0.320

    def test_effective_carbon_footprint_none_when_no_carbon_data(self):
        """Test effective_carbon_footprint returns None when no carbon data."""
        parcel = ApiParcel(
            shipment_number="123",
            status="DELIVERED",
            pick_up_point=ApiPickUpPoint(name="GDA117M", type=["parcel_locker"]),
            carbon_footprint=None,
        )

        assert parcel.effective_carbon_footprint is None

    def test_effective_carbon_footprint_none_when_value_missing(self):
        """Test effective_carbon_footprint returns None when value is missing."""
        parcel = ApiParcel(
            shipment_number="123",
            status="DELIVERED",
            pick_up_point=ApiPickUpPoint(name="GDA117M", type=["parcel_locker"]),
            carbon_footprint=ApiCarbonFootprint(
                box_machine_delivery=None,
                address_delivery="0.320",
            ),
        )

        assert parcel.effective_carbon_footprint is None

    def test_effective_carbon_footprint_invalid_value(self):
        """Test effective_carbon_footprint returns None for invalid value."""
        parcel = ApiParcel(
            shipment_number="123",
            status="DELIVERED",
            pick_up_point=ApiPickUpPoint(name="GDA117M", type=["parcel_locker"]),
            carbon_footprint=ApiCarbonFootprint(
                box_machine_delivery="invalid",
                address_delivery="0.320",
            ),
        )

        assert parcel.effective_carbon_footprint is None

    def test_pick_up_date_parsed_valid(self):
        """Test pick_up_date_parsed with valid ISO date."""
        parcel = ApiParcel(
            shipment_number="123",
            status="DELIVERED",
            pick_up_date="2025-12-02T20:45:47.443Z",
        )

        result = parcel.pick_up_date_parsed
        assert result is not None
        assert result.year == 2025
        assert result.month == 12
        assert result.day == 2
        assert result.hour == 20
        assert result.minute == 45

    def test_pick_up_date_parsed_none_when_no_date(self):
        """Test pick_up_date_parsed returns None when no date."""
        parcel = ApiParcel(
            shipment_number="123",
            status="DELIVERED",
            pick_up_date=None,
        )

        assert parcel.pick_up_date_parsed is None

    def test_pick_up_date_parsed_invalid_date(self):
        """Test pick_up_date_parsed returns None for invalid date."""
        parcel = ApiParcel(
            shipment_number="123",
            status="DELIVERED",
            pick_up_date="invalid-date",
        )

        assert parcel.pick_up_date_parsed is None


# =============================================================================
# DailyCarbonFootprint Tests
# =============================================================================


class TestDailyCarbonFootprint:
    """Tests for DailyCarbonFootprint dataclass."""

    def test_init(self):
        """Test initialization."""
        daily = DailyCarbonFootprint(
            date="2025-12-02",
            value=0.024,
            parcel_count=2,
        )

        assert daily.date == "2025-12-02"
        assert daily.value == 0.024
        assert daily.parcel_count == 2


# =============================================================================
# CarbonFootprintStats Tests
# =============================================================================


class TestCarbonFootprintStats:
    """Tests for CarbonFootprintStats dataclass."""

    def test_init(self):
        """Test initialization."""
        stats = CarbonFootprintStats(
            total_co2_kg=0.5,
            total_parcels=10,
            daily_data=[],
        )

        assert stats.total_co2_kg == 0.5
        assert stats.total_parcels == 10
        assert stats.daily_data == []

    def test_total_co2_grams(self):
        """Test total_co2_grams property."""
        stats = CarbonFootprintStats(
            total_co2_kg=0.5,
            total_parcels=10,
            daily_data=[],
        )

        assert stats.total_co2_grams == 500.0

    def test_with_daily_data(self):
        """Test initialization with daily data."""
        daily_data = [
            DailyCarbonFootprint(date="2025-12-01", value=0.012, parcel_count=1),
            DailyCarbonFootprint(date="2025-12-02", value=0.024, parcel_count=2),
        ]

        stats = CarbonFootprintStats(
            total_co2_kg=0.036,
            total_parcels=3,
            daily_data=daily_data,
        )

        assert len(stats.daily_data) == 2
        assert stats.daily_data[0].date == "2025-12-01"
        assert stats.daily_data[1].value == 0.024
