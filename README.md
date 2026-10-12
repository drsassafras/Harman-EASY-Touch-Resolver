# Harman EasyTouch Resolver

[![Validate](hhttps://github.com/drsassafras/Harman-EASY-Touch-Resolver/actions/workflows/validate.yaml/badge.svg)](https://github.com/drsassafras/Harman-EASY-Touch-Resolver/actions/workflows/validate.yaml)
[![Tests](hhttps://github.com/drsassafras/Harman-EASY-Touch-Resolver/actions/workflows/tests.yaml/badge.svg)](https://github.com/drsassafras/Harman-EASY-Touch-Resolver/actions/workflows/tests.yaml)

A Home Assistant integration that works out what a Harman pellet stove is doing by watching how much power it draws.

The stove does not report its own state, but each stage of operation (lighting, burning at each heat level, cooling down, idle) has a distinctive power draw. This integration takes a power sensor (in watts), smooths it with a 20 second moving average, maps that average to a state using a **profile**, and then settles on a final state using per-state timing rules, so brief blips don't cause flapping.

It does not talk to the stove. It only reads an existing Home Assistant power sensor (for example from a smart plug or an energy monitor), so there is no cloud service, no account and nothing to poll.

## Tested hardware

This integration was developed and tested on a **Harman Allure 50 (120V)** running **EasyTouch firmware [24.04.15](https://downloads.hearthnhome.com/installManuals/HarmanFW.zip)**.

Other stoves may work, but have not been tested. **We would love to hear from you with custom profiles for other stoves.** It is possible that stoves that are not EasyTouch could work with the right timings, but this has not been confirmed.

> **Note:** Because this integration infers state from power draw, failing or non-standard components (for example a worn igniter, a different fan or auger motor, or a replacement control board) can change the power levels and cause a profile to behave incorrectly.

## Entities

Each stove you add creates one device with:

| Entity | Description |
|---|---|
| **State** (sensor) | The resolved state: `sensor_fault`, `idle`, `extinguish`, `post_ignite`, `fault_extinguish`, `cool_down`, `burn_1` to `burn_6`, `ignite`. Has `raw_state` and `moving_average` attributes. |
| **General state** (sensor) | A simplified view: `Faulted`, `Lighting`, `Burning`, `Cooldown`, `Idle`. |
| **Active** (binary sensor) | On while the general state is `Lighting` or `Burning`. |

## Installation

### Prerequisites

- A Home Assistant power sensor (`device_class: power`, in watts) that measures the stove's electrical draw. A smart plug with energy monitoring works well.

### With HACS (recommended)

1. In HACS, open the three-dot menu and choose **Custom repositories**.
2. Add `https://github.com/YOUR_GITHUB_USER/harman_easytouch_resolver` with the category **Integration**.
3. Find **Harman EasyTouch Resolver** in HACS, download it, and restart Home Assistant.

### Manually

1. Copy `custom_components/harman_easytouch_resolver` into the `custom_components` folder of your Home Assistant configuration.
2. Restart Home Assistant.

### Add the stove

Go to **Settings → Devices & services → Add integration**, search for **Harman EasyTouch Resolver** and fill in:

| Field | Description |
|---|---|
| **Stove name** | A name for the stove, for example "Living room stove". It becomes the device name and must be unique. |
| **Power monitoring for pellet stove (watts)** | The power sensor described above. A sensor can only be used by one stove. |
| **Profile** | A built-in or saved profile, or *Import / design a new profile…* to open the JSON editor. |

## Changing settings

Select **Configure** on the integration. The first page has the same sensor and profile fields. To edit a profile's JSON at any time, tick **Edit profile JSON** and select **Submit**. The editor opens pre-filled with the selected profile.

Built-in profiles can't be overwritten, so editing one saves a copy under the new `name` you give it. Editing one of your own profiles under the same name updates it, and every stove using it reloads.

## Actions

This integration does not provide any actions.

## Removing the integration

1. Go to **Settings → Devices & services**, open **Harman EasyTouch Resolver**.
2. Open the three-dot menu on the stove and choose **Delete**. Repeat for each stove.
3. If you installed with HACS, remove it there too, or delete `custom_components/harman_easytouch_resolver` and restart.

Saved custom profiles are kept in `.storage/harman_easytouch_resolver.profiles`. Delete that file after removing the last stove if you no longer want them.

## Finding the right power levels for your stove

Every stove is a little different. To tune a profile:

1. Open the **State** entity and look at its `moving_average` attribute (under **Attributes** in the entity dialog, or in Developer Tools → States).
2. Watch the value as the stove goes through a normal cycle: lighting, each burn level, cooldown and off.
3. Note the watts at each stage and use them to adjust the thresholds in a custom profile.
4. Adjust the timings if states change too slowly or flap.

## Profiles

Profiles are JSON with a `name`, `thresholds` and optional `timings`.

Thresholds and timings both refer to the `moving_average` attribute, and all five timing keys are optional.

### Thresholds

Each value is the lower limit of a state, in watts. A state applies when the sensor's `moving_average` is above that state's threshold and not above the next state's threshold up. Values must strictly decrease from `ignite` down to `idle`. At or below the `idle` value the state is `sensor_fault`.

### Timings

A state change only becomes final after the new state has held for a set number of seconds. Each state's timings apply when moving into that state. The states have a fixed order: `sensor_fault`, `idle`, `extinguish`, `post_ignite`, `fault_extinguish`, `cool_down`, `burn_1` to `burn_6`, `ignite`. All keys are optional.

| Key | Seconds to wait when... | If missing |
|---|---|---|
| `sequp` | moving up one step into this state | 0 |
| `seqdown` | moving down one step into this state | 0 |
| `nonseq` | jumping more than one step (for example `burn_1` to `burn_3`) | 0 |
| `cascadeup` | moving up one step after an unfinished change | uses `sequp` |
| `cascadedown` | moving down one step after an unfinished change | uses `seqdown` |

A change is "unfinished" when the state changes again before the previous change became final. Example: the stove is at `burn_1` and moves to `burn_2`, but before the wait ends it moves to `burn_3`. The wait for `burn_3` then uses `cascadeup` instead of `sequp`. A new change always cancels the one still waiting.

A state that has no entry in `timings` at all waits 3 seconds for every kind of move.

### Example

```json
{
  "name": "My stove",
  "thresholds": {
    "ignite": 155, "burn_6": 140, "burn_5": 127, "burn_4": 115,
    "burn_3": 101, "burn_2": 86, "burn_1": 71, "cool_down": 60,
    "fault_extinguish": 32, "post_ignite": 19, "extinguish": 5, "idle": 1
  },
  "timings": {
    "burn_3": { "sequp": 75, "seqdown": 75, "cascadeup": 20, "cascadedown": 20, "nonseq": 10 },
    "idle": { "sequp": 0, "seqdown": 0, "nonseq": 0 }
  }
}
```

## How it behaves

- The 20 second moving average is fixed because of the stove's 10 second power cycle.
- After a restart, or when the power sensor comes back from unavailable, the integration waits for a full 20 seconds of data before resolving a state. The previous resolved state is remembered, and the first reading that disagrees with it is applied after 30 seconds.
- When the power sensor becomes unavailable or not a number, all three entities keep showing the last state for the **Keep last state when the sensor drops out** time (60 seconds by default, 0 to 600 in the options). Only if the sensor is still bad after that do they show as unavailable. Set it to 0 for the old behaviour. A short outage therefore leaves no gap in the history.
- The same time covers a Home Assistant restart: the last state is restored and shown while the power sensor comes online. If your power sensor takes longer than that to start (for example a Zigbee or MQTT device), raise the value. Time while Home Assistant itself is not running cannot be recorded.
- If readings were missing for more than 20 seconds, the integration waits for a fresh 20 second window before changing the state.
- Updates are event driven: the integration reacts to the power sensor's state changes and never polls.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Entities are unavailable | The power sensor has been unavailable, unknown or not numeric for longer than the keep-last-state time. |
| State is `unknown` | Waiting for the first 20 seconds of readings. |
| State flaps between two levels | Thresholds sit too close to the stove's real power at that level. Check `moving_average` and move the threshold. Increase the timings for that state. |
| State is stuck on `sensor_fault` | `moving_average` is at or below the profile's `idle` value. Check the sensor's units are watts. |
| "Profile not found" in the log | A stove refers to a profile that no longer exists. It falls back to `Allure 50`. |

## Translations

English, Canadian English, Canadian French, Irish and Welsh. The Irish and Welsh have not been reviewed by native speakers; corrections are welcome.

## Development

```bash
pip install -r requirements_test.txt
pytest
```

`tests/test_profile.py`, `tests/test_engine.py` and `tests/test_translations.py` need nothing but Python. The others use the Home Assistant test harness. See [docs/quality_scale.md](docs/quality_scale.md) for how the integration lines up with Home Assistant's quality scale.

## Contributing

Custom profiles for other stoves are very welcome. Please open an issue with your stove model, firmware version, and the profile JSON.
