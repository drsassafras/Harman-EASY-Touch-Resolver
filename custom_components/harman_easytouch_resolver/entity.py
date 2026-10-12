"""Shared entity base."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .runtime import StoveRuntime


class StoveEntity(RestoreEntity):
    """Base for all entities of one stove."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, runtime: StoveRuntime, key: str) -> None:
        self.runtime = runtime
        entry = runtime.entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Harman",
            model=runtime.profile.name,
        )

    @property
    def available(self) -> bool:
        return self.runtime.available

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.runtime.add_listener(self.async_write_ha_state))
