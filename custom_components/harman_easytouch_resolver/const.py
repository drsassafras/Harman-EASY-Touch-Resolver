"""Constants for the Harman EasyTouch Resolver integration."""

DOMAIN = "harman_easytouch_resolver"

CONF_SOURCE = "source_entity"
CONF_PROFILE = "profile"
CONF_PROFILE_JSON = "profile_json"

DEFAULT_PROFILE = "Allure 50"

# Fixed by the stove's 10 second cycle: 20 s is the only window that works.
MOVING_AVERAGE_SECONDS = 20
# After a restart / source recovery, wait this long before syncing to the raw state.
STARTUP_SYNC_SECONDS = 30

# Timing used for a state a profile does not configure (matches the old automation).
DEFAULT_TIMING = {"sequp": 3, "seqdown": 3, "nonseq": 3}
TIMING_KEYS = ("sequp", "seqdown", "cascadeup", "cascadedown", "nonseq")

# Fixed state order. Sequential up/down is decided by position in this list.
ORDER = [
    "sensor_fault",
    "idle",
    "extinguish",
    "post_ignite",
    "fault_extinguish",
    "cool_down",
    "burn_1",
    "burn_2",
    "burn_3",
    "burn_4",
    "burn_5",
    "burn_6",
    "ignite",
]

# Raw state ladder, highest first. Each threshold is "power > value".
# Anything at or below the last one is "sensor_fault".
THRESHOLD_ORDER = [
    "ignite",
    "burn_6",
    "burn_5",
    "burn_4",
    "burn_3",
    "burn_2",
    "burn_1",
    "cool_down",
    "fault_extinguish",
    "post_ignite",
    "extinguish",
    "idle",
]

GENERAL_STATE_MAP = {
    "sensor_fault": "Faulted",
    "fault_extinguish": "Faulted",
    "ignite": "Lighting",
    "post_ignite": "Lighting",
    "burn_1": "Burning",
    "burn_2": "Burning",
    "burn_3": "Burning",
    "burn_4": "Burning",
    "burn_5": "Burning",
    "burn_6": "Burning",
    "extinguish": "Cooldown",
    "cool_down": "Cooldown",
    "idle": "Idle",
}
GENERAL_STATE_OPTIONS = ["Faulted", "Lighting", "Burning", "Cooldown", "Idle"]

# The binary sensor is on when the general state is one of these.
ACTIVE_GENERAL_STATES = {"Lighting", "Burning"}

# Dropdown value that means "let me import / design a new profile".
IMPORT_NEW = "__import_new__"
