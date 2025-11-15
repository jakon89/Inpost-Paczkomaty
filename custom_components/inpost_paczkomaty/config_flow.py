"""Config flow for InPost Air integration."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, asdict

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectOptionDict, SelectSelectorMode,
)

from . import MailbayInpostApi
from .const import DOMAIN, MAX_ENTRIES
from .utils import haversine

_LOGGER = logging.getLogger(__name__)


@dataclass
class SimpleParcelLocker:
    code: str
    description: str
    distance: float


class InPostAirConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        from .api import InPostApi

        existing_entries = self._async_current_entries()
        if len(existing_entries) > MAX_ENTRIES:
            return self.async_abort(
                reason=f"max_entries"
            )

        parcel_lockers = [
            SimpleParcelLocker(
                code=locker.n,
                description=locker.d,
                distance=haversine(
                    self.hass.config.longitude,
                    self.hass.config.latitude,
                    locker.l.o,
                    locker.l.a,
                ),
            )
            for locker in await InPostApi(self.hass).get_parcel_lockers_list()
        ]

        # Build options for SelectSelector
        options = [
            SelectOptionDict(
                label=f"{locker.code} [{locker.distance:.2f}km] ({locker.description})",
                value=locker.code,
            )
            for locker in sorted(parcel_lockers, key=lambda locker: locker.distance)
        ]

        if user_input is not None:
            mailbay_api_client = MailbayInpostApi(self.hass, None)

            try:
                ha_instance_data = await mailbay_api_client.register_ha_instance(uuid.uuid4())
                _LOGGER.info("Registered HA instance and updated config entry: %s", asdict(ha_instance_data))

                return self.async_create_entry(title=f"Forwarding address: parcels@{ha_instance_data.domain}", data={**asdict(ha_instance_data)}, options=user_input)
            except Exception as e:
                _LOGGER.error("Cannot register HA instance: %s", e)
                return self.async_abort(
                    reason=f"cannot_register_ha_instance"
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(
                    "lockers",
                    default=[],
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        multiple=True,
                        custom_value=False,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }),
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry):
        return InPostAirOptionsFlow(entry)

class InPostAirOptionsFlow(config_entries.OptionsFlow):
    """Allow user to pick which lockers they want to track."""

    def __init__(self, entry):
        self.entry = entry

    async def async_step_init(self, user_input=None):
        """Show the list of lockers fetched by coordinator."""
        from .api import InPostApi

        parcel_lockers = [
            SimpleParcelLocker(
                code=locker.n,
                description=locker.d,
                distance=haversine(
                    self.hass.config.longitude,
                    self.hass.config.latitude,
                    locker.l.o,
                    locker.l.a,
                ),
            )
            for locker in await InPostApi(self.hass).get_parcel_lockers_list()
        ]

        # Build options for SelectSelector
        options = [
            SelectOptionDict(
                label=f"{locker.code} [{locker.distance:.2f}km] ({locker.description})",
                value=locker.code,
            )
            for locker in sorted(parcel_lockers, key=lambda locker: locker.distance)
        ]

        # Default selection = previously selected ones
        current = self.entry.options.get("lockers", [])

        if user_input is not None:
            self.hass.config_entries.async_update_entry(
                self.entry, options=user_input
            )
            await self.hass.config_entries.async_reload(self.entry.entry_id)

            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    "lockers",
                    default=current,
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        multiple=True,
                        custom_value=False,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }),
        )
