"""Functions to connect to InPost APIs."""

import logging
from typing import Dict, List, Optional

from dacite import Config, from_dict
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

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
    ParcelsSummary,
    TrackedParcelsResponse,
)
from custom_components.inpost_paczkomaty.utils import (
    convert_keys_to_snake_case,
    get_language_code,
)

_LOGGER = logging.getLogger(__name__)


class InPostApiClient:
    """Client for official InPost API using Bearer token authentication."""

    PARCELS_ENDPOINT = "/v4/parcels/tracked"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        access_token: Optional[str] = None,
    ) -> None:
        """Initialize the InPost API client.

        Args:
            hass: Home Assistant instance.
            entry: Config entry containing authentication data.
            access_token: Optional access token override.
        """
        self.hass = hass
        data = entry.data if entry and entry.data else {}
        token = access_token or data.get(CONF_ACCESS_TOKEN)

        self._http_client = HttpClient(
            auth_type="Bearer",
            auth_value=token,
            custom_headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Accept-Language": get_language_code(hass.config.language),
            },
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
        """Close the HTTP client session."""
        await self._http_client.close()


# Backwards compatibility alias
CustomInpostApi = InPostApiClient


class InPostApi:
    """Legacy API client for InPost parcel locker locations."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the legacy API client."""
        self.hass = hass
        self.session = async_create_clientsession(hass)

    async def get_parcel_lockers_list(self) -> list[InPostParcelLocker]:
        """Get parcel lockers list from public InPost endpoint.

        Returns:
            List of parcel locker details.

        Raises:
            ApiClientError: If API request fails.
        """
        try:
            async with self.session.get(
                "https://inpost.pl/sites/default/files/points.json"
            ) as response:
                response.raise_for_status()
                data = await response.json()

                # Parse response
                from dataclasses import dataclass

                @dataclass
                class ParcelLockerListResponse:
                    date: str
                    page: int
                    total_pages: int
                    items: list[InPostParcelLocker]

                response_data = from_dict(ParcelLockerListResponse, data)
                return response_data.items

        except Exception as exception:
            _LOGGER.error("Error fetching parcel lockers: %s", exception)
            raise ApiClientError("Error communicating with InPost API!") from exception
