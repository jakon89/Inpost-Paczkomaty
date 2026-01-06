"""InPost API data coordinator."""

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import InPostApiClient
from .const import DEFAULT_UPDATE_INTERVAL
from .models import ParcelsSummary

_LOGGER = logging.getLogger(__name__)


class InpostDataCoordinator(DataUpdateCoordinator[ParcelsSummary]):
    """Data coordinator for InPost parcels API."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: InPostApiClient,
        update_interval_seconds: int = DEFAULT_UPDATE_INTERVAL,
    ) -> None:
        """Initialize the data coordinator.

        Args:
            hass: Home Assistant instance.
            api_client: InPost API client instance.
            update_interval_seconds: Data refresh interval in seconds.
        """
        super().__init__(
            hass,
            _LOGGER,
            name="InPost Paczkomaty data coordinator",
            update_interval=timedelta(seconds=update_interval_seconds),
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
            return await self.api_client.get_parcels()
        except Exception as err:
            _LOGGER.error("Cannot read parcels from InPost API: %s", err)
            raise UpdateFailed("Error fetching InPost parcels update") from err
