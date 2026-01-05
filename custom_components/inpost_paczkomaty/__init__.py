"""InPost Paczkomaty integration for Home Assistant."""

from __future__ import annotations

import logging
from typing import Any
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv

from custom_components.inpost_paczkomaty.coordinator import InpostDataCoordinator
from .api import InPostApiClient
from .const import (
    CONF_HTTP_TIMEOUT,
    CONF_IGNORED_EN_ROUTE_STATUSES,
    CONF_PARCEL_LOCKERS_URL,
    CONF_SHOW_ONLY_OWN_PARCELS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_HTTP_TIMEOUT,
    DEFAULT_IGNORED_EN_ROUTE_STATUSES,
    DEFAULT_PARCEL_LOCKERS_URL,
    DEFAULT_SHOW_ONLY_OWN_PARCELS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    ENTRY_PHONE_NUMBER_CONFIG,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

# Schema for configuration.yaml
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(
                    CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
                ): cv.positive_int,
                vol.Optional(
                    CONF_IGNORED_EN_ROUTE_STATUSES,
                    default=DEFAULT_IGNORED_EN_ROUTE_STATUSES,
                ): vol.All(cv.ensure_list, [cv.string]),
                vol.Optional(
                    CONF_HTTP_TIMEOUT, default=DEFAULT_HTTP_TIMEOUT
                ): cv.positive_int,
                vol.Optional(
                    CONF_PARCEL_LOCKERS_URL, default=DEFAULT_PARCEL_LOCKERS_URL
                ): cv.url,
                vol.Optional(
                    CONF_SHOW_ONLY_OWN_PARCELS, default=DEFAULT_SHOW_ONLY_OWN_PARCELS
                ): cv.boolean,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the InPost Paczkomaty component from configuration.yaml."""
    if DOMAIN in config:
        hass.data[DOMAIN] = config[DOMAIN]
    else:
        hass.data[DOMAIN] = {}
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up InPost Paczkomaty from a config entry."""
    _LOGGER.info(
        "Starting InPost Paczkomaty for phone: %s",
        entry.data.get(ENTRY_PHONE_NUMBER_CONFIG, "unknown"),
    )

    # Get configuration from configuration.yaml or use defaults
    domain_config = hass.data.get(DOMAIN, {})
    update_interval = domain_config.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    ignored_en_route_statuses = domain_config.get(
        CONF_IGNORED_EN_ROUTE_STATUSES, DEFAULT_IGNORED_EN_ROUTE_STATUSES
    )
    http_timeout = domain_config.get(CONF_HTTP_TIMEOUT, DEFAULT_HTTP_TIMEOUT)
    parcel_lockers_url = domain_config.get(
        CONF_PARCEL_LOCKERS_URL, DEFAULT_PARCEL_LOCKERS_URL
    )
    show_only_own_parcels = domain_config.get(
        CONF_SHOW_ONLY_OWN_PARCELS, DEFAULT_SHOW_ONLY_OWN_PARCELS
    )

    api_client = InPostApiClient(
        hass,
        entry,
        ignored_en_route_statuses=ignored_en_route_statuses,
        http_timeout=http_timeout,
        parcel_lockers_url=parcel_lockers_url,
        show_only_own_parcels=show_only_own_parcels,
    )
    coordinator = InpostDataCoordinator(hass, api_client, update_interval)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
