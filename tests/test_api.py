"""Tests for InPost API clients."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.inpost_paczkomaty.api import InPostApiClient
from custom_components.inpost_paczkomaty.exceptions import ApiClientError
from custom_components.inpost_paczkomaty.const import CONF_ACCESS_TOKEN
from custom_components.inpost_paczkomaty.models import (
    ApiParcel,
    ApiPickUpPoint,
    HttpResponse,
    Locker,
    ParcelsSummary,
    UserProfile,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry with access token."""
    entry = MagicMock()
    entry.data = {CONF_ACCESS_TOKEN: "test_access_token"}
    return entry


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.config.language = "pl"
    return hass


@pytest.fixture
def sample_api_response():
    """Sample InPost API response data."""
    return {
        "updatedUntil": "2025-12-30T08:42:55.488Z",
        "more": False,
        "parcels": [
            {
                "shipmentNumber": "695080086580180027785172",
                "shipmentType": "parcel",
                "openCode": "689756",
                "status": "READY_TO_PICKUP",
                "pickUpPoint": {
                    "name": "GDA117M",
                    "location": {"latitude": 54.3188, "longitude": 18.58508},
                    "addressDetails": {
                        "postCode": "80-180",
                        "city": "Gdańsk",
                    },
                },
                "receiver": {
                    "phoneNumber": {"prefix": "+48", "value": "123456789"},
                    "email": "test@example.com",
                    "name": "Test User",
                },
                "sender": {"name": "Test Sender"},
            },
            {
                "shipmentNumber": "520113012280180076018438",
                "shipmentType": "courier",
                "status": "OUT_FOR_DELIVERY",
                "pickUpPoint": None,
                "receiver": {
                    "phoneNumber": {"prefix": "+48", "value": "987654321"},
                },
                "sender": {"name": "Amazon"},
            },
            {
                "shipmentNumber": "620999567280180432895075",
                "shipmentType": "parcel",
                "status": "CONFIRMED",
                "pickUpPoint": {
                    "name": "GDA08M",
                },
            },
            {
                "shipmentNumber": "111111111111111111111111",
                "shipmentType": "parcel",
                "status": "DELIVERED",
                "pickUpPoint": {"name": "GDA117M"},
            },
        ],
    }


@pytest.fixture
def sample_api_response_snake_case(sample_api_response):
    """Sample API response already converted to snake_case."""
    from custom_components.inpost_paczkomaty.utils import convert_keys_to_snake_case

    return convert_keys_to_snake_case(sample_api_response)


@pytest.fixture
def sample_profile_response():
    """Sample InPost profile API response data."""
    return {
        "personal": {
            "firstName": "Mykola",
            "lastName": "Mykhalov",
            "email": "test@example.com",
            "emailVerified": True,
            "phoneNumber": "575875127",
            "phoneNumberPrefix": "+48",
        },
        "delivery": {
            "points": {
                "items": [
                    {
                        "name": "GDA145M",
                        "type": "PL",
                        "addressLines": [
                            "Rakoczego 13",
                            "Przy sklepie Netto",
                            "80-288 Gdańsk",
                        ],
                        "active": True,
                    },
                    {
                        "name": "GDA03B",
                        "type": "PL",
                        "addressLines": [
                            "Rakoczego 15",
                            "Stacja paliw BP",
                            "80-288 Gdańsk",
                        ],
                        "active": False,
                    },
                    {
                        "name": "GDA117M",
                        "type": "PL",
                        "addressLines": [
                            "Wieżycka 8",
                            "obiekt mieszkalny",
                            "80-180 Gdańsk",
                        ],
                        "active": True,
                        "preferred": True,
                    },
                ]
            },
            "preferredDeliveryType": "BOX_MACHINE",
        },
        "shoppingActive": True,
    }


# =============================================================================
# InPostApiClient Tests
# =============================================================================


class TestInPostApiClient:
    """Tests for InPostApiClient class."""

    def test_init_with_config_entry(self, mock_hass, mock_config_entry):
        """Test client initialization with config entry."""
        client = InPostApiClient(mock_hass, mock_config_entry)

        assert client.hass == mock_hass
        assert client._http_client is not None

    def test_init_with_access_token_override(self, mock_hass, mock_config_entry):
        """Test client initialization with access token override."""
        client = InPostApiClient(
            mock_hass, mock_config_entry, access_token="override_token"
        )

        # The override token should be used
        assert "Authorization" in client._http_client.headers
        assert client._http_client.headers["Authorization"] == "Bearer override_token"

    def test_init_with_empty_entry(self, mock_hass):
        """Test client initialization with empty config entry."""
        entry = MagicMock()
        entry.data = {}

        client = InPostApiClient(mock_hass, entry)
        assert client._http_client is not None

    @pytest.mark.asyncio
    async def test_get_parcels_success(
        self, mock_hass, mock_config_entry, sample_api_response
    ):
        """Test successful parcels retrieval."""
        client = InPostApiClient(mock_hass, mock_config_entry)

        mock_response = HttpResponse(
            body=sample_api_response,
            status=200,
        )

        with patch.object(
            client._http_client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = mock_response

            result = await client.get_parcels()

            assert isinstance(result, ParcelsSummary)
            assert result.all_count == 4
            assert result.ready_for_pickup_count == 1
            assert result.en_route_count == 2  # OUT_FOR_DELIVERY + CONFIRMED
            assert "GDA117M" in result.ready_for_pickup
            assert result.ready_for_pickup["GDA117M"].count == 1

    @pytest.mark.asyncio
    async def test_get_parcels_api_error(self, mock_hass, mock_config_entry):
        """Test API error handling."""
        client = InPostApiClient(mock_hass, mock_config_entry)

        mock_response = HttpResponse(
            body={"error": "Unauthorized"},
            status=401,
        )

        with patch.object(
            client._http_client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = mock_response

            with pytest.raises(ApiClientError) as exc_info:
                await client.get_parcels()

            assert "Status: 401" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_close(self, mock_hass, mock_config_entry):
        """Test client close method."""
        client = InPostApiClient(mock_hass, mock_config_entry)

        with (
            patch.object(
                client._http_client, "close", new_callable=AsyncMock
            ) as mock_close,
            patch.object(
                client._public_http_client, "close", new_callable=AsyncMock
            ) as mock_public_close,
        ):
            await client.close()
            mock_close.assert_called_once()
            mock_public_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_profile_success(
        self, mock_hass, mock_config_entry, sample_profile_response
    ):
        """Test successful profile retrieval."""
        client = InPostApiClient(mock_hass, mock_config_entry)

        mock_response = HttpResponse(
            body=sample_profile_response,
            status=200,
        )

        with patch.object(
            client._http_client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = mock_response

            result = await client.get_profile()

            assert isinstance(result, UserProfile)
            assert result.shopping_active is True
            assert result.personal is not None
            assert result.personal.first_name == "Mykola"
            assert result.delivery is not None
            assert result.delivery.points is not None
            assert len(result.delivery.points.items) == 3

    @pytest.mark.asyncio
    async def test_get_profile_favorite_lockers(
        self, mock_hass, mock_config_entry, sample_profile_response
    ):
        """Test extracting favorite lockers from profile."""
        client = InPostApiClient(mock_hass, mock_config_entry)

        mock_response = HttpResponse(
            body=sample_profile_response,
            status=200,
        )

        with patch.object(
            client._http_client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = mock_response

            result = await client.get_profile()
            favorites = result.get_favorite_locker_codes()

            # Should have 2 active lockers with preferred first
            assert len(favorites) == 2
            assert favorites[0] == "GDA117M"  # Preferred
            assert "GDA145M" in favorites
            assert "GDA03B" not in favorites  # Inactive

    @pytest.mark.asyncio
    async def test_get_profile_api_error(self, mock_hass, mock_config_entry):
        """Test profile API error handling."""
        client = InPostApiClient(mock_hass, mock_config_entry)

        mock_response = HttpResponse(
            body={"error": "Unauthorized"},
            status=401,
        )

        with patch.object(
            client._http_client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = mock_response

            with pytest.raises(ApiClientError) as exc_info:
                await client.get_profile()

            assert "Status: 401" in str(exc_info.value)


class TestBuildParcelsSummary:
    """Tests for _build_parcels_summary method."""

    def test_empty_parcels(self, mock_hass, mock_config_entry):
        """Test with empty parcel list."""
        client = InPostApiClient(mock_hass, mock_config_entry)
        result = client._build_parcels_summary([])

        assert result.all_count == 0
        assert result.ready_for_pickup_count == 0
        assert result.en_route_count == 0
        assert result.ready_for_pickup == {}
        assert result.en_route == {}

    def test_ready_for_pickup_parcels(self, mock_hass, mock_config_entry):
        """Test parcels ready for pickup."""
        client = InPostApiClient(mock_hass, mock_config_entry)

        parcels = [
            ApiParcel(
                shipment_number="123",
                status="READY_TO_PICKUP",
                pick_up_point=ApiPickUpPoint(name="GDA117M"),
            ),
            ApiParcel(
                shipment_number="456",
                status="READY_TO_PICKUP",
                pick_up_point=ApiPickUpPoint(name="GDA117M"),
            ),
        ]

        result = client._build_parcels_summary(parcels)

        assert result.ready_for_pickup_count == 2
        assert "GDA117M" in result.ready_for_pickup
        assert result.ready_for_pickup["GDA117M"].count == 2
        assert len(result.ready_for_pickup["GDA117M"].parcels) == 2

    def test_en_route_parcels(self, mock_hass, mock_config_entry):
        """Test en route parcels with different statuses."""
        client = InPostApiClient(mock_hass, mock_config_entry)

        parcels = [
            ApiParcel(
                shipment_number="1",
                status="OUT_FOR_DELIVERY",
                pick_up_point=ApiPickUpPoint(name="GDA08M"),
            ),
            ApiParcel(
                shipment_number="2",
                status="CONFIRMED",
                pick_up_point=ApiPickUpPoint(name="GDA08M"),
            ),
            ApiParcel(
                shipment_number="3",
                status="SENT_FROM_SOURCE_BRANCH",
                pick_up_point=ApiPickUpPoint(name="GDA117M"),
            ),
        ]

        result = client._build_parcels_summary(parcels)

        assert result.en_route_count == 3
        assert "GDA08M" in result.en_route
        assert "GDA117M" in result.en_route
        assert result.en_route["GDA08M"].count == 2
        assert result.en_route["GDA117M"].count == 1

    def test_courier_parcels_without_locker(self, mock_hass, mock_config_entry):
        """Test courier parcels without pickup point use COURIER as locker_id."""
        client = InPostApiClient(mock_hass, mock_config_entry)

        parcels = [
            ApiParcel(
                shipment_number="123",
                status="OUT_FOR_DELIVERY",
                shipment_type="courier",
                pick_up_point=None,
            ),
        ]

        result = client._build_parcels_summary(parcels)

        assert result.en_route_count == 1
        assert "COURIER" in result.en_route
        assert result.en_route["COURIER"].count == 1

    def test_delivered_parcels_not_counted(self, mock_hass, mock_config_entry):
        """Test that delivered parcels are not counted in ready or en_route."""
        client = InPostApiClient(mock_hass, mock_config_entry)

        parcels = [
            ApiParcel(
                shipment_number="123",
                status="DELIVERED",
                pick_up_point=ApiPickUpPoint(name="GDA117M"),
            ),
        ]

        result = client._build_parcels_summary(parcels)

        assert result.all_count == 1
        assert result.ready_for_pickup_count == 0
        assert result.en_route_count == 0
        assert result.ready_for_pickup == {}
        assert result.en_route == {}


# =============================================================================
# Parcel Lockers Tests
# =============================================================================


@pytest.fixture
def sample_parcel_lockers_response():
    """Sample parcel lockers API response."""
    return {
        "date": "2025-01-01",
        "page": 1,
        "total_pages": 1,
        "items": [
            {
                "n": "GDA117M",
                "t": 1,
                "d": "obiekt mieszkalny",
                "m": "Gdańsk",
                "q": 0,
                "f": "24/7",
                "c": "80-180",
                "g": "pomorskie",
                "e": "PL",
                "r": "Wieżycka",
                "o": "8",
                "b": "",
                "h": "",
                "i": "",
                "l": {"a": 54.3188, "o": 18.58508},
                "p": 1,
                "s": 1,
            },
            {
                "n": "GDA145M",
                "t": 1,
                "d": "Przy sklepie Netto",
                "m": "Gdańsk",
                "q": 0,
                "f": "24/7",
                "c": "80-288",
                "g": "pomorskie",
                "e": "PL",
                "r": "Rakoczego",
                "o": "13",
                "b": "",
                "h": "",
                "i": "",
                "l": {"a": 54.4052, "o": 18.5678},
                "p": 1,
                "s": 1,
            },
        ],
    }


class TestParcelLockers:
    """Tests for parcel lockers public endpoint."""

    @pytest.mark.asyncio
    async def test_get_parcel_lockers_list_success(
        self, mock_hass, sample_parcel_lockers_response
    ):
        """Test successful parcel lockers list retrieval."""
        client = InPostApiClient(mock_hass)

        mock_response = HttpResponse(
            body=sample_parcel_lockers_response,
            status=200,
        )

        with patch.object(
            client._public_http_client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = mock_response

            result = await client.get_parcel_lockers_list()

            assert len(result) == 2
            assert result[0].n == "GDA117M"
            assert result[0].d == "obiekt mieszkalny"
            assert result[1].n == "GDA145M"
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_parcel_lockers_list_api_error(self, mock_hass):
        """Test API error handling for parcel lockers."""
        client = InPostApiClient(mock_hass)

        mock_response = HttpResponse(
            body={"error": "Server error"},
            status=500,
        )

        with patch.object(
            client._public_http_client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = mock_response

            with pytest.raises(ApiClientError) as exc_info:
                await client.get_parcel_lockers_list()

            assert "Status: 500" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_parcel_lockers_list_network_error(self, mock_hass):
        """Test network error handling for parcel lockers."""
        client = InPostApiClient(mock_hass)

        with patch.object(
            client._public_http_client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = Exception("Network error")

            with pytest.raises(ApiClientError) as exc_info:
                await client.get_parcel_lockers_list()

            assert "Error communicating with InPost API!" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_client_without_auth(self, mock_hass):
        """Test client initialization without authentication."""
        client = InPostApiClient(mock_hass)

        # Should have public client for unauthenticated requests
        assert client._public_http_client is not None
        # Auth header should not be set when no token provided
        assert "Authorization" not in client._http_client.headers


# =============================================================================
# ApiParcel Model Tests
# =============================================================================


class TestApiParcel:
    """Tests for ApiParcel model methods."""

    def test_locker_id_with_pickup_point(self):
        """Test locker_id property with pickup point."""
        parcel = ApiParcel(
            shipment_number="123",
            status="READY_TO_PICKUP",
            pick_up_point=ApiPickUpPoint(name="GDA117M"),
        )
        assert parcel.locker_id == "GDA117M"

    def test_locker_id_without_pickup_point(self):
        """Test locker_id property without pickup point."""
        parcel = ApiParcel(
            shipment_number="123",
            status="OUT_FOR_DELIVERY",
            pick_up_point=None,
        )
        assert parcel.locker_id is None

    def test_status_description_known_status(self):
        """Test status_description for known statuses."""
        parcel = ApiParcel(shipment_number="123", status="READY_TO_PICKUP")
        assert parcel.status_description == "Gotowa do odbioru"

        parcel = ApiParcel(shipment_number="123", status="DELIVERED")
        assert parcel.status_description == "Doręczona"

    def test_status_description_unknown_status(self):
        """Test status_description for unknown status returns status itself."""
        parcel = ApiParcel(shipment_number="123", status="UNKNOWN_STATUS")
        assert parcel.status_description == "UNKNOWN_STATUS"

    def test_to_parcel_item(self):
        """Test conversion to ParcelItem."""
        from custom_components.inpost_paczkomaty.models import (
            ApiPhoneNumber,
            ApiReceiver,
        )

        parcel = ApiParcel(
            shipment_number="695080086580180027785172",
            status="READY_TO_PICKUP",
            open_code="689756",
            receiver=ApiReceiver(
                phone_number=ApiPhoneNumber(prefix="+48", value="123456789")
            ),
        )

        item = parcel.to_parcel_item()

        assert item.id == "695080086580180027785172"
        assert item.status == "READY_TO_PICKUP"
        assert item.code == "689756"
        assert item.phone == "+48123456789"
        assert item.status_desc == "Gotowa do odbioru"
