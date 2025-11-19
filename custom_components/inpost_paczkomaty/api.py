"""Functions to connect to InPost APIs."""

import asyncio
import logging
from dataclasses import dataclass

from aiohttp import ClientResponse
from dacite import from_dict
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from aiohttp import ClientResponseError

from custom_components.inpost_paczkomaty.const import (
    HA_ID_ENTRY_CONFIG,
    SECRET_ENTRY_CONFIG,
)
from custom_components.inpost_paczkomaty.models import (
    InPostParcelLocker,
    HaInstance,
    ParcelsSummary,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class ParcelLockerListResponse:
    date: str
    page: int
    total_pages: int
    items: list[InPostParcelLocker]


class CustomInpostApi:
    BASE_URL = "https://inpost.mailbay.io"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Init class."""
        self.session = async_create_clientsession(hass)
        data = entry.data if entry and entry.data else {}
        self._ha_id = data.get(HA_ID_ENTRY_CONFIG)
        self._secret = data.get(SECRET_ENTRY_CONFIG)

    async def get_parcels(self) -> ParcelsSummary:
        """Get parcel lockers list."""
        response = await self._request(
            method="get",
            url=f"{self.BASE_URL}/api/ha_instance/{self._ha_id}/parcels?secret={self._secret}",
        )
        response_data = from_dict(ParcelsSummary, await response.json())

        return response_data

    async def confirm_ha_instance(
        self, ha_id: str, secret: str, code: str
    ) -> HaInstance:
        response = await self._request(
            method="put",
            url=f"{self.BASE_URL}/api/ha_instance/{ha_id}?secret={secret}",
            data={"code": code},
        )

        return from_dict(HaInstance, await response.json())

    async def register_ha_instance(self, phone: str) -> HaInstance:
        response = await self._request(
            method="post",
            url=f"{self.BASE_URL}/api/ha_instance",
            data={"phone": phone},
        )

        return from_dict(HaInstance, await response.json())

    async def _request(
        self, method: str, url: str, data: dict | None = None
    ) -> ClientResponse:
        """Get information from the API."""
        try:
            async with asyncio.timeout(60):
                response = await self.session.request(
                    method=method,
                    url=url,
                    data=data,
                    headers={"X-HA-Integration": "InPost Paczkomaty"},
                )
                response.raise_for_status()

                return response

        except ClientResponseError as e:
            if e.status == 429:
                raise RateLimitedError("Too many requests (429)") from e
            raise ApiClientError(
                f"Error communicating with API! Status: {e.status}"
            ) from e

        except TimeoutError as e:
            _LOGGER.warning("Request timed out")
            raise ApiClientError("Request timed out") from e
        except Exception as exception:  # pylint: disable=broad-except
            _LOGGER.warning("Unknown API error occurred: %s", exception)

            raise ApiClientError("Error communicating with API!") from exception


class InPostApi:
    def __init__(self, hass: HomeAssistant) -> None:
        """Init class."""
        self.hass = hass
        self.session = async_create_clientsession(hass)

    async def _request(
        self,
        method: str,
        url: str,
        headers: dict | None = None,
    ) -> ClientResponse:
        """Get information from the API."""
        try:
            async with asyncio.timeout(30):
                response = await self.session.request(
                    method=method,
                    url=url,
                    headers=headers,
                )
                response.raise_for_status()

                return response

        except TimeoutError as e:
            _LOGGER.warning("Request timed out")
            raise ApiClientError("Request timed out") from e
        except Exception as exception:  # pylint: disable=broad-except
            raise ApiClientError("Error communicating with InPost API!") from exception

    async def get_parcel_lockers_list(self) -> list[InPostParcelLocker]:
        """Get parcel lockers list."""
        response = await self._request(
            method="get", url="https://inpost.pl/sites/default/files/points.json"
        )
        response_data = from_dict(ParcelLockerListResponse, await response.json())

        return response_data.items


class ApiClientError(Exception):
    """Exception to indicate a general API error."""


class RateLimitedError(Exception):
    """Raised when API returns HTTP 429."""

    pass
