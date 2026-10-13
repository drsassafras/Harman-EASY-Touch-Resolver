"""Translations and manifest sanity checks (no Home Assistant needed)."""

import json
from pathlib import Path
import re

import pytest

COMPONENT = Path(__file__).parent.parent / "custom_components" / "harman_easytouch_resolver"
TRANSLATIONS = sorted((COMPONENT / "translations").glob("*.json"))
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _flatten(node, prefix=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _flatten(value, f"{prefix}.{key}" if prefix else key)
    else:
        yield prefix, node


def _load(path: Path) -> dict[str, str]:
    return dict(_flatten(json.loads(path.read_text(encoding="utf-8"))))


EN = _load(COMPONENT / "translations" / "en.json")


def test_expected_languages_exist():
    assert {p.stem for p in TRANSLATIONS} >= {"en", "fr-CA", "ga", "cy"}


@pytest.mark.parametrize("path", TRANSLATIONS, ids=lambda p: p.stem)
def test_same_keys_as_english(path):
    other = _load(path)
    assert set(other) == set(EN), (set(EN) ^ set(other))


@pytest.mark.parametrize("path", TRANSLATIONS, ids=lambda p: p.stem)
def test_placeholders_match_english(path):
    other = _load(path)
    for key, text in EN.items():
        assert set(PLACEHOLDER.findall(text)) == set(PLACEHOLDER.findall(other[key])), key


@pytest.mark.parametrize("path", TRANSLATIONS, ids=lambda p: p.stem)
def test_no_empty_strings(path):
    assert all(text.strip() for text in _load(path).values())


def test_every_form_field_has_label_and_description():
    for step_path in ("config.step.user", "config.step.import_profile",
                      "config.step.reconfigure",
                      "options.step.init", "options.step.import_profile"):
        data = {k for k in EN if k.startswith(f"{step_path}.data.")}
        desc = {k for k in EN if k.startswith(f"{step_path}.data_description.")}
        assert data, step_path
        assert {k.rsplit(".", 1)[1] for k in data} == {k.rsplit(".", 1)[1] for k in desc}


def test_options_form_labels_are_human_readable():
    for key in ("source_entity", "profile", "edit_profile"):
        assert EN[f"options.step.init.data.{key}"] != key
    assert "pellet stove" in EN["options.step.init.data.source_entity"].lower()


def test_manifest():
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    for key in ("domain", "name", "version", "documentation", "issue_tracker", "codeowners"):
        assert key in manifest
    assert "example.com" not in manifest["documentation"]
    assert "example.com" not in manifest["issue_tracker"]
    assert manifest["issue_tracker"].startswith(manifest["documentation"])
    assert manifest["config_flow"] is True


def test_brand_icons_exist():
    assert (COMPONENT / "brand" / "icon.png").is_file()


def test_icons_json_state_keys_are_valid_translation_keys():
    icons = json.loads((COMPONENT / "icons.json").read_text())
    pattern = re.compile(r"^(?!.+__)(?!_)[\da-z_]+(?<!_)$")
    for platform in icons["entity"].values():
        for entity in platform.values():
            for state in entity.get("state", {}):
                assert pattern.match(state), state


def test_every_sensor_state_has_a_name_in_every_language():
    from custom_components.harman_easytouch_resolver.const import ORDER

    for path in TRANSLATIONS:
        keys = _load(path)
        prefix = "entity.sensor.state.state."
        found = {k[len(prefix):] for k in keys if k.startswith(prefix)}
        assert found == set(ORDER), path.stem


def test_every_entity_has_a_name_in_every_language():
    for path in TRANSLATIONS:
        keys = _load(path)
        for key in (
            "entity.sensor.state.name",
            "entity.sensor.general_state.name",
            "entity.binary_sensor.active.name",
        ):
            assert keys[key].strip(), (path.stem, key)


def test_repair_and_reconfigure_texts_exist():
    for key in (
        "issues.profile_missing.title",
        "issues.profile_missing.description",
        "config.abort.reconfigure_successful",
    ):
        assert key in EN


def test_every_general_state_has_a_translation_and_an_icon():
    from custom_components.harman_easytouch_resolver.const import (
        ACTIVE_GENERAL_STATES,
        GENERAL_STATE_MAP,
        GENERAL_STATE_OPTIONS,
    )

    assert set(GENERAL_STATE_MAP.values()) == set(GENERAL_STATE_OPTIONS)
    assert ACTIVE_GENERAL_STATES <= set(GENERAL_STATE_OPTIONS)
    for path in TRANSLATIONS:
        keys = _load(path)
        prefix = "entity.sensor.general_state.state."
        found = {k[len(prefix):] for k in keys if k.startswith(prefix)}
        assert found == set(GENERAL_STATE_OPTIONS), path.stem
    icons = json.loads((COMPONENT / "icons.json").read_text())
    # "unknown" has its own icon too; every real value needs one.
    icon_keys = set(icons["entity"]["sensor"]["general_state"]["state"]) - {"unknown"}
    assert icon_keys == set(GENERAL_STATE_OPTIONS)


def test_every_profile_error_has_a_translated_message():
    from custom_components.harman_easytouch_resolver.profile import (
        _MESSAGES,
        PROFILE_ERROR_CODES,
    )

    for path in TRANSLATIONS:
        keys = _load(path)
        for section in ("config", "options"):
            for code in PROFILE_ERROR_CODES:
                text = keys[f"{section}.error.{code}"]
                # Only placeholders the code can supply (the JSON error adds a column).
                allowed = set(PLACEHOLDER.findall(_MESSAGES[code])) | {"column"}
                assert set(PLACEHOLDER.findall(text)) <= allowed, (path.stem, code)
            assert f"{section}.error.invalid_profile" not in keys


def test_the_import_option_and_state_attributes_are_translated():
    from custom_components.harman_easytouch_resolver.const import IMPORT_NEW, ORDER

    for path in TRANSLATIONS:
        keys = _load(path)
        assert keys[f"selector.profile.options.{IMPORT_NEW}"].strip(), path.stem
        assert keys["entity.sensor.moving_average.name"].strip()
        prefix = "entity.sensor.raw_state.state."
        assert {k[len(prefix):] for k in keys if k.startswith(prefix)} == set(ORDER), path.stem
        assert keys["entity.sensor.raw_state.name"].strip()


def test_translated_text_does_not_quote_the_english_import_label():
    for path in TRANSLATIONS:
        if path.stem != "en":
            assert "Import / design a new profile" not in path.read_text(encoding="utf-8")


def test_translation_keys_are_valid():
    key_pattern = re.compile(r"^(?!.+__)(?!_)[\da-z_]+(?<!_)$")
    from custom_components.harman_easytouch_resolver.const import IMPORT_NEW

    assert key_pattern.match(IMPORT_NEW)


def test_icons_switch_with_the_state_and_never_default_to_a_lit_fireplace():
    from custom_components.harman_easytouch_resolver.const import (
        ACTIVE_GENERAL_STATES,
        GENERAL_STATE_MAP,
        ORDER,
    )

    icons = json.loads((COMPONENT / "icons.json").read_text())["entity"]
    state = icons["sensor"]["state"]
    assert icons["sensor"]["raw_state"] == state  # the raw state looks like the resolved one
    general = icons["sensor"]["general_state"]
    active = icons["binary_sensor"]["active"]

    # Anything that is not matched (unavailable, an unexpected value) must not look lit.
    for entry in (state, general, active):
        assert entry["default"] == "mdi:fireplace-off"
        assert entry["state"]["unknown"] == "mdi:help-circle-outline"

    for raw, value in GENERAL_STATE_MAP.items():
        assert raw in state["state"], raw
        assert value in general["state"], value
    assert set(state["state"]) - {"unknown"} == set(ORDER)

    # Idle is never shown with a fire, in either sensor or the binary sensor.
    assert state["state"]["idle"] == general["state"]["idle"] == "mdi:fireplace-off"
    assert active["state"]["on"] == "mdi:fireplace"
    # Cooling down is still active, so it uses the same lit fireplace as the binary sensor.
    assert state["state"]["cool_down"] == state["state"]["extinguish"] == "mdi:fireplace"
    assert general["state"]["cooldown"] == "mdi:fireplace"
    assert {"lighting", "burning", "cooldown"} == ACTIVE_GENERAL_STATES

    # The general state always uses the same family of icon as the raw states it covers.
    families = {
        "faulted": {"mdi:alert-circle", "mdi:alert"},
        "lighting": {"mdi:fire-circle"},
        "burning": {"mdi:fire"},
        "cooldown": {"mdi:fireplace"},
        "idle": {"mdi:fireplace-off"},
    }
    for raw, value in GENERAL_STATE_MAP.items():
        assert state["state"][raw] in families[value], raw
        assert general["state"][value] in families[value], value
