"""Functions to connect to InPost APIs."""

import logging
from typing import Dict, List, Optional

from dacite import Config, from_dict
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.inpost_paczkomaty.const import (
    API_BASE_URL,
    CONF_ACCESS_TOKEN,
)
from custom_components.inpost_paczkomaty.exceptions import ApiClientError
from custom_components.inpost_paczkomaty.http_client import HttpClient
from custom_components.inpost_paczkomaty.models import (
    ApiAddressDetails,
    ApiLocation,
    ApiParcel,
    ApiPhoneNumber,
    ApiPickUpPoint,
    ApiReceiver,
    ApiSender,
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
)

_LOGGER = logging.getLogger(__name__)


class InPostApiClient:
    """Client for InPost APIs.

    Supports both authenticated endpoints (parcels, profile) and
    public endpoints (parcel lockers list).
    """

    PARCELS_ENDPOINT = "/v4/parcels/tracked"
    PROFILE_ENDPOINT = "/izi/app/shopping/v2/profile"
    PARCEL_LOCKERS_URL = "https://inpost.pl/sites/default/files/points.json"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: Optional[ConfigEntry] = None,
        access_token: Optional[str] = None,
    ) -> None:
        """Initialize the InPost API client.

        Args:
            hass: Home Assistant instance.
            entry: Optional config entry containing authentication data.
            access_token: Optional access token override.
        """
        self.hass = hass
        data = entry.data if entry and entry.data else {}
        token = access_token or data.get(CONF_ACCESS_TOKEN)

        # Authenticated client for InPost mobile API
        self._http_client = HttpClient(
            auth_type="Bearer" if token else None,
            auth_value=token,
            custom_headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Accept-Language": get_language_code(hass.config.language),
            },
        )

        # Unauthenticated client for public endpoints
        self._public_http_client = HttpClient(
            custom_headers={
                "Accept": "application/json",
            }
        )

    async def get_parcels(self) -> ParcelsSummary:
        """Get tracked parcels and convert to ParcelsSummary.

        Returns:
            ParcelsSummary with parcels grouped by status.

        Raises:
            ApiClientError: If API request fails.
        """
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
        response = await self._http_client.get(
            url=f"{API_BASE_URL}{self.PROFILE_ENDPOINT}",
            custom_headers={
                # without this InPost API returns 500 Internal Server Error
                "User-Agent": "InPost-Mobile/4.4.2 (1)-release (iOS 26.2; iPhone15,3; pl)",
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
            response = await self._public_http_client.get(url=self.PARCEL_LOCKERS_URL)

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

        for parcel in parcels:
            locker_id = parcel.locker_id or "COURIER"

            if parcel.status == "READY_TO_PICKUP":
                ready_count += 1
                if locker_id not in ready_for_pickup:
                    ready_for_pickup[locker_id] = Locker(
                        locker_id=locker_id, count=0, parcels=[]
                    )
                ready_for_pickup[locker_id].parcels.append(parcel.to_parcel_item())
                ready_for_pickup[locker_id].count += 1

            elif parcel.status in EN_ROUTE_STATUSES:
                en_route_count += 1
                if locker_id not in en_route:
                    en_route[locker_id] = Locker(
                        locker_id=locker_id, count=0, parcels=[]
                    )
                en_route[locker_id].parcels.append(parcel.to_parcel_item())
                en_route[locker_id].count += 1

        return ParcelsSummary(
            all_count=len(parcels),
            ready_for_pickup_count=ready_count,
            en_route_count=en_route_count,
            ready_for_pickup=ready_for_pickup,
            en_route=en_route,
        )

    async def close(self) -> None:
        """Close all HTTP client sessions."""
        await self._http_client.close()
        await self._public_http_client.close()


# Backwards compatibility aliases
CustomInpostApi = InPostApiClient
InPostApi = InPostApiClient
