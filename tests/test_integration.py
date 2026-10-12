"""Setup, entities and behaviour of a running stove."""

from __future__ import annotations

from datetime import timedelta

import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_NAME, STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache,
)
from unittest.mock import patch

from custom_components.harman_easytouch_resolver.const import (
    CONF_PROFILE,
    CONF_SOURCE,
    CONF_UNAVAILABLE_DELAY,
    DOMAIN,
    GENERAL_STATE_OPTIONS,
    ORDER,
)
from custom_components.harman_easytouch_resolver.profile import ALLURE_50

SOURCE = "sensor.stove_power"
OTHER_SOURCE = "sensor.other_power"
STATE = "sensor.pellet_stove_state"
GENERAL = "sensor.pellet_stove_general_state"
ACTIVE = "binary_sensor.pellet_stove_active"
POWER_ATTRS = {"device_class": "power", "unit_of_measurement": "W"}


class Clock:
    """Stands in for the `time` module inside runtime.py only."""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now


@pytest.fixture
def clock():
    clock = Clock()
    with patch("custom_components.harman_easytouch_resolver.runtime.time", clock):
        yield clock


def _entry(
    profile: str = "Allure 50", source: str = SOURCE, delay: int | None = None
) -> MockConfigEntry:
    """`delay` is the unavailable grace period; None leaves it out (the 60 s default)."""
    options = {CONF_SOURCE: source, CONF_PROFILE: profile}
    if delay is not None:
        options[CONF_UNAVAILABLE_DELAY] = delay
    return MockConfigEntry(
        domain=DOMAIN,
        title="Pellet stove",
        data={CONF_NAME: "Pellet stove"},
        options=options,
        unique_id="pellet_stove",
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _feed(hass: HomeAssistant, clock: Clock, value, at: float, entity: str = SOURCE) -> None:
    clock.now = at
    hass.states.async_set(entity, str(value), POWER_ATTRS)
    await hass.async_block_till_done()


async def _settle(hass: HomeAssistant, clock: Clock, value, start: float = 0.0) -> None:
    """Feed a steady power level for a full 20 s window so a state resolves."""
    await _feed(hass, clock, value, start)
    await _feed(hass, clock, value, start + 21)


async def _after(hass: HomeAssistant, seconds: float) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done()


# -- setup -----------------------------------------------------------------------------------


async def test_setup_and_unload(hass: HomeAssistant, clock) -> None:
    entry = _entry()
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert hass.states.get(STATE).state == STATE_UNAVAILABLE

    # Nothing should still be listening to the source after unload.
    await _feed(hass, clock, 100, 5)


async def test_entities_unavailable_until_source_reports(hass: HomeAssistant, clock) -> None:
    await _setup(hass, _entry())
    for entity in (STATE, GENERAL, ACTIVE):
        assert hass.states.get(entity).state == STATE_UNAVAILABLE


async def test_device_and_unique_ids(hass: HomeAssistant, clock) -> None:
    entry = _entry()
    await _setup(hass, entry)
    registry = er.async_get(hass)
    assert registry.async_get(STATE).unique_id == f"{entry.entry_id}_state"
    assert registry.async_get(GENERAL).unique_id == f"{entry.entry_id}_general_state"
    assert registry.async_get(ACTIVE).unique_id == f"{entry.entry_id}_active"

    device = dr.async_get(hass).async_get(registry.async_get(STATE).device_id)
    assert device is not None
    assert (DOMAIN, entry.entry_id) in device.identifiers
    assert device.name == "Pellet stove"
    assert device.manufacturer == "Harman"
    assert device.model == "Allure 50"  # the stove profile
    assert registry.async_get(STATE).device_id == device.id


async def test_device_model_follows_the_profile(hass: HomeAssistant, hass_storage, clock) -> None:
    custom = ALLURE_50.to_dict()
    custom["name"] = "Allure 30"
    hass_storage[f"{DOMAIN}.profiles"] = {
        "version": 1,
        "minor_version": 1,
        "key": f"{DOMAIN}.profiles",
        "data": {"profiles": {"Allure 30": custom}},
    }
    entry = _entry(profile="Allure 30")
    await _setup(hass, entry)
    device = dr.async_get(hass).async_get(er.async_get(hass).async_get(STATE).device_id)
    assert device.model == "Allure 30"


async def test_enum_options(hass: HomeAssistant, clock) -> None:
    await _setup(hass, _entry())
    await _settle(hass, clock, 100)
    assert hass.states.get(STATE).attributes["options"] == ORDER
    assert hass.states.get(GENERAL).attributes["options"] == GENERAL_STATE_OPTIONS


# -- state resolution --------------------------------------------------------------------------


async def test_unknown_until_a_full_window_of_data(hass: HomeAssistant, clock) -> None:
    await _setup(hass, _entry())
    await _feed(hass, clock, 100, 0)
    assert hass.states.get(STATE).state == STATE_UNKNOWN
    assert hass.states.get(STATE).attributes["moving_average"] == 100.0
    assert hass.states.get(STATE).attributes["raw_state"] is None


async def test_burning_state(hass: HomeAssistant, clock) -> None:
    await _setup(hass, _entry())
    await _settle(hass, clock, 100)
    assert hass.states.get(STATE).state == "burn_2"
    assert hass.states.get(STATE).attributes["raw_state"] == "burn_2"
    assert hass.states.get(STATE).attributes["moving_average"] == 100.0
    assert hass.states.get(GENERAL).state == "Burning"
    assert hass.states.get(GENERAL).attributes["icon"] == "mdi:fire"
    assert hass.states.get(ACTIVE).state == STATE_ON


async def test_idle_state(hass: HomeAssistant, clock) -> None:
    await _setup(hass, _entry())
    await _settle(hass, clock, 3)
    assert hass.states.get(STATE).state == "idle"
    assert hass.states.get(GENERAL).state == "Idle"
    assert hass.states.get(GENERAL).attributes["icon"] == "mdi:fireplace-off"
    assert hass.states.get(ACTIVE).state == STATE_OFF


async def test_ignite_is_lighting_and_active(hass: HomeAssistant, clock) -> None:
    await _setup(hass, _entry())
    await _settle(hass, clock, 100)
    await _feed(hass, clock, 170, 42)  # jump to ignite: no wait configured
    assert hass.states.get(STATE).state == "ignite"
    assert hass.states.get(GENERAL).state == "Lighting"
    assert hass.states.get(ACTIVE).state == STATE_ON


async def test_fault_is_not_active(hass: HomeAssistant, clock) -> None:
    await _setup(hass, _entry())
    await _settle(hass, clock, 0.5)
    assert hass.states.get(STATE).state == "sensor_fault"
    assert hass.states.get(GENERAL).state == "Faulted"
    assert hass.states.get(ACTIVE).state == STATE_OFF


async def test_change_commits_only_after_the_delay(hass: HomeAssistant, clock) -> None:
    await _setup(hass, _entry())
    await _settle(hass, clock, 100)  # burn_2
    await _feed(hass, clock, 110, 42)  # burn_3: sequp is 75 s
    assert hass.states.get(STATE).attributes["raw_state"] == "burn_3"
    assert hass.states.get(STATE).state == "burn_2"
    await _after(hass, 74)
    assert hass.states.get(STATE).state == "burn_2"
    await _after(hass, 76)
    assert hass.states.get(STATE).state == "burn_3"


# -- unavailable / invalid source ----------------------------------------------------------------


async def test_source_unavailable_keeps_resolved_state_but_marks_entities_unavailable(
    hass: HomeAssistant, clock
) -> None:
    await _setup(hass, _entry(delay=0))
    await _settle(hass, clock, 100)
    clock.now = 50
    hass.states.async_set(SOURCE, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    for entity in (STATE, GENERAL, ACTIVE):
        assert hass.states.get(entity).state == STATE_UNAVAILABLE

    await _feed(hass, clock, 100, 100)
    assert hass.states.get(STATE).state == "burn_2"  # remembered
    assert hass.states.get(STATE).attributes["raw_state"] is None  # not re-evaluated yet
    await _feed(hass, clock, 100, 121)
    assert hass.states.get(STATE).attributes["raw_state"] == "burn_2"


# -- unavailable grace period -----------------------------------------------------------------


async def _drop_source(hass: HomeAssistant, clock: Clock, at: float) -> None:
    clock.now = at
    hass.states.async_set(SOURCE, STATE_UNAVAILABLE)
    await hass.async_block_till_done()


async def test_short_dropout_keeps_the_last_state(hass: HomeAssistant, clock) -> None:
    await _setup(hass, _entry())
    await _settle(hass, clock, 100)
    await _drop_source(hass, clock, 30)
    for entity in (STATE, GENERAL, ACTIVE):
        assert hass.states.get(entity).state != STATE_UNAVAILABLE
    assert hass.states.get(STATE).state == "burn_2"
    assert hass.states.get(GENERAL).state == "Burning"
    assert hass.states.get(ACTIVE).state == STATE_ON

    await _after(hass, 59)
    assert hass.states.get(STATE).state == "burn_2"  # still inside the grace period
    await _feed(hass, clock, 100, 40)  # source is back
    await _after(hass, 120)  # the old grace timer must not fire
    assert hass.states.get(STATE).state == "burn_2"


async def test_dropout_longer_than_the_grace_period_goes_unavailable(
    hass: HomeAssistant, clock
) -> None:
    await _setup(hass, _entry())
    await _settle(hass, clock, 100)
    await _drop_source(hass, clock, 30)
    await _after(hass, 61)
    for entity in (STATE, GENERAL, ACTIVE):
        assert hass.states.get(entity).state == STATE_UNAVAILABLE


async def test_another_bad_reading_mid_grace_changes_nothing(hass: HomeAssistant, clock) -> None:
    await _setup(hass, _entry())
    await _settle(hass, clock, 100)
    await _drop_source(hass, clock, 30)
    hass.states.async_set(SOURCE, STATE_UNKNOWN)  # a second bad value while waiting
    await hass.async_block_till_done()
    assert hass.states.get(STATE).state == "burn_2"  # still showing the last state
    await _after(hass, 61)
    assert hass.states.get(STATE).state == STATE_UNAVAILABLE
    hass.states.async_set(SOURCE, "abc")  # and bad readings once down stay unavailable
    await hass.async_block_till_done()
    assert hass.states.get(STATE).state == STATE_UNAVAILABLE


async def test_custom_grace_period_is_used(hass: HomeAssistant, clock) -> None:
    await _setup(hass, _entry(delay=300))
    await _settle(hass, clock, 100)
    await _drop_source(hass, clock, 30)
    await _after(hass, 200)
    assert hass.states.get(STATE).state == "burn_2"
    await _after(hass, 301)
    assert hass.states.get(STATE).state == STATE_UNAVAILABLE


async def test_long_gap_inside_grace_needs_a_fresh_window(hass: HomeAssistant, clock) -> None:
    await _setup(hass, _entry())
    await _settle(hass, clock, 100)  # burn_2
    await _drop_source(hass, clock, 30)
    await _feed(hass, clock, 170, 55)  # back after 25 s: older than the 20 s window
    assert hass.states.get(STATE).state == "burn_2"
    assert hass.states.get(STATE).attributes["moving_average"] == 170.0
    assert hass.states.get(STATE).attributes["raw_state"] == "burn_2"  # not judged on 1 sample
    await _feed(hass, clock, 170, 76)  # full window again
    assert hass.states.get(STATE).attributes["raw_state"] == "ignite"


# -- restart: restored state is shown while the power sensor comes online ----------------------


async def test_restart_shows_restored_state_until_the_source_appears(
    hass: HomeAssistant, clock
) -> None:
    mock_restore_cache(hass, [State(STATE, "burn_4")])
    await _setup(hass, _entry())  # the power sensor does not exist yet
    for entity in (STATE, GENERAL, ACTIVE):
        assert hass.states.get(entity).state != STATE_UNAVAILABLE
    assert hass.states.get(STATE).state == "burn_4"

    await _after(hass, 30)
    assert hass.states.get(STATE).state == "burn_4"
    await _feed(hass, clock, 100, 35)  # the power sensor finally comes online
    assert hass.states.get(STATE).state == "burn_4"  # still the restored state
    await _after(hass, 300)  # the startup grace timer must not fire now
    assert hass.states.get(STATE).state != STATE_UNAVAILABLE


async def test_restart_with_a_source_that_never_appears_goes_unavailable(
    hass: HomeAssistant, clock
) -> None:
    mock_restore_cache(hass, [State(STATE, "burn_4")])
    await _setup(hass, _entry())
    await _after(hass, 61)
    for entity in (STATE, GENERAL, ACTIVE):
        assert hass.states.get(entity).state == STATE_UNAVAILABLE


async def test_restart_with_grace_off_is_unavailable_immediately(
    hass: HomeAssistant, clock
) -> None:
    mock_restore_cache(hass, [State(STATE, "burn_4")])
    await _setup(hass, _entry(delay=0))
    assert hass.states.get(STATE).state == STATE_UNAVAILABLE


@pytest.mark.parametrize("bad", ["abc", "nan", "inf", "-inf", STATE_UNKNOWN])
async def test_non_numeric_source_is_unavailable(hass: HomeAssistant, clock, bad) -> None:
    await _setup(hass, _entry(delay=0))
    await _settle(hass, clock, 100)
    clock.now = 50
    hass.states.async_set(SOURCE, bad, POWER_ATTRS)
    await hass.async_block_till_done()
    assert hass.states.get(STATE).state == STATE_UNAVAILABLE


async def test_source_present_at_setup_is_used_immediately(hass: HomeAssistant, clock) -> None:
    hass.states.async_set(SOURCE, "100", POWER_ATTRS)
    await _setup(hass, _entry())
    assert hass.states.get(STATE).state == STATE_UNKNOWN  # available, window not full
    assert hass.states.get(STATE).attributes["moving_average"] == 100.0


# -- restore ---------------------------------------------------------------------------------------


async def test_state_is_restored_then_synced(hass: HomeAssistant, clock) -> None:
    mock_restore_cache(hass, [State(STATE, "burn_4")])
    hass.states.async_set(SOURCE, "100", POWER_ATTRS)
    await _setup(hass, _entry())
    assert hass.states.get(STATE).state == "burn_4"

    await _feed(hass, clock, 100, 21)  # first evaluation disagrees with the restored state
    assert hass.states.get(STATE).state == "burn_4"
    await _after(hass, 31)  # startup sync is 30 s
    assert hass.states.get(STATE).state == "burn_2"


async def test_garbage_restored_state_is_ignored(hass: HomeAssistant, clock) -> None:
    mock_restore_cache(hass, [State(STATE, "not_a_state")])
    await _setup(hass, _entry())
    await _settle(hass, clock, 100)
    assert hass.states.get(STATE).state == "burn_2"


# -- profiles --------------------------------------------------------------------------------------------


async def test_unknown_profile_falls_back_to_allure_50(hass: HomeAssistant, clock, caplog) -> None:
    await _setup(hass, _entry(profile="Deleted profile"))
    assert "falling back" in caplog.text
    await _settle(hass, clock, 100)
    assert hass.states.get(STATE).state == "burn_2"


async def test_saved_custom_profile_is_used(hass: HomeAssistant, hass_storage, clock) -> None:
    custom = ALLURE_50.to_dict()
    custom["name"] = "Double"
    custom["thresholds"] = {k: v * 2 for k, v in custom["thresholds"].items()}
    hass_storage[f"{DOMAIN}.profiles"] = {
        "version": 1,
        "minor_version": 1,
        "key": f"{DOMAIN}.profiles",
        "data": {"profiles": {"Double": custom}},
    }
    await _setup(hass, _entry(profile="Double"))
    await _settle(hass, clock, 100)  # 100 W is only "fault_extinguish" on this profile
    assert hass.states.get(STATE).state == "fault_extinguish"
    assert hass.states.get(GENERAL).state == "Faulted"


async def test_changing_options_reloads_with_the_new_sensor(hass: HomeAssistant, clock) -> None:
    entry = _entry()
    await _setup(hass, entry)
    await _settle(hass, clock, 100)
    assert hass.states.get(STATE).state == "burn_2"

    hass.config_entries.async_update_entry(
        entry, options={CONF_SOURCE: OTHER_SOURCE, CONF_PROFILE: "Allure 50"}
    )
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    # The new sensor drives the stove; the resolved state was restored across the reload.
    await _feed(hass, clock, 3, 200, OTHER_SOURCE)
    await _feed(hass, clock, 3, 221, OTHER_SOURCE)
    await _after(hass, 31)  # resolved state was restored; startup sync is 30 s
    assert hass.states.get(STATE).state == "idle"
