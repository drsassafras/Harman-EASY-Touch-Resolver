"""Harman EasyTouch Resolver."""

from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import CONF_PROFILE, DEFAULT_PROFILE, DOMAIN
from .profile import ALLURE_50
from .profiles import async_get_profile_store
from .runtime import StoveConfigEntry, StoveRuntime

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]


def _issue_id(entry: StoveConfigEntry) -> str:
    return f"profile_missing_{entry.entry_id}"


async def async_setup_entry(hass: HomeAssistant, entry: StoveConfigEntry) -> bool:
    store = await async_get_profile_store(hass)
    name = entry.options.get(CONF_PROFILE, DEFAULT_PROFILE)
    profile = store.get(name)
    if profile is None:
        _LOGGER.warning("Profile '%s' not found; falling back to '%s'", name, ALLURE_50.name)
        profile = ALLURE_50
        ir.async_create_issue(
            hass,
            DOMAIN,
            _issue_id(entry),
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="profile_missing",
            translation_placeholders={
                "stove": entry.title,
                "profile": name,
                "fallback": ALLURE_50.name,
            },
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, _issue_id(entry))

    runtime = StoveRuntime(hass, entry, profile)
    entry.runtime_data = runtime

    # Entities first (so the main sensor can restore its last state), then start listening.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    runtime.async_start()
    entry.async_on_unload(runtime.async_stop)
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_update))
    return True


async def _async_reload_on_update(hass: HomeAssistant, entry: StoveConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: StoveConfigEntry) -> bool:
    ir.async_delete_issue(hass, DOMAIN, _issue_id(entry))
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
