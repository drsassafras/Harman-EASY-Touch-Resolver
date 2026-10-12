"""Profile parsing, validation and state mapping (no Home Assistant needed)."""

import json

import pytest

from custom_components.harman_easytouch_resolver.const import THRESHOLD_ORDER
from custom_components.harman_easytouch_resolver.profile import (
    ALLURE_50,
    BUILTIN_PROFILES,
    Profile,
    ProfileError,
    parse_profile_json,
    template_json,
)


def _valid() -> dict:
    return json.loads(json.dumps(ALLURE_50.to_dict()))


# -- raw_state -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("watts", "expected"),
    [
        (500, "ignite"),
        (155.1, "ignite"),
        (155, "burn_6"),  # thresholds are "power > value"
        (141, "burn_6"),
        (127.5, "burn_5"),
        (116, "burn_4"),
        (102, "burn_3"),
        (87, "burn_2"),
        (72, "burn_1"),
        (61, "cool_down"),
        (60, "fault_extinguish"),
        (33, "fault_extinguish"),
        (20, "post_ignite"),
        (6, "extinguish"),
        (1.5, "idle"),
        (1, "sensor_fault"),  # at or below idle
        (0, "sensor_fault"),
        (-5, "sensor_fault"),
    ],
)
def test_allure_raw_state(watts, expected):
    assert ALLURE_50.raw_state(watts) == expected


def test_raw_state_covers_every_threshold():
    seen = {ALLURE_50.raw_state(ALLURE_50.thresholds[s] + 0.01) for s in THRESHOLD_ORDER}
    assert seen == set(THRESHOLD_ORDER)


# -- from_dict / validation ----------------------------------------------------


def test_round_trip():
    clone = Profile.from_dict(ALLURE_50.to_dict())
    assert clone == ALLURE_50


def test_name_is_stripped():
    data = _valid()
    data["name"] = "  Spaced  "
    assert Profile.from_dict(data).name == "Spaced"


def test_timings_are_optional():
    data = _valid()
    del data["timings"]
    assert Profile.from_dict(data).timings == {}


def test_all_timing_keys_are_optional():
    data = _valid()
    data["timings"] = {"burn_3": {}}
    assert Profile.from_dict(data).timings == {"burn_3": {}}


def test_integer_values_become_floats():
    data = _valid()
    assert all(isinstance(v, float) for v in Profile.from_dict(data).thresholds.values())


def _mutate(fn):
    data = _valid()
    fn(data)
    return data


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "JSON object"),
        ("text", "JSON object"),
        (_mutate(lambda d: d.pop("name")), "'name'"),
        (_mutate(lambda d: d.update(name="   ")), "'name'"),
        (_mutate(lambda d: d.update(name=5)), "'name'"),
        (_mutate(lambda d: d.pop("thresholds")), "'thresholds' must be an object"),
        (_mutate(lambda d: d.update(thresholds=[])), "'thresholds' must be an object"),
        (_mutate(lambda d: d["thresholds"].pop("burn_3")), "missing threshold for 'burn_3'"),
        (_mutate(lambda d: d["thresholds"].update(bogus=1)), "unknown threshold"),
        (_mutate(lambda d: d["thresholds"].update(burn_3="x")), "must be a number"),
        (_mutate(lambda d: d["thresholds"].update(burn_3=True)), "must be a number"),
        (_mutate(lambda d: d["thresholds"].update(burn_3=float("inf"))), "finite"),
        (_mutate(lambda d: d["thresholds"].update(burn_3=float("nan"))), "finite"),
        (_mutate(lambda d: d["thresholds"].update(burn_5=140)), "strictly decrease"),
        (_mutate(lambda d: d["thresholds"].update(idle=5)), "strictly decrease"),
        (_mutate(lambda d: d.update(timings=[])), "'timings' must be an object"),
        (_mutate(lambda d: d["timings"].update(nope={})), "unknown state in timings"),
        (_mutate(lambda d: d["timings"].update(burn_1=[])), "must be an object"),
        (_mutate(lambda d: d["timings"]["burn_1"].update(wait=1)), "unknown timing"),
        (_mutate(lambda d: d["timings"]["burn_1"].update(sequp="1")), "must be a number"),
        (_mutate(lambda d: d["timings"]["burn_1"].update(sequp=-1)), "0 or more"),
    ],
)
def test_invalid_profiles(payload, message):
    with pytest.raises(ProfileError) as err:
        Profile.from_dict(payload)
    assert message in str(err.value)


# -- JSON helpers ----------------------------------------------------------------


def test_parse_profile_json_ok():
    profile = parse_profile_json(json.dumps(_valid()))
    assert profile == ALLURE_50


def test_parse_profile_json_syntax_error_reports_line():
    with pytest.raises(ProfileError) as err:
        parse_profile_json('{\n  "name": \n}')
    assert "not valid JSON" in str(err.value)
    assert "line 3" in str(err.value)


def test_template_json_renames_builtin_so_it_can_be_saved():
    text = template_json(ALLURE_50)
    data = json.loads(text)
    assert data["name"] == "Allure 50 (custom)"
    assert data["name"] not in BUILTIN_PROFILES
    assert parse_profile_json(text).thresholds == ALLURE_50.thresholds


def test_template_json_keeps_custom_name():
    custom = Profile.from_dict({**_valid(), "name": "Mine"})
    assert json.loads(template_json(custom))["name"] == "Mine"


def test_builtin_registry():
    assert BUILTIN_PROFILES == {"Allure 50": ALLURE_50}


def test_profile_errors_carry_a_code_and_placeholders():
    data = _valid()
    data["thresholds"].pop("burn_3")
    with pytest.raises(ProfileError) as err:
        Profile.from_dict(data)
    assert err.value.code == "profile_threshold_missing"
    assert err.value.placeholders == {"state": "burn_3"}

    data = _valid()
    data["timings"]["burn_1"]["sequp"] = float("inf")
    with pytest.raises(ProfileError) as err:
        Profile.from_dict(data)
    assert err.value.code == "profile_timing_not_finite"
    assert err.value.placeholders == {"state": "burn_1", "key": "sequp"}

    with pytest.raises(ProfileError) as err:
        parse_profile_json("{ nope")
    assert err.value.code == "profile_json_invalid"
    assert err.value.placeholders["line"] == "1"
    assert "column" in err.value.placeholders
