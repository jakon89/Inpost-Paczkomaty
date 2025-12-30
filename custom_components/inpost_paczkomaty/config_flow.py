"""Config flow for InPost Paczkomaty integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

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

from .const import (
    DOMAIN,
    ENTRY_PHONE_NUMBER_CONFIG,
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN_EXPIRES_IN,
    CONF_TOKEN_TYPE,
)
from .exceptions import (
    IdentityAdditionLimitReachedError,
    InPostApiError,
    InvalidOtpCodeError,
    RateLimitError,
)
from .inpost_auth_flow import InpostAuth
from .utils import haversine

_LOGGER = logging.getLogger(__name__)


@dataclass
class SimpleParcelLocker:
    """Simple parcel locker data container."""

    code: str
    description: str
    city: str
    street: str
    building: str
    zip_code: str
    latitude: float
    longitude: float
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


class InPostConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle InPost Paczkomaty config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict = {}
        self._auth: InpostAuth | None = None
        self._lockers_map: dict[str, SimpleParcelLocker] = {}

    async def _cleanup_auth(self) -> None:
        """Clean up the authentication session."""
        if self._auth:
            await self._auth.close()
            self._auth = None

    async def async_step_user(self, user_input=None):
        """Handle the initial step - phone number input."""
        errors: dict[str, str] = {}

        if user_input is not None:
            phone_number = user_input["phone_number"].strip()

            # Validate phone number format (9 digits)
            if not phone_number.isdigit() or len(phone_number) != 9:
                errors["base"] = "invalid_phone_format"
            else:
                try:
                    # Initialize InPost OAuth2 authentication
                    self._auth = InpostAuth(language=self.hass.config.language)

                    # Step 1: Initialize OAuth session
                    await self._auth.initialize_session()

                    # Step 2: Fetch XSRF token
                    auth_step = await self._auth.fetch_xsrf_token()
                    _LOGGER.debug("Initial auth step: %s", auth_step.step)

                    # Step 3: Submit phone number (with Polish country code)
                    phone_with_code = f"+48{phone_number}"
                    auth_step = await self._auth.submit_phone_number(phone_with_code)
                    _LOGGER.info(
                        "Phone number submitted, next step: %s", auth_step.step
                    )

                    # Store phone number for later use
                    self._data = {
                        ENTRY_PHONE_NUMBER_CONFIG: phone_number,
                    }

                    return await self.async_step_code()

                except RateLimitError as e:
                    _LOGGER.error("Rate limit exceeded: %s", e)
                    errors["base"] = "rate_limited_error"
                    await self._cleanup_auth()

                except IdentityAdditionLimitReachedError as e:
                    _LOGGER.error("Identity addition limit reached: %s", e)
                    errors["base"] = "identity_limit_reached"
                    await self._cleanup_auth()

                except InPostApiError as e:
                    _LOGGER.error("InPost API error: %s", e)
                    errors["base"] = "phone_unknown_server_error"
                    await self._cleanup_auth()

                except Exception as e:
                    _LOGGER.exception("Unexpected error during phone submission: %s", e)
                    errors["base"] = "phone_unknown_server_error"
                    await self._cleanup_auth()

        return self.async_show_form(
            step_id="user",
            data_schema=USER_SCHEMA,
            errors=errors,
        )

    async def async_step_code(self, user_input=None):
        """Handle OTP code verification step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                if not self._auth:
                    _LOGGER.error("Authentication session not found")
                    return await self.async_step_user()

                # Step 4: Submit OTP code
                otp_code = user_input["sms_code"].strip()
                auth_step = await self._auth.submit_otp_code(otp_code)
                _LOGGER.info("OTP submitted, step: %s", auth_step.step)

                # Check current step after OTP submission
                auth_step = await self._auth.get_current_step()

                # Step 5: Check if email confirmation is required
                requires_email, hashed_email = auth_step.requires_email
                if requires_email:
                    _LOGGER.info("Email confirmation required for: %s", hashed_email)
                    self._data["hashed_email"] = hashed_email
                    return await self.async_step_email_confirm()

                # If onboarded, proceed to get tokens
                if auth_step.is_onboarded:
                    return await self._complete_authentication()

                # Handle unexpected step
                _LOGGER.warning("Unexpected auth step: %s", auth_step.step)
                errors["base"] = "unexpected_auth_step"

            except InvalidOtpCodeError as e:
                _LOGGER.error("Invalid OTP code: %s", e)
                errors["base"] = "invalid_code"

            except RateLimitError as e:
                _LOGGER.error("Rate limit exceeded: %s", e)
                errors["base"] = "rate_limited_error"

            except InPostApiError as e:
                _LOGGER.error("InPost API error during OTP: %s", e)
                errors["base"] = "invalid_code"

            except Exception as e:
                _LOGGER.exception("Unexpected error during OTP verification: %s", e)
                errors["base"] = "invalid_code"

        return self.async_show_form(
            step_id="code",
            data_schema=CODE_SCHEMA,
            errors=errors,
        )

    async def async_step_email_confirm(self, user_input=None):
        """Handle email confirmation step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                if not self._auth:
                    _LOGGER.error("Authentication session not found")
                    return await self.async_step_user()

                # Check if email was confirmed
                auth_step = await self._auth.get_current_step()

                if auth_step.is_onboarded:
                    return await self._complete_authentication()

                # Still waiting for email confirmation
                errors["base"] = "email_not_confirmed"

            except Exception as e:
                _LOGGER.exception("Error checking email confirmation: %s", e)
                errors["base"] = "email_confirmation_error"

        else:
            # First time showing this step - send email confirmation request
            try:
                if self._auth:
                    await self._auth.request_email_confirmation()
                    _LOGGER.info("Email confirmation request sent")
            except Exception as e:
                _LOGGER.error("Failed to send email confirmation request: %s", e)
                errors["base"] = "email_confirmation_error"

        return self.async_show_form(
            step_id="email_confirm",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={
                "hashed_email": self._data.get("hashed_email", ""),
            },
        )

    async def _complete_authentication(self):
        """Complete authentication and proceed to locker selection."""
        try:
            if not self._auth:
                _LOGGER.error("Authentication session not found")
                return await self.async_step_user()

            # Step 7: Fetch authorization code
            auth_code = await self._auth.fetch_authorization_code()
            _LOGGER.debug("Authorization code obtained")

            # Exchange code for tokens
            tokens = await self._auth.exchange_code_for_tokens(auth_code)
            _LOGGER.info("Tokens obtained successfully")

            # Store tokens in config entry data
            self._data[CONF_ACCESS_TOKEN] = tokens.access_token
            self._data[CONF_REFRESH_TOKEN] = tokens.refresh_token
            self._data[CONF_TOKEN_EXPIRES_IN] = tokens.expires_in
            self._data[CONF_TOKEN_TYPE] = tokens.token_type

            # Clean up auth session
            await self._cleanup_auth()

            # Proceed to locker selection step
            return await self.async_step_lockers()

        except InPostApiError as e:
            _LOGGER.error("Failed to get tokens: %s", e)
            await self._cleanup_auth()
            return self.async_abort(reason="token_exchange_failed")

        except Exception as e:
            _LOGGER.exception("Unexpected error during token exchange: %s", e)
            await self._cleanup_auth()
            return self.async_abort(reason="token_exchange_failed")

    async def _get_favorite_lockers(self) -> list[str]:
        """Fetch favorite lockers from user profile.

        Returns:
            List of favorite locker codes, or empty list if unavailable.
        """
        from .api import InPostApiClient

        try:
            # Create a temporary API client with the access token
            class TempEntry:
                data = {CONF_ACCESS_TOKEN: self._data.get(CONF_ACCESS_TOKEN)}

            api_client = InPostApiClient(
                self.hass,
                TempEntry(),
                access_token=self._data.get(CONF_ACCESS_TOKEN),
            )

            profile = await api_client.get_profile()
            await api_client.close()

            favorite_lockers = profile.get_favorite_locker_codes()
            _LOGGER.info(
                "Found %d favorite lockers from profile", len(favorite_lockers)
            )
            return favorite_lockers

        except Exception as e:
            _LOGGER.warning("Failed to fetch favorite lockers: %s", e)
            return []

    async def async_step_lockers(self, user_input=None):
        """Handle parcel locker selection step."""
        from .api import InPostApiClient
        from .exceptions import ApiClientError

        errors: dict[str, str] = {}

        if user_input is not None:
            # User submitted locker selection - create the config entry
            phone_number = self._data.get(ENTRY_PHONE_NUMBER_CONFIG, "")
            selected_codes = user_input.get("lockers", [])
            # Build lockers list with full data
            lockers_data = []
            for code in selected_codes:
                locker = self._lockers_map.get(code)
                if locker:
                    lockers_data.append(
                        {
                            "code": locker.code,
                            "description": locker.description,
                            "city": locker.city,
                            "street": locker.street,
                            "building": locker.building,
                            "zip_code": locker.zip_code,
                            "latitude": locker.latitude,
                            "longitude": locker.longitude,
                        }
                    )
                else:
                    lockers_data.append({"code": code})
            return self.async_create_entry(
                title=f"InPost: +48 {phone_number}",
                data=self._data,
                options={"lockers": lockers_data},
            )

        # Fetch all available parcel lockers
        parcel_lockers: list[SimpleParcelLocker] = []
        api_client = InPostApiClient(self.hass)
        try:
            raw_lockers = await api_client.get_parcel_lockers_list()
            parcel_lockers = [
                SimpleParcelLocker(
                    code=locker.n,
                    description=locker.d,
                    city=locker.c,
                    street=locker.e,
                    building=locker.b,
                    zip_code=locker.o,
                    latitude=locker.l.a,
                    longitude=locker.l.o,
                    distance=haversine(
                        self.hass.config.longitude,
                        self.hass.config.latitude,
                        locker.l.o,
                        locker.l.a,
                    ),
                )
                for locker in raw_lockers
            ]
            # Store lockers for later use when saving
            self._lockers_map = {locker.code: locker for locker in parcel_lockers}
        except ApiClientError as e:
            _LOGGER.error("Failed to fetch parcel lockers: %s", e)
            errors["base"] = "cannot_fetch_lockers"
        except Exception as e:
            _LOGGER.exception("Unexpected error fetching parcel lockers: %s", e)
            errors["base"] = "cannot_fetch_lockers"
        finally:
            await api_client.close()

        # Build options sorted by distance
        locker_codes = {locker.code for locker in parcel_lockers}
        options = [
            SelectOptionDict(
                label=(
                    f"{locker.code} [{locker.distance:.2f}km] "
                    f"({locker.description} - {locker.city}, {locker.street} {locker.building})"
                ),
                value=locker.code,
            )
            for locker in sorted(parcel_lockers, key=lambda locker: locker.distance)
        ]

        # Get favorite lockers from profile API for pre-selection
        favorite_lockers = await self._get_favorite_lockers()

        # Filter to only include lockers that exist in the options
        default_lockers = [code for code in favorite_lockers if code in locker_codes]

        return self.async_show_form(
            step_id="lockers",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "lockers",
                        default=default_lockers,
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
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry):
        """Get the options flow handler."""
        return InPostOptionsFlow(entry)


class InPostOptionsFlow(config_entries.OptionsFlow):
    """Handle InPost Paczkomaty options flow."""

    def __init__(self, entry):
        """Initialize options flow."""
        self.entry = entry
        self._lockers_map: dict[str, SimpleParcelLocker] = {}

    async def async_step_init(self, user_input=None):
        """Show the list of lockers fetched by coordinator."""
        from .api import InPostApiClient
        from .exceptions import ApiClientError

        errors: dict[str, str] = {}

        if user_input is not None:
            selected_codes = user_input.get("lockers", [])
            # Build lockers list with full data
            lockers_data = []
            for code in selected_codes:
                locker = self._lockers_map.get(code)
                if locker:
                    lockers_data.append(
                        {
                            "code": locker.code,
                            "description": locker.description,
                            "city": locker.city,
                            "street": locker.street,
                            "building": locker.building,
                            "zip_code": locker.zip_code,
                            "latitude": locker.latitude,
                            "longitude": locker.longitude,
                        }
                    )
                else:
                    lockers_data.append({"code": code})
            options_data = {"lockers": lockers_data}
            self.hass.config_entries.async_update_entry(
                self.entry, options=options_data
            )
            await self.hass.config_entries.async_reload(self.entry.entry_id)

            return self.async_create_entry(title="", data=options_data)

        # Fetch parcel lockers with error handling
        parcel_lockers: list[SimpleParcelLocker] = []
        api_client = InPostApiClient(self.hass)
        try:
            raw_lockers = await api_client.get_parcel_lockers_list()
            parcel_lockers = [
                SimpleParcelLocker(
                    code=locker.n,
                    description=locker.d,
                    city=locker.c,
                    street=locker.e,
                    building=locker.b,
                    zip_code=locker.o,
                    latitude=locker.l.a,
                    longitude=locker.l.o,
                    distance=haversine(
                        self.hass.config.longitude,
                        self.hass.config.latitude,
                        locker.l.o,
                        locker.l.a,
                    ),
                )
                for locker in raw_lockers
            ]
            # Store lockers for later use when saving
            self._lockers_map = {locker.code: locker for locker in parcel_lockers}
        except ApiClientError as e:
            _LOGGER.error("Failed to fetch parcel lockers: %s", e)
            errors["base"] = "cannot_fetch_lockers"
        except Exception as e:
            _LOGGER.exception("Unexpected error fetching parcel lockers: %s", e)
            errors["base"] = "cannot_fetch_lockers"
        finally:
            await api_client.close()

        # Build options for SelectSelector
        options = [
            SelectOptionDict(
                label=(
                    f"{locker.code} [{locker.distance:.2f}km] "
                    f"({locker.description} - {locker.city}, {locker.street} {locker.building})"
                ),
                value=locker.code,
            )
            for locker in sorted(parcel_lockers, key=lambda locker: locker.distance)
        ]

        # Default selection = previously selected ones (handle both old and new format)
        current_lockers = self.entry.options.get("lockers", [])
        if current_lockers and isinstance(current_lockers[0], dict):
            # New format: list of dicts with code and description
            current = [locker["code"] for locker in current_lockers]
        else:
            # Old format: list of codes (for backwards compatibility)
            current = current_lockers

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
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
            errors=errors,
        )
