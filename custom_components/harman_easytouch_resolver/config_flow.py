"""Config flow: add a stove (pick or import a profile), and change settings later."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)
from homeassistant.util import slugify

from .const import (
    CONF_EDIT_PROFILE,
    CONF_PROFILE,
    CONF_PROFILE_JSON,
    CONF_SOURCE,
    CONF_UNAVAILABLE_DELAY,
    DEFAULT_PROFILE,
    DEFAULT_UNAVAILABLE_DELAY,
    DOMAIN,
    IMPORT_NEW,
    MAX_UNAVAILABLE_DELAY,
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
_DELAY_SELECTOR = NumberSelector(
    NumberSelectorConfig(
        min=0,
        max=MAX_UNAVAILABLE_DELAY,
        step=1,
        mode=NumberSelectorMode.BOX,
        unit_of_measurement="s",
    )
)
_JSON_SELECTOR = TextSelector(TextSelectorConfig(multiline=True))


def _profile_selector(names: list[str], allow_import: bool = False) -> SelectSelector:
    options = [SelectOptionDict(value=n, label=n) for n in names]
    if allow_import:
        options.append(
            SelectOptionDict(value=IMPORT_NEW, label="Import / design a new profile…")
        )
    # translation_key translates the "import" entry; saved profile names have no
    # translation and are shown as they are.
    return SelectSelector(
        SelectSelectorConfig(
            options=options,
            mode=SelectSelectorMode.DROPDOWN,
            translation_key="profile",
        )
    )


def _check_profile_text(text: str) -> tuple[Profile | None, ProfileError | None]:
    """Return (profile, None) or (None, error). (None, None) means a reserved name."""
    try:
        profile = parse_profile_json(text)
    except ProfileError as err:
        return None, err
    if profile.name in BUILTIN_PROFILES or profile.name == IMPORT_NEW:
        return None, None  # reserved name: caller shows the 'reserved_name' error
    return profile, None


def _source_in_use(
    hass: HomeAssistant, source: str, exclude_entry_id: str | None = None
) -> bool:
    """True if another stove already watches this power sensor."""
    return any(
        entry.options.get(CONF_SOURCE) == source
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.entry_id != exclude_entry_id
    )


class HarmanEasyTouchConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add one stove."""

    VERSION = 1

    def __init__(self) -> None:
        self._name: str = ""
        self._source: str = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        store = await async_get_profile_store(self.hass)
        if user_input is not None:
            self._name = user_input[CONF_NAME].strip()
            self._source = user_input[CONF_SOURCE]
            await self.async_set_unique_id(slugify(self._name))
            self._abort_if_unique_id_configured()
            if _source_in_use(self.hass, self._source):
                errors["base"] = "source_in_use"
            elif user_input[CONF_PROFILE] == IMPORT_NEW:
                return await self.async_step_import_profile()
            else:
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
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_import_profile(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        schema = vol.Schema({vol.Required(CONF_PROFILE_JSON): _JSON_SELECTOR})

        if user_input is not None:
            profile, error = _check_profile_text(user_input[CONF_PROFILE_JSON])
            if error is not None:
                errors["base"] = error.code
                placeholders = dict(error.placeholders)
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

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Point an existing stove at a different power sensor."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            if _source_in_use(self.hass, user_input[CONF_SOURCE], entry.entry_id):
                errors["base"] = "source_in_use"
            else:
                # The entry's update listener reloads the stove when the options change.
                self.hass.config_entries.async_update_entry(
                    entry, options={**entry.options, CONF_SOURCE: user_input[CONF_SOURCE]}
                )
                return self.async_abort(reason="reconfigure_successful")

        schema = vol.Schema({vol.Required(CONF_SOURCE): _SOURCE_SELECTOR})
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                schema, user_input or {CONF_SOURCE: entry.options.get(CONF_SOURCE)}
            ),
            errors=errors,
        )

    def _create(self, profile_name: str) -> ConfigFlowResult:
        return self.async_create_entry(
            title=self._name,
            data={CONF_NAME: self._name},
            options={CONF_SOURCE: self._source, CONF_PROFILE: profile_name},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return HarmanEasyTouchOptionsFlow()


class HarmanEasyTouchOptionsFlow(OptionsFlow):
    """Change source/profile, and optionally edit the profile JSON."""

    def __init__(self) -> None:
        self._source: str | None = None
        self._profile: str | None = None
        self._delay: int = DEFAULT_UNAVAILABLE_DELAY

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        store = await async_get_profile_store(self.hass)
        options = self.config_entry.options

        if user_input is not None:
            if _source_in_use(
                self.hass, user_input[CONF_SOURCE], self.config_entry.entry_id
            ):
                errors["base"] = "source_in_use"
            else:
                self._source = user_input[CONF_SOURCE]
                self._profile = user_input[CONF_PROFILE]
                self._delay = int(user_input[CONF_UNAVAILABLE_DELAY])
                if user_input.get(CONF_EDIT_PROFILE):
                    return await self.async_step_import_profile()
                return self.async_create_entry(
                    data={
                        **options,
                        CONF_SOURCE: self._source,
                        CONF_PROFILE: self._profile,
                        CONF_UNAVAILABLE_DELAY: self._delay,
                    }
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_SOURCE): _SOURCE_SELECTOR,
                vol.Required(CONF_PROFILE): _profile_selector(store.names),
                vol.Required(
                    CONF_UNAVAILABLE_DELAY, default=DEFAULT_UNAVAILABLE_DELAY
                ): _DELAY_SELECTOR,
                vol.Optional(CONF_EDIT_PROFILE, default=False): bool,
            }
        )
        suggested = user_input or {
            CONF_SOURCE: options.get(CONF_SOURCE),
            CONF_PROFILE: options.get(CONF_PROFILE, DEFAULT_PROFILE),
            CONF_UNAVAILABLE_DELAY: options.get(
                CONF_UNAVAILABLE_DELAY, DEFAULT_UNAVAILABLE_DELAY
            ),
        }
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
            errors=errors,
        )

    async def async_step_import_profile(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        schema = vol.Schema({vol.Required(CONF_PROFILE_JSON): _JSON_SELECTOR})

        if user_input is not None:
            profile, error = _check_profile_text(user_input[CONF_PROFILE_JSON])
            if error is not None:
                errors["base"] = error.code
                placeholders = dict(error.placeholders)
            elif profile is None:
                errors["base"] = "reserved_name"
            else:
                return await self._save_and_apply(profile)
            suggested = user_input
        else:
            # Start from the selected profile so it can be edited and saved under a new name.
            store = await async_get_profile_store(self.hass)
            name = self._profile or self.config_entry.options.get(
                CONF_PROFILE, DEFAULT_PROFILE
            )
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
        options = {
            **self.config_entry.options,
            CONF_SOURCE: self._source or self.config_entry.options.get(CONF_SOURCE),
            CONF_PROFILE: profile.name,
            CONF_UNAVAILABLE_DELAY: self._delay,
        }
        if options == self.config_entry.options:
            # Same name re-imported: options don't change, so reload explicitly.
            self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)
        return self.async_create_entry(data=options)
