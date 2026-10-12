"""Stove profiles: thresholds + per-state timings. No Home Assistant imports."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Any

from .const import ORDER, THRESHOLD_ORDER, TIMING_KEYS


# English text for every profile error, keyed by its code. The same codes are the keys of
# the translated messages in translations/*.json (under config.error and options.error),
# which is what the forms show; this text is for logs and tests.
_MESSAGES = {
    "profile_json_invalid": "not valid JSON ({reason}, line {line})",
    "profile_not_object": "profile must be a JSON object",
    "profile_name_invalid": "'name' must be a non-empty string",
    "profile_thresholds_not_object": "'thresholds' must be an object",
    "profile_threshold_missing": "missing threshold for '{state}'",
    "profile_threshold_not_number": "threshold '{state}' must be a number",
    "profile_threshold_not_finite": "threshold '{state}' must be a finite number",
    "profile_threshold_unknown": "unknown threshold state(s): {states}",
    "profile_thresholds_order": "thresholds must strictly decrease from 'ignite' down to 'idle'",
    "profile_timings_not_object": "'timings' must be an object",
    "profile_timing_unknown_state": "unknown state in timings: '{state}'",
    "profile_timing_state_not_object": "timings for '{state}' must be an object",
    "profile_timing_unknown_key": "unknown timing '{key}' for '{state}'",
    "profile_timing_not_number": "{state}.{key} must be a number",
    "profile_timing_not_finite": "{state}.{key} must be a finite number",
    "profile_timing_negative": "{state}.{key} must be 0 or more",
}
PROFILE_ERROR_CODES = tuple(_MESSAGES)


class ProfileError(ValueError):
    """Raised when profile data is invalid.

    `code` identifies the problem and `placeholders` holds the values to show with it, so
    the forms can show a translated message instead of the English text in `str(error)`.
    """

    def __init__(self, code: str, **placeholders: str) -> None:
        self.code = code
        self.placeholders = placeholders
        super().__init__(_MESSAGES[code].format(**placeholders))


def _number(value: Any, prefix: str, **placeholders: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProfileError(f"{prefix}_not_number", **placeholders)
    if not math.isfinite(value):
        raise ProfileError(f"{prefix}_not_finite", **placeholders)
    return float(value)


@dataclass(frozen=True)
class Profile:
    """A named set of thresholds and timings."""

    name: str
    thresholds: dict[str, float]
    timings: dict[str, dict[str, float]]

    def raw_state(self, power: float) -> str:
        """Map an averaged power value (watts) to a raw state."""
        for state in THRESHOLD_ORDER:
            if power > self.thresholds[state]:
                return state
        return "sensor_fault"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "thresholds": dict(self.thresholds),
            "timings": {s: dict(t) for s, t in self.timings.items()},
        }

    @classmethod
    def from_dict(cls, data: Any) -> Profile:
        if not isinstance(data, dict):
            raise ProfileError("profile_not_object")

        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ProfileError("profile_name_invalid")

        raw_thresholds = data.get("thresholds")
        if not isinstance(raw_thresholds, dict):
            raise ProfileError("profile_thresholds_not_object")
        thresholds: dict[str, float] = {}
        for state in THRESHOLD_ORDER:
            if state not in raw_thresholds:
                raise ProfileError("profile_threshold_missing", state=state)
            thresholds[state] = _number(
                raw_thresholds[state], "profile_threshold", state=state
            )
        extra = set(raw_thresholds) - set(THRESHOLD_ORDER)
        if extra:
            raise ProfileError("profile_threshold_unknown", states=", ".join(sorted(extra)))
        values = [thresholds[s] for s in THRESHOLD_ORDER]
        if any(a <= b for a, b in zip(values, values[1:])):
            raise ProfileError("profile_thresholds_order")

        raw_timings = data.get("timings", {})
        if not isinstance(raw_timings, dict):
            raise ProfileError("profile_timings_not_object")
        timings: dict[str, dict[str, float]] = {}
        for state, cfg in raw_timings.items():
            if state not in ORDER:
                raise ProfileError("profile_timing_unknown_state", state=state)
            if not isinstance(cfg, dict):
                raise ProfileError("profile_timing_state_not_object", state=state)
            clean: dict[str, float] = {}
            for key, value in cfg.items():
                if key not in TIMING_KEYS:
                    raise ProfileError("profile_timing_unknown_key", key=key, state=state)
                number = _number(value, "profile_timing", state=state, key=key)
                if number < 0:
                    raise ProfileError("profile_timing_negative", state=state, key=key)
                clean[key] = number
            timings[state] = clean

        return cls(name=name.strip(), thresholds=thresholds, timings=timings)


ALLURE_50 = Profile.from_dict(
    {
        "name": "Allure 50",
        "thresholds": {
            "ignite": 155,
            "burn_6": 140,
            "burn_5": 127,
            "burn_4": 115,
            "burn_3": 101,
            "burn_2": 86,
            "burn_1": 71,
            "cool_down": 60,
            "fault_extinguish": 32,
            "post_ignite": 19,
            "extinguish": 5,
            "idle": 1,
        },
        "timings": {
            "ignite": {"sequp": 0, "seqdown": 0, "nonseq": 0},
            "burn_6": {"sequp": 75, "seqdown": 30, "cascadeup": 30, "nonseq": 8},
            "burn_5": {"sequp": 75, "seqdown": 75, "cascadeup": 20, "cascadedown": 20, "nonseq": 10},
            "burn_4": {"sequp": 75, "seqdown": 75, "cascadeup": 20, "cascadedown": 20, "nonseq": 10},
            "burn_3": {"sequp": 75, "seqdown": 75, "cascadeup": 20, "cascadedown": 20, "nonseq": 10},
            "burn_2": {"sequp": 75, "seqdown": 75, "cascadeup": 20, "cascadedown": 20, "nonseq": 10},
            "burn_1": {"sequp": 10, "seqdown": 75, "cascadedown": 20, "nonseq": 8},
            "cool_down": {"sequp": 10, "seqdown": 50, "cascadeup": 25, "nonseq": 60},
            "fault_extinguish": {"sequp": 45, "seqdown": 60, "cascadedown": 45, "nonseq": 20},
            "post_ignite": {"sequp": 20, "seqdown": 10, "cascadedown": 60, "nonseq": 6},
            "extinguish": {"sequp": 30, "seqdown": 10, "nonseq": 6},
            "idle": {"sequp": 0, "seqdown": 0, "nonseq": 0},
            "sensor_fault": {"seqdown": 200, "nonseq": 200},
        },
    }
)

BUILTIN_PROFILES: dict[str, Profile] = {ALLURE_50.name: ALLURE_50}


def parse_profile_json(text: str) -> Profile:
    """Parse and validate profile JSON typed or pasted by the user."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as err:
        raise ProfileError(
            "profile_json_invalid",
            reason=err.msg,
            line=str(err.lineno),
            column=str(err.colno),
        ) from err
    return Profile.from_dict(data)


def template_json(profile: Profile) -> str:
    """JSON to pre-fill the import box. Built-in names are changed so it can be saved as-is."""
    data = profile.to_dict()
    if data["name"] in BUILTIN_PROFILES:
        data["name"] = f"{data['name']} (custom)"
    return json.dumps(data, indent=2)
