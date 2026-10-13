# Home Assistant quality scale: self-assessment

Home Assistant does not review or rate custom integrations, so there is no official tier for this one. This page checks it against every rule of the Bronze, Silver, Gold and Platinum tiers ([rule list](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/)).

How to read the status column:

- **Done**: implemented and covered by a test or a check.
- **Exempt**: the rule does not apply, with the reason.

## Bronze

| Rule | Status | Notes |
|---|---|---|
| action-setup | Exempt | No actions. |
| appropriate-polling | Done | No polling; reacts to the power sensor's state changes. |
| brands | Done | `brand/icon.png` and `brand/icon@2x.png`. |
| common-modules | Done | Shared entity base in `entity.py`; engine and runtime split from the platforms. No coordinator: there is no data to fetch. |
| config-flow-test-coverage | Done | `tests/test_config_flow.py` covers the config flow, options flow, reconfigure flow and profile store. |
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
| test-before-setup | Exempt | Nothing to connect to. An unavailable sensor keeps the last state, then makes the entities unavailable, rather than failing setup. |
| unique-config-entry | Done | Unique by stove name and by power sensor. |

## Silver

| Rule | Status | Notes |
|---|---|---|
| action-exceptions | Exempt | No actions. |
| config-entry-unloading | Done | `async_unload_entry`; tested. |
| docs-configuration-parameters | Done | README "Changing settings" lists every option. |
| docs-installation-parameters | Done | README "Add the stove". |
| entity-unavailable | Done | Entities keep the last state for the configured time, then become unavailable. |
| integration-owner | Done | `codeowners` in `manifest.json`. |
| log-when-unavailable | Done | One warning when the power sensor stays down past the keep-last-state time, one info message when it reports again; tested. |
| parallel-updates | Done | `PARALLEL_UPDATES = 0` on both platforms (nothing is fetched). |
| reauthentication-flow | Exempt | No authentication. |
| test-coverage | Done | 100% of all modules on the last local run (`pytest --cov`). |

## Gold

| Rule | Status | Notes |
|---|---|---|
| devices | Done | One device per stove. |
| diagnostics | Done | `diagnostics.py`: options, profile, averaging state and the source sensor; tested. |
| discovery / discovery-update-info | Exempt | There is no network device to discover. |
| docs-data-update | Done | README "How it behaves". |
| docs-examples | Done | README "Automation examples". |
| docs-known-limitations | Done | README "Known limitations". |
| docs-supported-devices | Done | README "Tested hardware". |
| docs-supported-functions | Done | README "Entities". |
| docs-troubleshooting | Done | README "Troubleshooting". |
| docs-use-cases | Done | README "Use cases". |
| dynamic-devices | Exempt | One device per config entry. |
| entity-category | Exempt | No diagnostic or configuration entities. |
| entity-device-class | Done | ENUM sensors and a RUNNING binary sensor. |
| entity-disabled-by-default | Exempt | Three entities, none noisy. |
| entity-translations | Done | Names, every state of the state sensors and the diagnostic sensors' names are translated (English, Canadian French, Irish, Welsh). Irish and Welsh are not native-reviewed. |
| exception-translations | Exempt | The integration raises no exceptions to the user. Profile validation problems are shown as translated form errors. |
| icon-translations | Done | `icons.json` covers every state of both sensors and the binary sensor. |
| reconfiguration-flow | Done | Reconfigure changes the power sensor; tested. |
| repair-issues | Done | A missing profile raises a repair item that clears itself; tested. |
| stale-devices | Exempt | One device per config entry; it is removed with the entry. |

## Platinum

| Rule | Status | Notes |
|---|---|---|
| async-dependency | Exempt | No dependencies. |
| inject-websession | Exempt | No dependencies, no web requests. |
| strict-typing | Done | `[tool.mypy] strict = true`; `mypy` reports no issues, and the `mypy` CI job keeps it that way. |

The code is fully asynchronous and event driven.
