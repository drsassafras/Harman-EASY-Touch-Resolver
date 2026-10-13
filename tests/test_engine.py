"""Resolver engine tests: moving average, raw state and delayed commits.

The engine is pure Python, so a fake scheduler and a fake clock stand in for Home Assistant.
"""

import pytest

from custom_components.harman_easytouch_resolver.const import (
    DEFAULT_TIMING,
    MOVING_AVERAGE_SECONDS,
    STARTUP_SYNC_SECONDS,
)
from custom_components.harman_easytouch_resolver.engine import StoveEngine
from custom_components.harman_easytouch_resolver.profile import ALLURE_50, Profile

# Distinct numbers per key so a test can tell exactly which one was used.
PROFILE = Profile.from_dict(
    {
        "name": "Test",
        "thresholds": ALLURE_50.to_dict()["thresholds"],
        "timings": {
            "idle": {},  # configured but empty: every missing key means 0 seconds
            "extinguish": {"seqdown": 7},
            "burn_1": {"sequp": 11, "seqdown": 12, "nonseq": 13},
            "burn_2": {"sequp": 21, "seqdown": 22, "cascadeup": 23, "cascadedown": 24, "nonseq": 25},
            "burn_3": {"sequp": 31, "seqdown": 32, "cascadeup": 33, "cascadedown": 34, "nonseq": 35},
            "burn_4": {"sequp": 41, "seqdown": 42},
        },
    }
)


class Harness:
    """Engine plus a fake clock/scheduler."""

    def __init__(self, profile: Profile = PROFILE) -> None:
        self.t = 0.0
        self.jobs: list[list] = []  # [due, fn, active]
        self.changes = 0
        self.engine = StoveEngine(profile, self._schedule, self._on_change)

    def _on_change(self) -> None:
        self.changes += 1

    def _schedule(self, delay, fn):
        job = [self.t + delay, fn, True]
        self.jobs.append(job)

        def cancel() -> None:
            job[2] = False

        return cancel

    def advance(self, seconds: float) -> None:
        end = self.t + seconds
        while True:
            due = [j for j in self.jobs if j[2] and j[0] <= end]
            if not due:
                break
            job = min(due, key=lambda j: j[0])
            self.t = max(self.t, job[0])
            job[2] = False
            job[1]()
        self.t = end

    def pending(self) -> int:
        return sum(1 for j in self.jobs if j[2])

    def start_at(self, state: str) -> "Harness":
        """Begin with `state` already resolved and the raw state agreeing with it."""
        self.engine.restore(state)
        self.engine._handle_raw(state)
        assert self.engine.committed == state
        assert self.pending() == 0
        return self

    def raw(self, state: str) -> None:
        self.engine._handle_raw(state)


# -- timing selection ------------------------------------------------------------


def _commit_time(h: Harness, limit: float = 200) -> float | None:
    """Seconds until the pending change commits (None if it never does)."""
    before = h.engine.committed
    step = 0.5
    elapsed = 0.0
    while elapsed < limit:
        h.advance(step)
        elapsed += step
        if h.engine.committed != before:
            return elapsed
    return None


@pytest.mark.parametrize(
    ("start", "target", "expected"),
    [
        ("burn_1", "burn_2", 21),  # one step up        -> sequp of the new state
        ("burn_3", "burn_2", 22),  # one step down      -> seqdown of the new state
        ("burn_1", "burn_3", 35),  # two steps up       -> nonseq
        ("burn_3", "burn_1", 13),  # two steps down     -> nonseq
        ("burn_2", "idle", 0),     # idle has no keys   -> 0, so immediate
        ("post_ignite", "extinguish", 7),  # seqdown only
    ],
)
def test_delay_for_each_kind_of_move(start, target, expected):
    h = Harness().start_at(start)
    h.raw(target)
    if expected == 0:
        assert h.engine.committed == target
        assert h.pending() == 0
    else:
        h.advance(expected - 0.5)
        assert h.engine.committed == start
        h.advance(0.5)
        assert h.engine.committed == target


def test_state_without_timings_uses_default():
    h = Harness().start_at("burn_1")
    h.raw("cool_down")  # not configured in PROFILE -> DEFAULT_TIMING
    assert _commit_time(h) == DEFAULT_TIMING["seqdown"]


def test_missing_key_in_a_configured_state_is_zero():
    h = Harness().start_at("burn_4")
    h.raw("burn_5")  # burn_5 not configured -> default 3
    h.advance(3)
    h.raw("burn_6")  # default again
    h.advance(3)
    # burn_4 has sequp/seqdown but no nonseq: jump down two steps from burn_6 -> burn_4
    assert h.engine.committed == "burn_6"
    h.raw("burn_4")
    assert h.engine.committed == "burn_4"  # nonseq missing -> 0 -> immediate


# -- cascade ("unfinished change") ---------------------------------------------------


def test_cascade_up_uses_cascadeup_when_previous_change_was_interrupted():
    h = Harness().start_at("burn_1")
    h.raw("burn_2")  # pending, sequp 21
    h.advance(5)
    h.raw("burn_3")  # old raw (burn_2) never committed -> cascadeup 33
    h.advance(32.5)
    assert h.engine.committed == "burn_1"
    h.advance(0.5)
    assert h.engine.committed == "burn_3"


def test_cascade_down_uses_cascadedown_when_previous_change_was_interrupted():
    h = Harness().start_at("burn_3")
    h.raw("burn_2")
    h.advance(5)
    h.raw("burn_1")  # burn_1 has no cascadedown -> falls back to seqdown 12
    h.advance(11.5)
    assert h.engine.committed == "burn_3"
    h.advance(0.5)
    assert h.engine.committed == "burn_1"


def test_cascade_down_key_is_used_when_configured():
    h = Harness().start_at("burn_4")
    h.raw("burn_3")
    h.advance(1)
    h.raw("burn_2")  # cascadedown 24
    h.advance(23.5)
    assert h.engine.committed == "burn_4"
    h.advance(0.5)
    assert h.engine.committed == "burn_2"


def test_cascade_up_falls_back_to_sequp_when_key_missing():
    h = Harness().start_at("burn_2")
    h.raw("burn_3")  # pending
    h.advance(1)
    h.raw("burn_4")  # interrupted, but burn_4 has no cascadeup -> its sequp (41)
    assert _commit_time(h) == 41


def test_cascade_not_used_when_previous_change_finished():
    h = Harness().start_at("burn_1")
    h.raw("burn_2")
    h.advance(21)
    assert h.engine.committed == "burn_2"
    h.raw("burn_3")  # clean step up -> sequp 31, not cascadeup 33
    h.advance(30.5)
    assert h.engine.committed == "burn_2"
    h.advance(0.5)
    assert h.engine.committed == "burn_3"


# -- pending changes -----------------------------------------------------------------


def test_new_change_cancels_the_pending_one():
    h = Harness().start_at("burn_1")
    h.raw("burn_2")
    h.advance(5)
    h.raw("burn_3")
    h.advance(100)
    # burn_2 never became final.
    assert h.engine.committed == "burn_3"
    assert h.pending() == 0


def test_returning_to_resolved_state_cancels_pending_and_stays_put():
    h = Harness().start_at("burn_2")
    h.raw("burn_3")
    h.advance(10)
    h.raw("burn_2")  # back where we were: schedules a commit to the same state
    h.advance(100)
    assert h.engine.committed == "burn_2"


def test_repeated_raw_state_does_not_reschedule():
    h = Harness().start_at("burn_1")
    h.raw("burn_2")
    jobs = len(h.jobs)
    h.raw("burn_2")
    assert len(h.jobs) == jobs


# -- startup / restore -----------------------------------------------------------------


def test_first_evaluation_commits_immediately_when_nothing_restored():
    h = Harness()
    h.raw("burn_3")
    assert h.engine.committed == "burn_3"
    assert h.pending() == 0


def test_first_evaluation_matching_restored_state_does_nothing():
    h = Harness()
    h.engine.restore("burn_3")
    h.raw("burn_3")
    assert h.pending() == 0


def test_first_evaluation_differing_from_restored_waits_for_startup_sync():
    h = Harness()
    h.engine.restore("burn_3")
    h.raw("burn_1")
    h.advance(STARTUP_SYNC_SECONDS - 0.5)
    assert h.engine.committed == "burn_3"
    h.advance(0.5)
    assert h.engine.committed == "burn_1"


def test_restore_ignores_unknown_state_and_does_not_override():
    h = Harness()
    h.engine.restore("nonsense")
    assert h.engine.committed is None
    h.engine.restore("idle")
    h.engine.restore("burn_6")
    assert h.engine.committed == "idle"


def test_restore_notifies():
    h = Harness()
    h.engine.restore("idle")
    assert h.changes == 1


# -- moving average / update_power ---------------------------------------------------------


def test_no_state_until_a_full_window_of_data():
    h = Harness()
    for t in (0, 5, 10, 15, 19):
        h.t = t
        h.engine.update_power(100, t)
    assert h.engine.moving_average == 100
    assert h.engine.raw_state is None
    assert h.engine.committed is None


def test_state_resolves_after_full_window():
    h = Harness()
    for t in (0, 10, MOVING_AVERAGE_SECONDS):
        h.t = t
        h.engine.update_power(100, t)
    assert h.engine.raw_state == "burn_2"
    assert h.engine.committed == "burn_2"


def test_moving_average_drops_old_samples():
    h = Harness()
    h.engine.update_power(10, 0)
    h.engine.update_power(20, 10)
    h.engine.update_power(30, 25)  # cutoff 5 -> the sample at t=0 is gone
    assert h.engine.moving_average == 25
    h.engine.update_power(50, 35)  # cutoff 15 -> only 25 and 35 remain
    assert h.engine.moving_average == 40


def test_sample_exactly_at_cutoff_is_kept():
    h = Harness()
    h.engine.update_power(10, 0)
    h.engine.update_power(30, 20)
    assert h.engine.moving_average == 20


def test_update_power_notifies():
    h = Harness()
    h.engine.update_power(100, 0)
    assert h.changes >= 1


def test_power_change_flows_through_to_a_delayed_commit():
    h = Harness().start_at("burn_2")
    # Establish a full window at 110 W (burn_3 range), then evaluate.
    h.t = 0
    h.engine.update_power(110, 0)
    h.engine.raw_state = "burn_2"
    h.t = 21
    h.engine.update_power(110, 21)
    assert h.engine.raw_state == "burn_3"
    assert h.engine.committed == "burn_2"
    h.advance(30.5)
    assert h.engine.committed == "burn_2"
    h.advance(0.5)
    assert h.engine.committed == "burn_3"


# -- source loss / shutdown ------------------------------------------------------------------


def test_reset_source_keeps_resolved_state_but_clears_everything_else():
    h = Harness().start_at("burn_2")
    h.engine.update_power(100, 0)
    h.raw("burn_3")
    assert h.pending() == 1
    h.engine.reset_source()
    assert h.pending() == 0
    assert h.engine.committed == "burn_2"
    assert h.engine.raw_state is None
    assert h.engine.moving_average is None
    h.advance(100)
    assert h.engine.committed == "burn_2"


def test_after_source_returns_first_evaluation_is_treated_as_startup():
    h = Harness().start_at("burn_2")
    h.engine.reset_source()
    h.raw("burn_5")
    h.advance(STARTUP_SYNC_SECONDS)
    assert h.engine.committed == "burn_5"


def test_shutdown_cancels_pending():
    h = Harness().start_at("burn_1")
    h.raw("burn_2")
    h.engine.shutdown()
    h.advance(100)
    assert h.engine.committed == "burn_1"


def test_shutdown_without_pending_is_safe():
    Harness().engine.shutdown()


# -- attributes -----------------------------------------------------------------------------------


def test_attributes_empty():
    assert Harness().engine.attributes == {"moving_average": None}


def test_attributes_rounded():
    h = Harness()
    h.engine.update_power(10.04, 0)
    h.engine.update_power(10.09, 1)
    attrs = h.engine.attributes
    assert attrs["moving_average"] == 10.1
    assert "raw_state" not in attrs


# -- tick (ageing the window without a new reading) -----------------------------------------------


def test_tick_does_nothing_without_samples():
    h = Harness()
    h.engine.tick(100)
    assert h.engine.moving_average is None
    assert h.changes == 0


def test_tick_ages_old_samples_out_but_keeps_the_newest():
    h = Harness()
    h.engine.update_power(170, 0)
    h.engine.update_power(170, 10)
    h.engine.update_power(170, 20)
    assert h.engine.raw_state == "ignite"
    h.engine.update_power(25, 21)
    assert h.engine.raw_state == "burn_4"  # 122 W: old readings still dominate
    assert h.engine.moving_average > 100
    h.engine.tick(42)  # everything older than 22 s is gone, the 25 W reading stays
    assert h.engine.moving_average == 25
    assert h.engine.raw_state == "post_ignite"


def test_tick_notifies_only_when_something_changed():
    h = Harness()
    h.engine.update_power(100, 0)
    h.engine.update_power(100, 21)
    before = h.changes
    h.engine.tick(22)  # same average, same raw state
    assert h.changes == before
    h.engine.update_power(20, 23)
    before = h.changes
    h.engine.tick(60)
    assert h.changes == before + 1


def test_tick_before_a_full_window_does_not_judge():
    h = Harness()
    h.engine.update_power(100, 0)
    h.engine.tick(5)
    assert h.engine.raw_state is None
