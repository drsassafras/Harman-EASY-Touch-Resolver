"""Binary sensor: is the stove active?"""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ACTIVE_GENERAL_STATES
from .entity import StoveEntity
from .runtime import StoveConfigEntry, StoveRuntime


async def async_setup_entry(
    hass: HomeAssistant, entry: StoveConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([StoveActiveBinarySensor(entry.runtime_data)])


class StoveActiveBinarySensor(StoveEntity, BinarySensorEntity):
    """On while the general state is Lighting or Burning."""

    _attr_name = "Active"
    _attr_translation_key = "active"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, runtime: StoveRuntime) -> None:
        super().__init__(runtime, "active")

    @property
    def is_on(self) -> bool | None:
        general = self.runtime.general_state
        return None if general is None else general in ACTIVE_GENERAL_STATES
