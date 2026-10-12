# Home Assistant quality scale: Bronze self-assessment

Custom integrations are not reviewed against the quality scale, but this one follows the Bronze rules where they apply.

| Rule | Status | Notes |
|---|---|---|
| action-setup | Exempt | No actions. |
| appropriate-polling | Done | No polling; reacts to the power sensor's state changes. |
| brands | Done | `brand/icon.png` and `brand/icon@2x.png`. |
| common-modules | Done | Shared entity base in `entity.py`; engine and runtime split from the platforms. No coordinator: there is no data to fetch. |
| config-flow-test-coverage | Written, not yet run | `tests/test_config_flow.py` is written to cover every branch of the config flow, options flow and profile store. Run `pytest --cov` and check `config_flow.py` reaches 100%. |
| config-flow | Done | Set up and changed entirely from the UI; every field has a label and a description. |
| dependency-transparency | Done | No external requirements. |
| docs-actions | Done | README states there are no actions. |
| docs-triggers / docs-conditions | Exempt | The integration defines none. |
| docs-high-level-description | Done | README introduction. |
| docs-installation-instructions | Done | README: prerequisites, HACS and manual install, configuration fields. |
| docs-removal-instructions | Done | README. |
| entity-event-setup | Done | Entities subscribe in `async_added_to_hass` and unsubscribe with `async_on_remove`. |
| entity-unique-id | Done | `<entry_id>_<key>`. |
| has-entity-name | Done | |
| runtime-data | Done | `entry.runtime_data`. |
| test-before-configure | Exempt | There is no connection to test; the sensor is picked with an entity selector. A sensor can't be used by two stoves. |
| test-before-setup | Exempt | Nothing to connect to. An unavailable sensor makes the entities unavailable rather than failing setup. |
| unique-config-entry | Done | Unique by stove name and by power sensor. |

## Known gaps beyond Bronze

- Entity names and enum states are not translated (names are fixed English strings); the "Import / design a new profile…" dropdown entry is English only.
- No diagnostics, repair issues or reconfigure flow.
