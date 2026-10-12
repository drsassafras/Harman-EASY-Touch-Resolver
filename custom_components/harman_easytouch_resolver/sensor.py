"""Sensors: resolved state (with raw_state / moving_average attributes) and general state."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import GENERAL_STATE_OPTIONS, ORDER
from .entity import StoveEntity
from .runtime import StoveConfigEntry, StoveRuntime


async def async_setup_entry(
    hass: HomeAssistant, entry: StoveConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    runtime = entry.runtime_data
    async_add_entities([StoveStateSensor(runtime), StoveGeneralStateSensor(runtime)])


class StoveStateSensor(StoveEntity, SensorEntity):
    """The resolved state. Values match the old input_select options."""

    _attr_name = "State"
    _attr_translation_key = "state"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ORDER

    def __init__(self, runtime: StoveRuntime) -> None:
        super().__init__(runtime, "state")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            self.runtime.engine.restore(last.state)

    @property
    def native_value(self) -> str | None:
        return self.runtime.state

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        return self.runtime.engine.attributes


class StoveGeneralStateSensor(StoveEntity, SensorEntity):
    """Faulted / Lighting / Burning / Cooldown / Idle."""

    _attr_name = "General state"
    _attr_translation_key = "general_state"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = GENERAL_STATE_OPTIONS

    def __init__(self, runtime: StoveRuntime) -> None:
        super().__init__(runtime, "general_state")

    @property
    def native_value(self) -> str | None:
        return self.runtime.general_state
