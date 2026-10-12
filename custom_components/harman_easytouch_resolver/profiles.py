"""Persistent storage for custom profiles."""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import CONF_PROFILE, DOMAIN
from .profile import BUILTIN_PROFILES, Profile, ProfileError

_LOGGER = logging.getLogger(__name__)
_KEY = f"{DOMAIN}.profiles"


class ProfileStore:
    """Built-in profiles plus user-saved custom profiles."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store = Store(hass, 1, _KEY)
        self._custom: dict[str, Profile] = {}

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        for name, raw in data.get("profiles", {}).items():
            try:
                self._custom[name] = Profile.from_dict(raw)
            except ProfileError as err:
                _LOGGER.warning("Ignoring invalid saved profile '%s': %s", name, err)

    @property
    def names(self) -> list[str]:
        return list(BUILTIN_PROFILES) + sorted(
            name for name in self._custom if name not in BUILTIN_PROFILES
        )

    def get(self, name: str) -> Profile | None:
        return BUILTIN_PROFILES.get(name) or self._custom.get(name)

    async def async_save(self, profile: Profile) -> None:
        self._custom[profile.name] = profile
        await self._store.async_save(
            {"profiles": {n: p.to_dict() for n, p in self._custom.items()}}
        )


async def async_get_profile_store(hass: HomeAssistant) -> ProfileStore:
    """Return the shared, loaded ProfileStore."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if "store" not in domain_data:
        store = ProfileStore(hass)
        await store.async_load()
        domain_data["store"] = store
    return domain_data["store"]


async def async_save_profile(
    hass: HomeAssistant, profile: Profile, skip_entry_id: str | None = None
) -> None:
    """Save a custom profile; stoves already using that name reload to pick it up."""
    store = await async_get_profile_store(hass)
    await store.async_save(profile)
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id != skip_entry_id and entry.options.get(CONF_PROFILE) == profile.name:
            hass.config_entries.async_schedule_reload(entry.entry_id)
