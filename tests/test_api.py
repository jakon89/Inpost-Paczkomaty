"""Tests for InPost API clients."""

import base64
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.inpost_paczkomaty.api import InPostApiClient
from custom_components.inpost_paczkomaty.exceptions import ApiClientError
from custom_components.inpost_paczkomaty.const import (
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    DEFAULT_HTTP_TIMEOUT,
    DEFAULT_IGNORED_EN_ROUTE_STATUSES,
    DEFAULT_PARCEL_LOCKERS_URL,
    DEFAULT_SHOW_ONLY_OWN_PARCELS,
)
from custom_components.inpost_paczkomaty.models import (
    ApiParcel,
    ApiPickUpPoint,
    AuthTokens,
    HttpResponse,
    ParcelsSummary,
    UserProfile,
)


# =============================================================================
# Helpers
# =============================================================================


def _create_jwt_token(exp_offset_seconds: int = 7200) -> str:
    """Create a JWT token for testing with given expiration offset.

    Args:
        exp_offset_seconds: Seconds from now until token expires.
                          Positive = expires in future, negative = already expired.

    Returns:
        A valid JWT token string.
    """
    header = {"alg": "RS256", "kid": "test-key"}
    payload = {
        "sub": "user123",
        "exp": int(time.time()) + exp_offset_seconds,
        "iat": int(time.time()),
    }
    header_b64 = (
        base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    )
    payload_b64 = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    return f"{header_b64}.{payload_b64}.fake_signature"


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def valid_access_token():
    """Create a valid access token that won't expire soon."""
    return _create_jwt_token(exp_offset_seconds=7200)  # 2 hours


@pytest.fixture
def expiring_access_token():
    """Create an access token that is about to expire."""
    return _create_jwt_token(exp_offset_seconds=300)  # 5 minutes


@pytest.fixture
def mock_config_entry(valid_access_token):
    """Create a mock config entry with access token."""
    entry = MagicMock()
    entry.data = {
        CONF_ACCESS_TOKEN: valid_access_token,
        CONF_REFRESH_TOKEN: "test_refresh_token",
    }
    return entry


@pytest.fixture
def mock_config_entry_expiring_token(expiring_access_token):
    """Create a mock config entry with expiring access token."""
    entry = MagicMock()
    entry.data = {
        CONF_ACCESS_TOKEN: expiring_access_token,
        CONF_REFRESH_TOKEN: "test_refresh_token",
    }
    return entry


@pytest.fixture
def mock_config_entry_no_refresh():
    """Create a mock config entry without refresh token."""
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

    def test_init_with_default_ignored_statuses(self, mock_hass, mock_config_entry):
        """Test client initialization uses default ignored en_route statuses."""
        client = InPostApiClient(mock_hass, mock_config_entry)

        assert client._ignored_en_route_statuses == frozenset(
            DEFAULT_IGNORED_EN_ROUTE_STATUSES
        )

    def test_init_with_custom_ignored_statuses(self, mock_hass, mock_config_entry):
        """Test client initialization with custom ignored en_route statuses."""
        custom_ignored = ["CONFIRMED", "DISPATCHED_BY_SENDER"]
        client = InPostApiClient(
            mock_hass, mock_config_entry, ignored_en_route_statuses=custom_ignored
        )

        assert client._ignored_en_route_statuses == frozenset(custom_ignored)

    def test_init_with_empty_ignored_statuses(self, mock_hass, mock_config_entry):
        """Test client initialization with empty ignored en_route statuses list."""
        client = InPostApiClient(
            mock_hass, mock_config_entry, ignored_en_route_statuses=[]
        )

        assert client._ignored_en_route_statuses == frozenset()

    def test_init_with_default_http_timeout(self, mock_hass, mock_config_entry):
        """Test client initialization uses default HTTP timeout."""
        client = InPostApiClient(mock_hass, mock_config_entry)

        assert client._http_client.default_timeout == DEFAULT_HTTP_TIMEOUT
        assert client._public_http_client.default_timeout == DEFAULT_HTTP_TIMEOUT

    def test_init_with_custom_http_timeout(self, mock_hass, mock_config_entry):
        """Test client initialization with custom HTTP timeout."""
        custom_timeout = 60
        client = InPostApiClient(
            mock_hass, mock_config_entry, http_timeout=custom_timeout
        )

        assert client._http_client.default_timeout == custom_timeout
        assert client._public_http_client.default_timeout == custom_timeout

    def test_init_with_default_parcel_lockers_url(self, mock_hass, mock_config_entry):
        """Test client initialization uses default parcel lockers URL."""
        client = InPostApiClient(mock_hass, mock_config_entry)

        assert client._parcel_lockers_url == DEFAULT_PARCEL_LOCKERS_URL

    def test_init_with_custom_parcel_lockers_url(self, mock_hass, mock_config_entry):
        """Test client initialization with custom parcel lockers URL."""
        custom_url = "https://custom.example.com/lockers.json"
        client = InPostApiClient(
            mock_hass, mock_config_entry, parcel_lockers_url=custom_url
        )

        assert client._parcel_lockers_url == custom_url

    def test_init_with_default_show_only_own_parcels(
        self, mock_hass, mock_config_entry
    ):
        """Test client initialization uses default show_only_own_parcels."""
        client = InPostApiClient(mock_hass, mock_config_entry)

        assert client._show_only_own_parcels == DEFAULT_SHOW_ONLY_OWN_PARCELS
        assert client._show_only_own_parcels is False

    def test_init_with_show_only_own_parcels_enabled(
        self, mock_hass, mock_config_entry
    ):
        """Test client initialization with show_only_own_parcels enabled."""
        client = InPostApiClient(
            mock_hass, mock_config_entry, show_only_own_parcels=True
        )

        assert client._show_only_own_parcels is True

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
            assert (
                result.en_route_count == 1
            )  # OUT_FOR_DELIVERY (CONFIRMED ignored by default)
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


# =============================================================================
# Token Refresh Tests
# =============================================================================


class TestTokenRefresh:
    """Tests for token refresh functionality."""

    @pytest.mark.asyncio
    async def test_refresh_access_token_success(self, mock_hass, mock_config_entry):
        """Test successful token refresh."""
        client = InPostApiClient(mock_hass, mock_config_entry)

        new_access_token = _create_jwt_token(7200)
        mock_response = HttpResponse(
            body={
                "access_token": new_access_token,
                "refresh_token": "new_refresh_token",
                "token_type": "Bearer",
                "expires_in": 7199,
                "scope": "openid",
                "id_token": "new_id_token",
            },
            status=200,
        )

        with patch.object(
            client._public_http_client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = mock_response

            result = await client.refresh_access_token()

            assert isinstance(result, AuthTokens)
            assert result.access_token == new_access_token
            assert result.refresh_token == "new_refresh_token"
            assert result.token_type == "Bearer"
            assert result.expires_in == 7199
            assert client._access_token == new_access_token
            assert client._refresh_token == "new_refresh_token"
            mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_access_token_updates_http_client_headers(
        self, mock_hass, mock_config_entry
    ):
        """Test that token refresh updates HTTP client authorization header."""
        client = InPostApiClient(mock_hass, mock_config_entry)

        new_access_token = _create_jwt_token(7200)
        mock_response = HttpResponse(
            body={
                "access_token": new_access_token,
                "refresh_token": "new_refresh_token",
            },
            status=200,
        )

        with patch.object(
            client._public_http_client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = mock_response

            with patch.object(
                client._http_client, "update_headers"
            ) as mock_update_headers:
                await client.refresh_access_token()

                mock_update_headers.assert_called_once_with(
                    {"Authorization": f"Bearer {new_access_token}"}
                )

    @pytest.mark.asyncio
    async def test_refresh_access_token_calls_callback(
        self, mock_hass, mock_config_entry
    ):
        """Test that token refresh calls the callback if set."""
        callback_mock = MagicMock()
        client = InPostApiClient(
            mock_hass, mock_config_entry, on_token_refresh=callback_mock
        )

        new_access_token = _create_jwt_token(7200)
        mock_response = HttpResponse(
            body={
                "access_token": new_access_token,
                "refresh_token": "new_refresh_token",
            },
            status=200,
        )

        with patch.object(
            client._public_http_client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = mock_response

            await client.refresh_access_token()

            callback_mock.assert_called_once()
            args = callback_mock.call_args[0]
            assert isinstance(args[0], AuthTokens)
            assert args[0].access_token == new_access_token

    @pytest.mark.asyncio
    async def test_refresh_access_token_api_error(self, mock_hass, mock_config_entry):
        """Test token refresh API error handling."""
        client = InPostApiClient(mock_hass, mock_config_entry)

        mock_response = HttpResponse(
            body={"error": "invalid_grant"},
            status=400,
        )

        with patch.object(
            client._public_http_client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = mock_response

            with pytest.raises(ApiClientError) as exc_info:
                await client.refresh_access_token()

            assert "Status: 400" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_refresh_access_token_no_refresh_token(self, mock_hass):
        """Test token refresh without refresh token raises error."""
        entry = MagicMock()
        entry.data = {CONF_ACCESS_TOKEN: "test_access_token"}
        client = InPostApiClient(mock_hass, entry)

        with pytest.raises(ApiClientError) as exc_info:
            await client.refresh_access_token()

        assert "No refresh token available" in str(exc_info.value)


class TestTokenAutoRefresh:
    """Tests for automatic token refresh before API requests."""

    @pytest.mark.asyncio
    async def test_get_parcels_refreshes_expiring_token(
        self, mock_hass, mock_config_entry_expiring_token, sample_api_response
    ):
        """Test that get_parcels refreshes an expiring token."""
        client = InPostApiClient(mock_hass, mock_config_entry_expiring_token)

        new_access_token = _create_jwt_token(7200)
        refresh_response = HttpResponse(
            body={
                "access_token": new_access_token,
                "refresh_token": "new_refresh_token",
            },
            status=200,
        )
        parcels_response = HttpResponse(
            body=sample_api_response,
            status=200,
        )

        with (
            patch.object(
                client._public_http_client, "post", new_callable=AsyncMock
            ) as mock_post,
            patch.object(
                client._http_client, "get", new_callable=AsyncMock
            ) as mock_get,
        ):
            mock_post.return_value = refresh_response
            mock_get.return_value = parcels_response

            result = await client.get_parcels()

            # Token should be refreshed
            mock_post.assert_called_once()
            assert isinstance(result, ParcelsSummary)

    @pytest.mark.asyncio
    async def test_get_parcels_no_refresh_for_valid_token(
        self, mock_hass, mock_config_entry, sample_api_response
    ):
        """Test that get_parcels does not refresh a valid token."""
        client = InPostApiClient(mock_hass, mock_config_entry)

        parcels_response = HttpResponse(
            body=sample_api_response,
            status=200,
        )

        with (
            patch.object(
                client._public_http_client, "post", new_callable=AsyncMock
            ) as mock_post,
            patch.object(
                client._http_client, "get", new_callable=AsyncMock
            ) as mock_get,
        ):
            mock_get.return_value = parcels_response

            result = await client.get_parcels()

            # Token should NOT be refreshed
            mock_post.assert_not_called()
            assert isinstance(result, ParcelsSummary)

    @pytest.mark.asyncio
    async def test_get_profile_refreshes_expiring_token(
        self, mock_hass, mock_config_entry_expiring_token, sample_profile_response
    ):
        """Test that get_profile refreshes an expiring token."""
        client = InPostApiClient(mock_hass, mock_config_entry_expiring_token)

        new_access_token = _create_jwt_token(7200)
        refresh_response = HttpResponse(
            body={
                "access_token": new_access_token,
                "refresh_token": "new_refresh_token",
            },
            status=200,
        )
        profile_response = HttpResponse(
            body=sample_profile_response,
            status=200,
        )

        with (
            patch.object(
                client._public_http_client, "post", new_callable=AsyncMock
            ) as mock_post,
            patch.object(
                client._http_client, "get", new_callable=AsyncMock
            ) as mock_get,
        ):
            mock_post.return_value = refresh_response
            mock_get.return_value = profile_response

            result = await client.get_profile()

            # Token should be refreshed
            mock_post.assert_called_once()
            assert isinstance(result, UserProfile)

    @pytest.mark.asyncio
    async def test_no_refresh_without_access_token(self, mock_hass):
        """Test that no refresh is attempted without access token."""
        entry = MagicMock()
        entry.data = {}
        client = InPostApiClient(mock_hass, entry)

        with patch.object(
            client._public_http_client, "post", new_callable=AsyncMock
        ) as mock_post:
            # This should not trigger a refresh attempt
            await client._ensure_valid_token()

            mock_post.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_refresh_without_refresh_token(
        self, mock_hass, mock_config_entry_no_refresh
    ):
        """Test that no refresh is attempted without refresh token."""
        # Use an expiring token
        entry = MagicMock()
        entry.data = {CONF_ACCESS_TOKEN: _create_jwt_token(300)}  # Expires in 5 min
        client = InPostApiClient(mock_hass, entry)

        with patch.object(
            client._public_http_client, "post", new_callable=AsyncMock
        ) as mock_post:
            # This should not trigger a refresh attempt
            await client._ensure_valid_token()

            mock_post.assert_not_called()


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
        """Test en route parcels with different statuses (CONFIRMED ignored by default)."""
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

        # CONFIRMED is ignored by default
        assert result.en_route_count == 2
        assert "GDA08M" in result.en_route
        assert "GDA117M" in result.en_route
        assert result.en_route["GDA08M"].count == 1
        assert result.en_route["GDA117M"].count == 1

    def test_en_route_parcels_with_no_ignored_statuses(
        self, mock_hass, mock_config_entry
    ):
        """Test en route parcels when no statuses are ignored."""
        client = InPostApiClient(
            mock_hass, mock_config_entry, ignored_en_route_statuses=[]
        )

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

        # No statuses ignored, all en_route statuses counted
        assert result.en_route_count == 3
        assert "GDA08M" in result.en_route
        assert "GDA117M" in result.en_route
        assert result.en_route["GDA08M"].count == 2
        assert result.en_route["GDA117M"].count == 1

    def test_en_route_parcels_with_custom_ignored_statuses(
        self, mock_hass, mock_config_entry
    ):
        """Test en route parcels with custom ignored statuses."""
        client = InPostApiClient(
            mock_hass,
            mock_config_entry,
            ignored_en_route_statuses=["CONFIRMED", "SENT_FROM_SOURCE_BRANCH"],
        )

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

        # CONFIRMED and SENT_FROM_SOURCE_BRANCH are ignored
        assert result.en_route_count == 1
        assert "GDA08M" in result.en_route
        assert "GDA117M" not in result.en_route
        assert result.en_route["GDA08M"].count == 1

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

    def test_show_only_own_parcels_filters_friend_parcels(
        self, mock_hass, mock_config_entry
    ):
        """Test that show_only_own_parcels filters out FRIEND parcels."""
        client = InPostApiClient(
            mock_hass, mock_config_entry, show_only_own_parcels=True
        )

        parcels = [
            ApiParcel(
                shipment_number="1",
                status="READY_TO_PICKUP",
                ownership_status="OWN",
                pick_up_point=ApiPickUpPoint(name="GDA117M"),
            ),
            ApiParcel(
                shipment_number="2",
                status="READY_TO_PICKUP",
                ownership_status="FRIEND",
                pick_up_point=ApiPickUpPoint(name="GDA117M"),
            ),
            ApiParcel(
                shipment_number="3",
                status="OUT_FOR_DELIVERY",
                ownership_status="OWN",
                pick_up_point=ApiPickUpPoint(name="GDA08M"),
            ),
            ApiParcel(
                shipment_number="4",
                status="OUT_FOR_DELIVERY",
                ownership_status="FRIEND",
                pick_up_point=ApiPickUpPoint(name="GDA08M"),
            ),
        ]

        result = client._build_parcels_summary(parcels)

        # Only OWN parcels should be counted
        assert result.ready_for_pickup_count == 1
        assert result.en_route_count == 1
        assert result.ready_for_pickup["GDA117M"].count == 1
        assert result.en_route["GDA08M"].count == 1

    def test_show_all_parcels_includes_friend_parcels(
        self, mock_hass, mock_config_entry
    ):
        """Test that default setting includes both OWN and FRIEND parcels."""
        client = InPostApiClient(
            mock_hass, mock_config_entry, show_only_own_parcels=False
        )

        parcels = [
            ApiParcel(
                shipment_number="1",
                status="READY_TO_PICKUP",
                ownership_status="OWN",
                pick_up_point=ApiPickUpPoint(name="GDA117M"),
            ),
            ApiParcel(
                shipment_number="2",
                status="READY_TO_PICKUP",
                ownership_status="FRIEND",
                pick_up_point=ApiPickUpPoint(name="GDA117M"),
            ),
        ]

        result = client._build_parcels_summary(parcels)

        # Both OWN and FRIEND parcels should be counted
        assert result.ready_for_pickup_count == 2
        assert result.ready_for_pickup["GDA117M"].count == 2


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
