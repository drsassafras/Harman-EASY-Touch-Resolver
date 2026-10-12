"""Per-stove runtime: glues the engine to Home Assistant."""

from __future__ import annotations

from collections.abc import Callable
import math
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers.event import async_call_later, async_track_state_change_event

from .const import CONF_SOURCE, GENERAL_STATE_MAP
from .engine import StoveEngine
from .profile import Profile


class StoveRuntime:
    """Owns one stove's engine and notifies entities when anything changes."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, profile: Profile) -> None:
        self.hass = hass
        self.entry = entry
        self.profile = profile
        self.available = False
        self.engine = StoveEngine(profile, self._schedule, self._notify)
        self._listeners: list[Callable[[], None]] = []
        self._unsub: Callable[[], None] | None = None

    # -- derived values ---------------------------------------------------

    @property
    def state(self) -> str | None:
        return self.engine.committed

    @property
    def general_state(self) -> str | None:
        return GENERAL_STATE_MAP.get(self.engine.committed) if self.engine.committed else None

    # -- lifecycle ----------------------------------------------------------

    @callback
    def async_start(self) -> None:
        source = self.entry.options[CONF_SOURCE]
        self._unsub = async_track_state_change_event(
            self.hass, [source], self._handle_source_event
        )
        self._apply(self.hass.states.get(source))

    @callback
    def async_stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
        self.engine.shutdown()

    # -- listeners ----------------------------------------------------------

    @callback
    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)

        @callback
        def remove() -> None:
            self._listeners.remove(listener)

        return remove

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    # -- internals ----------------------------------------------------------

    def _schedule(self, delay: float, func: Callable[[], None]) -> Callable[[], None]:
        @callback
        def _fire(_now) -> None:
            func()

        return async_call_later(self.hass, delay, _fire)

    @callback
    def _handle_source_event(self, event: Event[EventStateChangedData]) -> None:
        self._apply(event.data["new_state"])

    def _apply(self, state: State | None) -> None:
        value: float | None = None
        if state is not None and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            try:
                value = float(state.state)
            except ValueError:
                value = None
            if value is not None and not math.isfinite(value):
                value = None

        if value is None:
            self.engine.reset_source()
            self.available = False
            self._notify()
            return

        self.available = True
        self.engine.update_power(value, time.monotonic())
        self._notify()


type StoveConfigEntry = ConfigEntry[StoveRuntime]
