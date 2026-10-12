"""Config flow, options flow and profile store tests."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import slugify
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.harman_easytouch_resolver.const import (
    CONF_EDIT_PROFILE,
    CONF_PROFILE,
    CONF_PROFILE_JSON,
    CONF_SOURCE,
    CONF_UNAVAILABLE_DELAY,
    DOMAIN,
    IMPORT_NEW,
)
from custom_components.harman_easytouch_resolver.profile import ALLURE_50, Profile
from custom_components.harman_easytouch_resolver.profiles import (
    async_get_profile_store,
    async_save_profile,
)

SOURCE = "sensor.stove_power"
OTHER_SOURCE = "sensor.other_power"
STORE_KEY = f"{DOMAIN}.profiles"


def _profile_json(name: str = "Mine", ignite: float = 155) -> str:
    data = ALLURE_50.to_dict()
    data["name"] = name
    data["thresholds"]["ignite"] = ignite
    return json.dumps(data)


def _suggested(result, key: str):
    """The pre-filled value of a form field."""
    for marker in result["data_schema"].schema:
        if marker == key:
            return (marker.description or {}).get("suggested_value")
    raise AssertionError(f"{key} not in form")


def _field_names(result) -> list[str]:
    return [str(marker) for marker in result["data_schema"].schema]


def _entry(name: str = "Pellet stove", source: str = SOURCE, profile: str = "Allure 50"):
    return MockConfigEntry(
        domain=DOMAIN,
        title=name,
        data={CONF_NAME: name},
        options={CONF_SOURCE: source, CONF_PROFILE: profile},
        unique_id=slugify(name),
    )


@pytest.fixture
def mock_setup_entry():
    with patch(
        "custom_components.harman_easytouch_resolver.async_setup_entry", return_value=True
    ) as mock:
        yield mock


# -- adding a stove -------------------------------------------------------------------


async def _start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_user_form(hass: HomeAssistant) -> None:
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert _field_names(result) == [CONF_NAME, CONF_SOURCE, CONF_PROFILE]


async def test_user_flow_with_builtin_profile(hass: HomeAssistant, mock_setup_entry) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "  Pellet stove ", CONF_SOURCE: SOURCE, CONF_PROFILE: "Allure 50"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Pellet stove"
    assert result["data"] == {CONF_NAME: "Pellet stove"}
    assert result["options"] == {CONF_SOURCE: SOURCE, CONF_PROFILE: "Allure 50"}
    assert result["result"].unique_id == "pellet_stove"
    mock_setup_entry.assert_called_once()


async def test_user_flow_with_new_profile(hass: HomeAssistant, mock_setup_entry) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Pellet stove", CONF_SOURCE: SOURCE, CONF_PROFILE: IMPORT_NEW},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "import_profile"
    template = json.loads(_suggested(result, CONF_PROFILE_JSON))
    assert template["name"] == "Allure 50 (custom)"  # built-in name already changed

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PROFILE_JSON: _profile_json("Mine")}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == {CONF_SOURCE: SOURCE, CONF_PROFILE: "Mine"}
    store = await async_get_profile_store(hass)
    assert store.get("Mine") is not None
    assert "Mine" in store.names


async def _to_import_step(hass: HomeAssistant):
    result = await _start(hass)
    return await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Pellet stove", CONF_SOURCE: SOURCE, CONF_PROFILE: IMPORT_NEW},
    )


async def test_import_rejects_bad_json(hass: HomeAssistant, mock_setup_entry) -> None:
    result = await _to_import_step(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PROFILE_JSON: "{ nope"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "profile_json_invalid"}
    assert result["description_placeholders"]["line"] == "1"
    assert _suggested(result, CONF_PROFILE_JSON) == "{ nope"  # the user's text is kept
    mock_setup_entry.assert_not_called()


async def test_import_rejects_invalid_profile(hass: HomeAssistant, mock_setup_entry) -> None:
    result = await _to_import_step(hass)
    bad = json.loads(_profile_json())
    bad["thresholds"]["burn_6"] = 500  # no longer decreasing
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PROFILE_JSON: json.dumps(bad)}
    )
    assert result["errors"] == {"base": "profile_thresholds_order"}


async def test_import_rejects_builtin_name(hass: HomeAssistant, mock_setup_entry) -> None:
    result = await _to_import_step(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PROFILE_JSON: _profile_json("Allure 50")}
    )
    assert result["errors"] == {"base": "reserved_name"}


async def test_import_rejects_reserved_dropdown_value(hass: HomeAssistant, mock_setup_entry) -> None:
    result = await _to_import_step(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PROFILE_JSON: _profile_json(IMPORT_NEW)}
    )
    assert result["errors"] == {"base": "reserved_name"}


async def test_import_can_be_corrected_and_resubmitted(hass: HomeAssistant, mock_setup_entry) -> None:
    result = await _to_import_step(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PROFILE_JSON: "{"}
    )
    assert result["errors"]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PROFILE_JSON: _profile_json("Fixed")}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_duplicate_name_aborts(hass: HomeAssistant, mock_setup_entry) -> None:
    _entry("Pellet stove").add_to_hass(hass)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "pellet STOVE", CONF_SOURCE: OTHER_SOURCE, CONF_PROFILE: "Allure 50"},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_same_power_sensor_cannot_be_used_twice(hass: HomeAssistant, mock_setup_entry) -> None:
    _entry("Pellet stove", SOURCE).add_to_hass(hass)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Second stove", CONF_SOURCE: SOURCE, CONF_PROFILE: "Allure 50"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "source_in_use"}
    assert _suggested(result, CONF_NAME) == "Second stove"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Second stove", CONF_SOURCE: OTHER_SOURCE, CONF_PROFILE: "Allure 50"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_saved_profiles_are_offered_for_new_stoves(hass: HomeAssistant, mock_setup_entry) -> None:
    await async_save_profile(hass, Profile.from_dict(json.loads(_profile_json("Mine"))))
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Pellet stove", CONF_SOURCE: SOURCE, CONF_PROFILE: "Mine"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_PROFILE] == "Mine"


# -- options flow -----------------------------------------------------------------------


async def _options(hass: HomeAssistant, entry):
    return await hass.config_entries.options.async_init(entry.entry_id)


async def test_options_form_is_the_main_window(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    result = await _options(hass, entry)
    assert result["type"] is FlowResultType.FORM  # a form, not a menu
    assert result["step_id"] == "init"
    assert _field_names(result) == [
        CONF_SOURCE,
        CONF_PROFILE,
        CONF_UNAVAILABLE_DELAY,
        CONF_EDIT_PROFILE,
    ]
    assert _suggested(result, CONF_SOURCE) == SOURCE
    assert _suggested(result, CONF_UNAVAILABLE_DELAY) == 60  # default for older entries
    assert _suggested(result, CONF_PROFILE) == "Allure 50"


async def test_options_change_sensor_and_profile(hass: HomeAssistant) -> None:
    await async_save_profile(hass, Profile.from_dict(json.loads(_profile_json("Mine"))))
    entry = _entry()
    entry.add_to_hass(hass)
    result = await _options(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SOURCE: OTHER_SOURCE, CONF_PROFILE: "Mine", CONF_EDIT_PROFILE: False},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        CONF_SOURCE: OTHER_SOURCE,
        CONF_PROFILE: "Mine",
        CONF_UNAVAILABLE_DELAY: 60,
    }
    assert CONF_EDIT_PROFILE not in entry.options  # a UI toggle, never stored


async def test_options_unavailable_delay_is_saved(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    result = await _options(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_SOURCE: SOURCE,
            CONF_PROFILE: "Allure 50",
            CONF_UNAVAILABLE_DELAY: 180,
            CONF_EDIT_PROFILE: False,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_UNAVAILABLE_DELAY] == 180


async def test_options_unavailable_delay_survives_profile_edit(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    result = await _options(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_SOURCE: SOURCE,
            CONF_PROFILE: "Allure 50",
            CONF_UNAVAILABLE_DELAY: 0,
            CONF_EDIT_PROFILE: True,
        },
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_PROFILE_JSON: _profile_json("Edited")}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_UNAVAILABLE_DELAY] == 0
    assert entry.options[CONF_PROFILE] == "Edited"


async def test_options_edit_builtin_profile_saves_a_copy(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    result = await _options(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SOURCE: OTHER_SOURCE, CONF_PROFILE: "Allure 50", CONF_EDIT_PROFILE: True},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "import_profile"
    assert json.loads(_suggested(result, CONF_PROFILE_JSON))["name"] == "Allure 50 (custom)"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_PROFILE_JSON: _profile_json("My Allure", ignite=160)}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    # The sensor chosen on the first page is kept, and the new profile is applied.
    assert entry.options == {
        CONF_SOURCE: OTHER_SOURCE,
        CONF_PROFILE: "My Allure",
        CONF_UNAVAILABLE_DELAY: 60,
    }
    store = await async_get_profile_store(hass)
    assert store.get("My Allure").thresholds["ignite"] == 160


async def test_options_edit_starts_from_the_selected_profile(hass: HomeAssistant) -> None:
    await async_save_profile(hass, Profile.from_dict(json.loads(_profile_json("Mine", 170))))
    entry = _entry()  # currently on the built-in profile
    entry.add_to_hass(hass)
    result = await _options(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SOURCE: SOURCE, CONF_PROFILE: "Mine", CONF_EDIT_PROFILE: True},
    )
    template = json.loads(_suggested(result, CONF_PROFILE_JSON))
    assert template["name"] == "Mine"  # custom names are not renamed
    assert template["thresholds"]["ignite"] == 170


async def test_options_edit_errors_and_retry(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    result = await _options(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SOURCE: SOURCE, CONF_PROFILE: "Allure 50", CONF_EDIT_PROFILE: True},
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_PROFILE_JSON: "[]"}
    )
    assert result["errors"] == {"base": "profile_not_object"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_PROFILE_JSON: _profile_json("Allure 50")}
    )
    assert result["errors"] == {"base": "reserved_name"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_PROFILE_JSON: _profile_json("Fine")}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_PROFILE] == "Fine"


async def test_options_cannot_reuse_another_stoves_sensor(hass: HomeAssistant) -> None:
    _entry("Other stove", OTHER_SOURCE).add_to_hass(hass)
    entry = _entry()
    entry.add_to_hass(hass)
    result = await _options(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SOURCE: OTHER_SOURCE, CONF_PROFILE: "Allure 50", CONF_EDIT_PROFILE: False},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "source_in_use"}
    assert entry.options[CONF_SOURCE] == SOURCE


async def test_options_keeping_own_sensor_is_allowed(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    result = await _options(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SOURCE: SOURCE, CONF_PROFILE: "Allure 50", CONF_EDIT_PROFILE: False},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_reimporting_the_same_name_reloads_this_stove(hass: HomeAssistant) -> None:
    await async_save_profile(hass, Profile.from_dict(json.loads(_profile_json("Mine"))))
    entry = _entry(profile="Mine")
    entry.add_to_hass(hass)
    # The saved options must be identical for the explicit reload to be needed, so this
    # entry already has the delay option (older entries get it added on first save).
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_UNAVAILABLE_DELAY: 60}
    )
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_schedule_reload"
    ) as reload:
        result = await _options(hass, entry)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_SOURCE: SOURCE, CONF_PROFILE: "Mine", CONF_EDIT_PROFILE: True},
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_PROFILE_JSON: _profile_json("Mine", ignite=180)}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    reload.assert_called_once_with(entry.entry_id)
    store = await async_get_profile_store(hass)
    assert store.get("Mine").thresholds["ignite"] == 180


async def test_editing_a_shared_profile_reloads_the_other_stoves(hass: HomeAssistant) -> None:
    await async_save_profile(hass, Profile.from_dict(json.loads(_profile_json("Mine"))))
    entry = _entry("Stove A", SOURCE, "Mine")
    other = _entry("Stove B", OTHER_SOURCE, "Mine")
    entry.add_to_hass(hass)
    other.add_to_hass(hass)
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_schedule_reload"
    ) as reload:
        result = await _options(hass, entry)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_SOURCE: SOURCE, CONF_PROFILE: "Mine", CONF_EDIT_PROFILE: True},
        )
        await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_PROFILE_JSON: _profile_json("Mine", ignite=190)}
        )
    reloaded = {call.args[0] for call in reload.call_args_list}
    assert other.entry_id in reloaded


# -- profile store -------------------------------------------------------------------------


async def test_store_lists_builtin_first_then_sorted_custom(hass: HomeAssistant) -> None:
    for name in ("Zed", "Alpha"):
        await async_save_profile(hass, Profile.from_dict(json.loads(_profile_json(name))))
    store = await async_get_profile_store(hass)
    assert store.names == ["Allure 50", "Alpha", "Zed"]


async def test_store_is_shared(hass: HomeAssistant) -> None:
    assert await async_get_profile_store(hass) is await async_get_profile_store(hass)


async def test_store_persists_saved_profiles(hass: HomeAssistant, hass_storage) -> None:
    await async_save_profile(hass, Profile.from_dict(json.loads(_profile_json("Mine"))))
    saved = hass_storage[STORE_KEY]["data"]["profiles"]
    assert saved["Mine"]["name"] == "Mine"


async def test_store_loads_saved_profiles_and_skips_invalid_ones(
    hass: HomeAssistant, hass_storage, caplog
) -> None:
    good = json.loads(_profile_json("Good"))
    hass_storage[STORE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": STORE_KEY,
        "data": {"profiles": {"Good": good, "Broken": {"name": "Broken"}}},
    }
    store = await async_get_profile_store(hass)
    assert store.names == ["Allure 50", "Good"]
    assert store.get("Broken") is None
    assert "Broken" in caplog.text


async def test_builtin_profiles_win_over_saved_ones_with_the_same_name(
    hass: HomeAssistant, hass_storage
) -> None:
    clash = json.loads(_profile_json("Allure 50", ignite=999))
    hass_storage[STORE_KEY] = {"version": 1, "data": {"profiles": {"Allure 50": clash}}}
    store = await async_get_profile_store(hass)
    assert store.get("Allure 50") is ALLURE_50
    assert store.names == ["Allure 50"]  # listed once


# -- reconfigure ----------------------------------------------------------------------------


async def _reconfigure(hass: HomeAssistant, entry):
    return await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )


async def test_reconfigure_changes_the_power_sensor(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    result = await _reconfigure(hass, entry)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert _field_names(result) == [CONF_SOURCE]
    assert _suggested(result, CONF_SOURCE) == SOURCE

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SOURCE: OTHER_SOURCE}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.options == {CONF_SOURCE: OTHER_SOURCE, CONF_PROFILE: "Allure 50"}


async def test_reconfigure_cannot_use_another_stoves_sensor(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    _entry("Second stove", OTHER_SOURCE).add_to_hass(hass)
    result = await _reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SOURCE: OTHER_SOURCE}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "source_in_use"}
    assert entry.options[CONF_SOURCE] == SOURCE
