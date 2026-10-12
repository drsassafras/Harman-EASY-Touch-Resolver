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
    assert {p.stem for p in TRANSLATIONS} >= {"en", "en-CA", "fr-CA", "ga", "cy"}


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
