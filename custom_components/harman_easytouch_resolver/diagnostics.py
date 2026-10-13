"""Diagnostics for a stove."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .runtime import StoveConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: StoveConfigEntry
) -> dict[str, Any]:
    """Return what is needed to understand why a stove is in its current state."""
    runtime = entry.runtime_data
    source = hass.states.get(runtime.source_entity)
    return {
        "entry": {"title": entry.title, "options": dict(entry.options)},
        "profile": runtime.profile.to_dict(),
        "runtime": {
            "available": runtime.available,
            "source_status": runtime.source_status,
            "keep_last_state_seconds": runtime.grace_seconds,
            "state": runtime.state,
            "general_state": runtime.general_state,
            "raw_state": runtime.raw_state,
            **runtime.engine.attributes,
        },
        "source": (
            None
            if source is None
            else {
                "entity_id": source.entity_id,
                "state": source.state,
                "unit_of_measurement": source.attributes.get("unit_of_measurement"),
                "device_class": source.attributes.get("device_class"),
            }
        ),
    }
