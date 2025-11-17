from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from custom_components.inpost_paczkomaty.coordinator import InpostDataCoordinator
from .api import CustomInpostApi
from .const import HA_ID_ENTRY_CONFIG

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.info(
        "Starting Inpost Paczkomaty with ha_id: %s", entry.data.get(HA_ID_ENTRY_CONFIG)
    )

    api_client = CustomInpostApi(hass, entry)
    coordinator = InpostDataCoordinator(hass, api_client)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
