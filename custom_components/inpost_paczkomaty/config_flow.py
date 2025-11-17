"""Config flow for InPost Air integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectOptionDict,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from . import CustomInpostApi
from .const import DOMAIN, HA_ID_ENTRY_CONFIG, SECRET_ENTRY_CONFIG
from .utils import haversine

_LOGGER = logging.getLogger(__name__)


@dataclass
class SimpleParcelLocker:
    code: str
    description: str
    distance: float


USER_SCHEMA = vol.Schema(
    {
        vol.Required(
            "phone_number",
        ): TextSelector(TextSelectorConfig(type="text"))
    }
)

CODE_SCHEMA = vol.Schema(
    {
        vol.Required(
            "sms_code",
        ): TextSelector(TextSelectorConfig(type="text"))
    }
)


class InPostAirConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            phone_number = user_input["phone_number"]

            if not phone_number.isdigit() or not (9 == len(phone_number)):
                errors["base"] = "invalid_phone_format"
            else:
                mailbay_api_client = CustomInpostApi(self.hass, None)
                try:
                    ha_instance_data = await mailbay_api_client.register_ha_instance(
                        phone_number
                    )
                    _LOGGER.info(
                        "Registered HA instance and updated config entry: %s",
                        asdict(ha_instance_data),
                    )
                    self._data = {
                        "phone_number": phone_number,
                        SECRET_ENTRY_CONFIG: ha_instance_data.secret,
                        HA_ID_ENTRY_CONFIG: ha_instance_data.ha_id,
                    }

                    return await self.async_step_code()

                except Exception as e:
                    _LOGGER.error("Cannot register HA instance: %s", e)
                    errors["base"] = "phone_unknown_server_error"

        return self.async_show_form(
            step_id="user",
            data_schema=USER_SCHEMA,
            errors=errors,
        )

    async def async_step_code(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                mailbay_api_client = CustomInpostApi(self.hass, None)

                ha_instance_data = await mailbay_api_client.confirm_ha_instance(
                    self._data["ha_id"], self._data["secret"], user_input["sms_code"]
                )
                _LOGGER.info(
                    "Confirmed HA instance: %s",
                    asdict(ha_instance_data),
                )

                return self.async_create_entry(
                    title=f"Inpost: +48 {self._data['phone_number']}",
                    data=self._data,
                    options=user_input,
                )

            except Exception as e:
                _LOGGER.error("Cannot confirm HA instance: %s", e)
                errors["base"] = "invalid_code"

        return self.async_show_form(
            step_id="code",
            data_schema=CODE_SCHEMA,
            errors=errors,
        )

    async def async_step_lockers(self, user_input=None):
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

        options = [
            SelectOptionDict(
                label=f"{locker.code} [{locker.distance:.2f}km] ({locker.description})",
                value=locker.code,
            )
            for locker in sorted(parcel_lockers, key=lambda locker: locker.distance)
        ]

        if user_input is not None:
            return self.async_create_entry(
                title=self._data["phone_number"],
                data={},
                options=user_input,
            )

        return self.async_show_form(
            step_id="lockers",
            data_schema=vol.Schema(
                {
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
                }
            ),
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
            self.hass.config_entries.async_update_entry(self.entry, options=user_input)
            await self.hass.config_entries.async_reload(self.entry.entry_id)

            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
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
                }
            ),
        )
