"""InPost API data coordinator."""

import asyncio
import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import InPostApiClient
from .models import ParcelsSummary

_LOGGER = logging.getLogger(__name__)


class InpostDataCoordinator(DataUpdateCoordinator[ParcelsSummary]):
    """Data coordinator for InPost parcels API."""

    def __init__(self, hass: HomeAssistant, api_client: InPostApiClient) -> None:
        """Initialize the data coordinator.

        Args:
            hass: Home Assistant instance.
            api_client: InPost API client instance.
        """
        super().__init__(
            hass,
            _LOGGER,
            name="InPost Paczkomaty data coordinator",
            update_interval=timedelta(seconds=30),
        )
        self.api_client = api_client

    async def _async_update_data(self) -> ParcelsSummary:
        """Fetch parcels data from InPost API.

        Returns:
            ParcelsSummary with current parcels data.

        Raises:
            UpdateFailed: If API request fails.
        """
        try:
            async with asyncio.timeout(30):
                return await self.api_client.get_parcels()

        except Exception as err:
            _LOGGER.error("Cannot read parcels from InPost API: %s", err)
            raise UpdateFailed("Error fetching InPost parcels update") from err
