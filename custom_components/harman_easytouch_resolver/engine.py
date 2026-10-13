"""State resolver engine. Pure Python so it can be tested without Home Assistant."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Any

from .const import (
    DEFAULT_TIMING,
    MOVING_AVERAGE_SECONDS,
    ORDER,
    STARTUP_SYNC_SECONDS,
)
from .profile import Profile

# schedule(delay_seconds, callback) -> cancel function
Scheduler = Callable[[float, Callable[[], None]], Callable[[], None]]


class StoveEngine:
    """20 s moving average -> raw state -> delayed, order-aware resolved state."""

    def __init__(
        self, profile: Profile, schedule: Scheduler, on_change: Callable[[], None]
    ) -> None:
        self.profile = profile
        self._schedule = schedule
        self._on_change = on_change

        self.committed: str | None = None  # the resolved state (main sensor value)
        self.raw_state: str | None = None
        self.moving_average: float | None = None

        self._samples: deque[tuple[float, float]] = deque()
        self._first_sample_at: float | None = None
        self._pending_cancel: Callable[[], None] | None = None

    # -- inputs ---------------------------------------------------------

    def restore(self, state: str) -> None:
        """Seed the resolved state from the last known value (after a restart)."""
        if self.committed is None and state in ORDER:
            self.committed = state
            self._on_change()

    def update_power(self, value: float, now: float) -> None:
        """Feed a new source reading (watts). `now` is a monotonic time in seconds."""
        if self._first_sample_at is None:
            self._first_sample_at = now
        self._samples.append((now, value))
        self._evaluate(now)
        self._on_change()

    def tick(self, now: float) -> None:
        """Let old readings age out of the window even when no new reading arrives.

        Many power sensors only report when the value changes. Without this, the readings
        from before a big change (for example the igniter switching off) would stay in the
        average until the next report, and the state would lag far behind the stove.
        The newest reading is always kept, so a steady value keeps counting.
        """
        if not self._samples:
            return
        before = self.moving_average
        raw_before = self.raw_state
        self._evaluate(now)
        if self.moving_average != before or self.raw_state != raw_before:
            self._on_change()

    def _evaluate(self, now: float) -> None:
        cutoff = now - MOVING_AVERAGE_SECONDS
        while len(self._samples) > 1 and self._samples[0][0] < cutoff:
            self._samples.popleft()
        self.moving_average = sum(v for _, v in self._samples) / len(self._samples)

        # Until a full window of data exists the average is not trustworthy.
        if (
            self._first_sample_at is not None
            and now - self._first_sample_at >= MOVING_AVERAGE_SECONDS
        ):
            self._handle_raw(self.profile.raw_state(self.moving_average))

    def reset_source(self) -> None:
        """Source went unavailable: drop everything transient, keep resolved state."""
        self._cancel_pending()
        self._samples.clear()
        self._first_sample_at = None
        self.moving_average = None
        self.raw_state = None

    def restart_window(self) -> None:
        """Readings stopped for longer than the window: require a fresh full window.

        Keeps the resolved and raw state, so a short outage does not look like a restart.
        """
        self._samples.clear()
        self._first_sample_at = None
        self.moving_average = None

    def shutdown(self) -> None:
        self._cancel_pending()

    # -- resolver (port of the 'Pellet Stove State Resolver' automation) --

    def _handle_raw(self, new_raw: str) -> None:
        old_raw = self.raw_state
        if old_raw is None:
            # First evaluation since startup / source recovery.
            self.raw_state = new_raw
            if self.committed is None:
                self._commit(new_raw)
            elif self.committed != new_raw:
                self._schedule_commit(new_raw, STARTUP_SYNC_SECONDS)
            return
        if new_raw == old_raw:
            return
        self.raw_state = new_raw
        # mode: restart -> a new change cancels whatever was still pending.
        self._cancel_pending()
        self._schedule_commit(new_raw, self._delay(old_raw, new_raw))

    def _delay(self, old: str, new: str) -> float:
        cfg = self.profile.timings.get(new, DEFAULT_TIMING)
        delta = ORDER.index(new) - ORDER.index(old)
        # "Reset": the previous raw state never made it to the resolved state,
        # i.e. a pending change was interrupted.
        is_reset = old != self.committed
        if delta == 1:
            key = "cascadeup" if is_reset and "cascadeup" in cfg else "sequp"
        elif delta == -1:
            key = "cascadedown" if is_reset and "cascadedown" in cfg else "seqdown"
        else:
            key = "nonseq"
        return float(cfg.get(key, 0))

    def _schedule_commit(self, state: str, delay: float) -> None:
        if delay <= 0:
            self._commit(state)
            return
        self._pending_cancel = self._schedule(delay, lambda: self._commit(state))

    def _commit(self, state: str) -> None:
        self._pending_cancel = None
        if state != self.committed:
            self.committed = state
            self._on_change()

    def _cancel_pending(self) -> None:
        if self._pending_cancel is not None:
            self._pending_cancel()
            self._pending_cancel = None

    # -- outputs --------------------------------------------------------

    @property
    def attributes(self) -> dict[str, Any]:
        return {
            "moving_average": (
                round(self.moving_average, 1) if self.moving_average is not None else None
            ),
        }
