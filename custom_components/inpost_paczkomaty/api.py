"""Functions to connect to InPost APIs."""

import logging
from typing import Callable, Dict, List, Optional

from dacite import Config, from_dict
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.inpost_paczkomaty.const import (
    API_BASE_URL,
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    DEFAULT_HTTP_TIMEOUT,
    DEFAULT_IGNORED_EN_ROUTE_STATUSES,
    DEFAULT_PARCEL_LOCKERS_URL,
    DEFAULT_SHOW_ONLY_OWN_PARCELS,
    OAUTH_CLIENT_ID,
    API_USER_AGENT,
)
from custom_components.inpost_paczkomaty.exceptions import ApiClientError
from custom_components.inpost_paczkomaty.http_client import HttpClient
from custom_components.inpost_paczkomaty.models import (
    ApiAddressDetails,
    ApiCarbonFootprint,
    ApiLocation,
    ApiParcel,
    ApiPhoneNumber,
    ApiPickUpPoint,
    ApiReceiver,
    ApiSender,
    AuthTokens,
    CarbonFootprintStats,
    DailyCarbonFootprint,
    EN_ROUTE_STATUSES,
    InPostParcelLocker,
    Locker,
    ParcelLockerListResponse,
    ParcelsSummary,
    ProfileDelivery,
    ProfileDeliveryAddress,
    ProfileDeliveryAddressData,
    ProfileDeliveryAddressDetails,
    ProfileDeliveryAddresses,
    ProfileDeliveryPoint,
    ProfileDeliveryPoints,
    ProfilePersonal,
    TrackedParcelsResponse,
    UserProfile,
)
from custom_components.inpost_paczkomaty.utils import (
    convert_keys_to_snake_case,
    get_language_code,
    is_token_expiring_soon,
)

_LOGGER = logging.getLogger(__name__)


class InPostApiClient:
    """Client for InPost APIs.

    Supports both authenticated endpoints (parcels, profile) and
    public endpoints (parcel lockers list).
    """

    PARCELS_ENDPOINT = "/v4/parcels/tracked"
    PROFILE_ENDPOINT = "/izi/app/shopping/v2/profile"
    TOKEN_ENDPOINT = "/global/oauth2/token"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: Optional[ConfigEntry] = None,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        on_token_refresh: Optional[Callable[[AuthTokens], None]] = None,
        ignored_en_route_statuses: Optional[List[str]] = None,
        http_timeout: int = DEFAULT_HTTP_TIMEOUT,
        parcel_lockers_url: str = DEFAULT_PARCEL_LOCKERS_URL,
        show_only_own_parcels: bool = DEFAULT_SHOW_ONLY_OWN_PARCELS,
    ) -> None:
        """Initialize the InPost API client.

        Args:
            hass: Home Assistant instance.
            entry: Optional config entry containing authentication data.
            access_token: Optional access token override.
            refresh_token: Optional refresh token override.
            on_token_refresh: Optional callback when token is refreshed.
            ignored_en_route_statuses: List of en_route statuses to ignore.
            http_timeout: HTTP request timeout in seconds.
            parcel_lockers_url: URL for fetching parcel lockers list.
            show_only_own_parcels: If True, only show parcels with OWN ownership.
        """
        self._parcel_lockers_url = parcel_lockers_url
        self._show_only_own_parcels = show_only_own_parcels
        self.hass = hass
        data = entry.data if entry and entry.data else {}
        self._access_token = access_token or data.get(CONF_ACCESS_TOKEN)
        self._refresh_token = refresh_token or data.get(CONF_REFRESH_TOKEN)
        self._on_token_refresh = on_token_refresh
        self._ignored_en_route_statuses = frozenset(
            ignored_en_route_statuses
            if ignored_en_route_statuses is not None
            else DEFAULT_IGNORED_EN_ROUTE_STATUSES
        )

        # Authenticated client for InPost mobile API
        self._http_client = HttpClient(
            auth_type="Bearer" if self._access_token else None,
            auth_value=self._access_token,
            custom_headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Accept-Language": get_language_code(hass.config.language),
            },
            default_timeout=http_timeout,
        )

        # Unauthenticated client for public endpoints
        self._public_http_client = HttpClient(
            custom_headers={
                "Accept": "application/json",
            },
            default_timeout=http_timeout,
        )

    async def _ensure_valid_token(self) -> None:
        """Ensure the access token is valid, refreshing if needed.

        Checks if the current access token is about to expire and
        refreshes it using the refresh token if necessary.

        Raises:
            ApiClientError: If token refresh fails.
        """
        if not self._access_token:
            return

        if not is_token_expiring_soon(self._access_token):
            return

        if not self._refresh_token:
            _LOGGER.warning("Access token is expiring but no refresh token available")
            return

        _LOGGER.info("Access token is expiring soon, refreshing...")
        await self.refresh_access_token()

    async def refresh_access_token(self) -> AuthTokens:
        """Refresh the access token using the refresh token.

        Returns:
            AuthTokens with new access and refresh tokens.

        Raises:
            ApiClientError: If token refresh fails.
        """
        if not self._refresh_token:
            raise ApiClientError("No refresh token available")

        response = await self._public_http_client.post(
            url=f"{API_BASE_URL}{self.TOKEN_ENDPOINT}",
            data={
                "client_id": OAUTH_CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
            },
            custom_headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "User-Agent": API_USER_AGENT,
            },
        )

        if response.is_error:
            _LOGGER.error("Token refresh failed with status %d", response.status)
            raise ApiClientError(
                f"Error refreshing access token! Status: {response.status}"
            )

        body = response.body
        tokens = AuthTokens(
            access_token=body.get("access_token", ""),
            refresh_token=body.get("refresh_token", ""),
            token_type=body.get("token_type", "Bearer"),
            expires_in=body.get("expires_in", 7199),
            scope=body.get("scope", "openid"),
            id_token=body.get("id_token"),
        )

        # Update internal state
        self._access_token = tokens.access_token
        self._refresh_token = tokens.refresh_token

        # Update HTTP client authorization header
        self._http_client.update_headers(
            {"Authorization": f"Bearer {tokens.access_token}"}
        )

        # Notify callback if set
        if self._on_token_refresh:
            self._on_token_refresh(tokens)

        _LOGGER.info("Access token refreshed successfully")
        return tokens

    async def get_parcels(self) -> ParcelsSummary:
        """Get tracked parcels and convert to ParcelsSummary.

        Returns:
            ParcelsSummary with parcels grouped by status.

        Raises:
            ApiClientError: If API request fails.
        """
        await self._ensure_valid_token()

        response = await self._http_client.get(
            url=f"{API_BASE_URL}{self.PARCELS_ENDPOINT}"
        )

        if response.is_error:
            _LOGGER.error("API request failed with status %d", response.status)
            raise ApiClientError(
                f"Error communicating with InPost API! Status: {response.status}"
            )

        # Convert camelCase keys to snake_case
        converted_data = convert_keys_to_snake_case(response.body)

        # Parse response using dacite
        dacite_config = Config(
            type_hooks={
                ApiLocation: lambda d: from_dict(ApiLocation, d, config=Config()),
                ApiAddressDetails: lambda d: from_dict(
                    ApiAddressDetails, d, config=Config()
                ),
                ApiPickUpPoint: lambda d: from_dict(ApiPickUpPoint, d, config=Config()),
                ApiPhoneNumber: lambda d: from_dict(ApiPhoneNumber, d, config=Config()),
                ApiReceiver: lambda d: from_dict(ApiReceiver, d, config=Config()),
                ApiSender: lambda d: from_dict(ApiSender, d, config=Config()),
                ApiCarbonFootprint: lambda d: from_dict(
                    ApiCarbonFootprint, d, config=Config()
                ),
            }
        )
        tracked_response = from_dict(
            TrackedParcelsResponse, converted_data, config=dacite_config
        )

        return self._build_parcels_summary(tracked_response.parcels)

    async def get_profile(self) -> UserProfile:
        """Get user profile with favorite lockers.

        Returns:
            UserProfile with delivery points and personal info.

        Raises:
            ApiClientError: If API request fails.
        """
        await self._ensure_valid_token()

        response = await self._http_client.get(
            url=f"{API_BASE_URL}{self.PROFILE_ENDPOINT}",
            custom_headers={
                # without this InPost API returns 500 Internal Server Error
                "User-Agent": API_USER_AGENT,
            },
        )

        if response.is_error:
            _LOGGER.warning(
                "Profile API request failed with status %d", response.status
            )
            raise ApiClientError(
                f"Error fetching profile from InPost API! Status: {response.status}"
            )

        # Convert camelCase keys to snake_case
        converted_data = convert_keys_to_snake_case(response.body)

        # Parse response using dacite
        dacite_config = Config(
            type_hooks={
                ProfilePersonal: lambda d: from_dict(
                    ProfilePersonal, d, config=Config()
                ),
                ProfileDelivery: lambda d: from_dict(
                    ProfileDelivery, d, config=Config()
                ),
                ProfileDeliveryPoints: lambda d: from_dict(
                    ProfileDeliveryPoints, d, config=Config()
                ),
                ProfileDeliveryPoint: lambda d: from_dict(
                    ProfileDeliveryPoint, d, config=Config()
                ),
                ProfileDeliveryAddresses: lambda d: from_dict(
                    ProfileDeliveryAddresses, d, config=Config()
                ),
                ProfileDeliveryAddress: lambda d: from_dict(
                    ProfileDeliveryAddress, d, config=Config()
                ),
                ProfileDeliveryAddressData: lambda d: from_dict(
                    ProfileDeliveryAddressData, d, config=Config()
                ),
                ProfileDeliveryAddressDetails: lambda d: from_dict(
                    ProfileDeliveryAddressDetails, d, config=Config()
                ),
            }
        )

        return from_dict(UserProfile, converted_data, config=dacite_config)

    async def get_parcel_lockers_list(self) -> list[InPostParcelLocker]:
        """Get parcel lockers list from public InPost endpoint.

        This method doesn't require authentication.

        Returns:
            List of parcel locker details.

        Raises:
            ApiClientError: If API request fails.
        """
        try:
            response = await self._public_http_client.get(url=self._parcel_lockers_url)

            if response.is_error:
                _LOGGER.error(
                    "Parcel lockers API request failed with status %d",
                    response.status,
                )
                raise ApiClientError(
                    f"Error fetching parcel lockers! Status: {response.status}"
                )

            response_data = from_dict(ParcelLockerListResponse, response.body)
            return response_data.items

        except ApiClientError:
            raise
        except Exception as exception:
            _LOGGER.error("Error fetching parcel lockers: %s", exception)
            raise ApiClientError("Error communicating with InPost API!") from exception

    def _build_parcels_summary(self, parcels: List[ApiParcel]) -> ParcelsSummary:
        """Build ParcelsSummary from list of parcels.

        Args:
            parcels: List of API parcels.

        Returns:
            ParcelsSummary with parcels grouped by status.
        """
        ready_for_pickup: Dict[str, Locker] = {}
        en_route: Dict[str, Locker] = {}

        ready_count = 0
        en_route_count = 0

        # Carbon footprint tracking
        daily_co2: Dict[str, Dict[str, float]] = {}  # {date: {co2, count}}
        total_co2 = 0.0
        total_delivered_parcels = 0

        for parcel in parcels:
            # Skip shared parcels if show_only_own_parcels is enabled
            if self._show_only_own_parcels and parcel.ownership_status != "OWN":
                continue

            locker_id = parcel.locker_id or "COURIER"

            if parcel.status == "READY_TO_PICKUP":
                ready_count += 1
                if locker_id not in ready_for_pickup:
                    ready_for_pickup[locker_id] = Locker(
                        locker_id=locker_id, count=0, parcels=[]
                    )
                ready_for_pickup[locker_id].parcels.append(parcel.to_parcel_item())
                ready_for_pickup[locker_id].count += 1

            elif (
                parcel.status in EN_ROUTE_STATUSES
                and parcel.status not in self._ignored_en_route_statuses
            ):
                en_route_count += 1
                if locker_id not in en_route:
                    en_route[locker_id] = Locker(
                        locker_id=locker_id, count=0, parcels=[]
                    )
                en_route[locker_id].parcels.append(parcel.to_parcel_item())
                en_route[locker_id].count += 1

            # Calculate carbon footprint for DELIVERED parcels
            if parcel.status == "DELIVERED":
                co2_value = parcel.effective_carbon_footprint
                pickup_date = parcel.pick_up_date_parsed

                if co2_value is not None and pickup_date is not None:
                    date_str = pickup_date.strftime("%Y-%m-%d")
                    if date_str not in daily_co2:
                        daily_co2[date_str] = {"co2": 0.0, "count": 0}
                    daily_co2[date_str]["co2"] += co2_value
                    daily_co2[date_str]["count"] += 1
                    total_co2 += co2_value
                    total_delivered_parcels += 1

        # Build carbon footprint stats
        daily_data = [
            DailyCarbonFootprint(
                date=date_str,
                value=data["co2"],
                parcel_count=int(data["count"]),
            )
            for date_str, data in sorted(daily_co2.items())
        ]

        carbon_stats = CarbonFootprintStats(
            total_co2_kg=round(total_co2, 4),
            total_parcels=total_delivered_parcels,
            daily_data=daily_data,
        )

        return ParcelsSummary(
            all_count=len(parcels),
            ready_for_pickup_count=ready_count,
            en_route_count=en_route_count,
            ready_for_pickup=ready_for_pickup,
            en_route=en_route,
            carbon_footprint_stats=carbon_stats,
        )

    async def close(self) -> None:
        """Close all HTTP client sessions."""
        await self._http_client.close()
        await self._public_http_client.close()


# Backwards compatibility aliases
CustomInpostApi = InPostApiClient
InPostApi = InPostApiClient
