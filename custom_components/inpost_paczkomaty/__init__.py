"""InPost Paczkomaty integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from custom_components.inpost_paczkomaty.coordinator import InpostDataCoordinator
from .api import InPostApiClient
from .const import ENTRY_PHONE_NUMBER_CONFIG

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up InPost Paczkomaty from a config entry."""
    _LOGGER.info(
        "Starting InPost Paczkomaty for phone: %s",
        entry.data.get(ENTRY_PHONE_NUMBER_CONFIG, "unknown"),
    )

    api_client = InPostApiClient(hass, entry)
    coordinator = InpostDataCoordinator(hass, api_client)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
