"""Sensors: resolved state, general state, and two diagnostics (raw state, moving average)."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import GENERAL_STATE_OPTIONS, ORDER
from .entity import StoveEntity
from .runtime import StoveConfigEntry, StoveRuntime

# All state comes from one in-memory runtime; nothing is fetched, so no limit is needed.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: StoveConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    runtime = entry.runtime_data
    async_add_entities(
        [
            StoveStateSensor(runtime),
            StoveGeneralStateSensor(runtime),
            StoveRawStateSensor(runtime),
            StoveMovingAverageSensor(runtime),
        ]
    )


class StoveStateSensor(StoveEntity, SensorEntity):
    """The resolved state. Values match the old input_select options."""

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


class StoveGeneralStateSensor(StoveEntity, SensorEntity):
    """faulted / lighting / burning / cooldown / idle."""

    _attr_translation_key = "general_state"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = GENERAL_STATE_OPTIONS

    def __init__(self, runtime: StoveRuntime) -> None:
        super().__init__(runtime, "general_state")

    @property
    def native_value(self) -> str | None:
        return self.runtime.general_state


class StoveRawStateSensor(StoveEntity, SensorEntity):
    """What the power level says right now, before the per-state delays are applied.

    Handy for tuning a profile: compare it with the resolved State to see which delay held
    a change back.
    """

    _attr_translation_key = "raw_state"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ORDER
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, runtime: StoveRuntime) -> None:
        super().__init__(runtime, "raw_state")

    @property
    def native_value(self) -> str | None:
        return self.runtime.raw_state


class StoveMovingAverageSensor(StoveEntity, SensorEntity):
    """The 20 second average of the power sensor, the number the profile's thresholds use."""

    _attr_translation_key = "moving_average"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, runtime: StoveRuntime) -> None:
        super().__init__(runtime, "moving_average")

    @property
    def native_value(self) -> float | None:
        average = self.runtime.engine.moving_average
        return None if average is None else round(average, 1)
