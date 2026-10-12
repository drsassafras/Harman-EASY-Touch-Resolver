"""Per-stove runtime: glues the engine to Home Assistant."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
import math
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import (
    Event,
    EventStateChangedData,
    EventStateReportedData,
    HassJob,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_state_report_event,
)

from .const import (
    CONF_SOURCE,
    CONF_UNAVAILABLE_DELAY,
    DEFAULT_UNAVAILABLE_DELAY,
    GENERAL_STATE_MAP,
    MOVING_AVERAGE_SECONDS,
)
from .engine import StoveEngine
from .profile import Profile


class _Source(Enum):
    """What the runtime currently knows about the power sensor."""

    UNSEEN = "unseen"  # nothing evaluated yet (just set up)
    OK = "ok"  # valid readings are arriving
    GRACE = "grace"  # bad/missing, but still inside the grace period
    DOWN = "down"  # bad/missing for longer than the grace period


class StoveRuntime:
    """Owns one stove's engine and notifies entities when anything changes."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, profile: Profile) -> None:
        self.hass = hass
        self.entry = entry
        self.profile = profile
        self.engine = StoveEngine(profile, self._schedule, self._notify)
        self.grace_seconds = float(
            entry.options.get(CONF_UNAVAILABLE_DELAY, DEFAULT_UNAVAILABLE_DELAY)
        )
        self._source = _Source.UNSEEN
        self._grace_cancel: Callable[[], None] | None = None
        self._last_sample_at: float | None = None
        self._listeners: list[Callable[[], None]] = []
        self._unsubs: list[Callable[[], None]] = []

    # -- derived values ---------------------------------------------------

    @property
    def state(self) -> str | None:
        return self.engine.committed

    @property
    def general_state(self) -> str | None:
        return GENERAL_STATE_MAP.get(self.engine.committed) if self.engine.committed else None

    @property
    def available(self) -> bool:
        """Entities are available while readings arrive, and during the grace period.

        During the grace period (and while the integration is still starting up) the
        last resolved state is shown, but only if there is one to show.
        """
        if self._source is _Source.OK:
            return True
        if self._source is _Source.DOWN:
            return False
        return self.grace_seconds > 0 and self.engine.committed is not None

    # -- lifecycle ----------------------------------------------------------

    @callback
    def async_start(self) -> None:
        source = self.entry.options[CONF_SOURCE]
        # A steady reading (same value and attributes) fires `state_reported`, not
        # `state_changed`. Both are samples for the moving average.
        self._unsubs = [
            async_track_state_change_event(self.hass, [source], self._handle_source_event),
            async_track_state_report_event(self.hass, [source], self._handle_source_report),
        ]
        self._apply(self.hass.states.get(source))

    @callback
    def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []
        self._cancel_grace()
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

    @callback
    def _handle_source_report(self, event: Event[EventStateReportedData]) -> None:
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
            self._source_lost()
            return

        now = time.monotonic()
        if (
            self._source is _Source.GRACE
            and self._last_sample_at is not None
            and now - self._last_sample_at > MOVING_AVERAGE_SECONDS
        ):
            # The gap outlasted the averaging window; don't judge on a single reading.
            self.engine.restart_window()
        self._cancel_grace()
        self._source = _Source.OK
        self._last_sample_at = now
        self.engine.update_power(value, now)
        self._notify()

    def _source_lost(self) -> None:
        if self._source in (_Source.GRACE, _Source.DOWN):
            return  # already waiting out the grace period, or already down
        if self.grace_seconds <= 0:
            self._go_down()
            return
        self._source = _Source.GRACE
        # cancel_on_shutdown: a pending grace timer must not hold up Home Assistant stopping.
        self._grace_cancel = async_call_later(
            self.hass,
            self.grace_seconds,
            HassJob(self._grace_expired, "harman_easytouch grace", cancel_on_shutdown=True),
        )

    @callback
    def _grace_expired(self, _now) -> None:
        self._grace_cancel = None
        self._go_down()

    def _go_down(self) -> None:
        self._source = _Source.DOWN
        self.engine.reset_source()
        self._last_sample_at = None
        self._notify()

    def _cancel_grace(self) -> None:
        if self._grace_cancel is not None:
            self._grace_cancel()
            self._grace_cancel = None


type StoveConfigEntry = ConfigEntry[StoveRuntime]
