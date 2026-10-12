"""Config flow: add a stove (pick or import a profile), and change settings later."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)
from homeassistant.util import slugify

from .const import (
    CONF_PROFILE,
    CONF_PROFILE_JSON,
    CONF_SOURCE,
    DEFAULT_PROFILE,
    DOMAIN,
    IMPORT_NEW,
)
from .profile import (
    ALLURE_50,
    BUILTIN_PROFILES,
    Profile,
    ProfileError,
    parse_profile_json,
    template_json,
)
from .profiles import async_get_profile_store, async_save_profile

# Only offer power sensors (watts).
_SOURCE_SELECTOR = EntitySelector(
    EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.POWER)
)
_JSON_SELECTOR = TextSelector(TextSelectorConfig(multiline=True))


def _profile_selector(names: list[str], allow_import: bool = False) -> SelectSelector:
    options = [SelectOptionDict(value=n, label=n) for n in names]
    if allow_import:
        options.append(
            SelectOptionDict(value=IMPORT_NEW, label="Import / design a new profile…")
        )
    return SelectSelector(
        SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
    )


def _check_profile_text(text: str) -> tuple[Profile | None, str | None]:
    """Return (profile, None) or (None, error message)."""
    try:
        profile = parse_profile_json(text)
    except ProfileError as err:
        return None, str(err)
    if profile.name in BUILTIN_PROFILES or profile.name == IMPORT_NEW:
        return None, None  # reserved name: caller shows the 'reserved_name' error
    return profile, None


class HarmanEasyTouchConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add one stove."""

    VERSION = 1

    def __init__(self) -> None:
        self._name: str = ""
        self._source: str = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        store = await async_get_profile_store(self.hass)
        if user_input is not None:
            self._name = user_input[CONF_NAME].strip()
            self._source = user_input[CONF_SOURCE]
            await self.async_set_unique_id(slugify(self._name))
            self._abort_if_unique_id_configured()
            if user_input[CONF_PROFILE] == IMPORT_NEW:
                return await self.async_step_import_profile()
            return self._create(user_input[CONF_PROFILE])

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): str,
                vol.Required(CONF_SOURCE): _SOURCE_SELECTOR,
                vol.Required(CONF_PROFILE, default=DEFAULT_PROFILE): _profile_selector(
                    store.names, allow_import=True
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_import_profile(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders = {"error": ""}
        schema = vol.Schema({vol.Required(CONF_PROFILE_JSON): _JSON_SELECTOR})

        if user_input is not None:
            profile, message = _check_profile_text(user_input[CONF_PROFILE_JSON])
            if message:
                errors["base"] = "invalid_profile"
                placeholders["error"] = message
            elif profile is None:
                errors["base"] = "reserved_name"
            else:
                await async_save_profile(self.hass, profile)
                return self._create(profile.name)
            suggested = user_input
        else:
            suggested = {CONF_PROFILE_JSON: template_json(ALLURE_50)}

        return self.async_show_form(
            step_id="import_profile",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
            errors=errors,
            description_placeholders=placeholders,
        )

    def _create(self, profile_name: str) -> ConfigFlowResult:
        return self.async_create_entry(
            title=self._name,
            data={CONF_NAME: self._name},
            options={CONF_SOURCE: self._source, CONF_PROFILE: profile_name},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return HarmanEasyTouchOptionsFlow()


class HarmanEasyTouchOptionsFlow(OptionsFlow):
    """Change source/profile, or import / design a profile."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init", menu_options=["settings", "import_profile"]
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        store = await async_get_profile_store(self.hass)
        options = self.config_entry.options
        if user_input is not None:
            return self.async_create_entry(data={**options, **user_input})
        schema = vol.Schema(
            {
                vol.Required(CONF_SOURCE, default=options.get(CONF_SOURCE)): _SOURCE_SELECTOR,
                vol.Required(
                    CONF_PROFILE, default=options.get(CONF_PROFILE, DEFAULT_PROFILE)
                ): _profile_selector(store.names),
            }
        )
        return self.async_show_form(step_id="settings", data_schema=schema)

    async def async_step_import_profile(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders = {"error": ""}
        schema = vol.Schema({vol.Required(CONF_PROFILE_JSON): _JSON_SELECTOR})

        if user_input is not None:
            profile, message = _check_profile_text(user_input[CONF_PROFILE_JSON])
            if message:
                errors["base"] = "invalid_profile"
                placeholders["error"] = message
            elif profile is None:
                errors["base"] = "reserved_name"
            else:
                return await self._save_and_apply(profile)
            suggested = user_input
        else:
            # Start from the current profile so it can be edited and saved under a new name.
            store = await async_get_profile_store(self.hass)
            name = self.config_entry.options.get(CONF_PROFILE, DEFAULT_PROFILE)
            suggested = {CONF_PROFILE_JSON: template_json(store.get(name) or ALLURE_50)}

        return self.async_show_form(
            step_id="import_profile",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def _save_and_apply(self, profile: Profile) -> ConfigFlowResult:
        await async_save_profile(
            self.hass, profile, skip_entry_id=self.config_entry.entry_id
        )
        options = {**self.config_entry.options, CONF_PROFILE: profile.name}
        if options == self.config_entry.options:
            # Same name re-imported: options don't change, so reload explicitly.
            self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)
        return self.async_create_entry(data=options)
