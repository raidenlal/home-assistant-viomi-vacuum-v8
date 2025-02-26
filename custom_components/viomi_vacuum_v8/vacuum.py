"""
Support for the Viomi Vacuum V8 robot.

This integration has been refactored to replace deprecated Home Assistant
vacuum state constants with the new VacuumActivity enum. Additionally,
we’ve improved error handling, added type hints and comments, and simplified
certain parts of the business logic.
"""

import asyncio
import logging
from functools import partial
from datetime import timedelta
import ast

import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_HOST,
    CONF_NAME,
    CONF_TOKEN,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.components.vacuum import (
    PLATFORM_SCHEMA,
    VacuumActivity,
    VacuumEntityFeature,
    StateVacuumEntity,
)
from miio import DeviceException, ViomiVacuum  # pylint: disable=import-error

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "Viomi Vacuum V8"
DOMAIN = "viomi_vacuum_v8"
DATA_KEY = "viomi_vacuum_v8"

# -------------------------------------------------------------------
# PLATFORM SCHEMA & SERVICE DEFINITIONS
# -------------------------------------------------------------------

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_TOKEN): vol.All(cv.string, vol.Length(min=32, max=32)),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    },
    extra=vol.ALLOW_EXTRA,
)

SERVICE_CLEAN_ZONE = "clean_zone"
SERVICE_CLEAN_AREA = "clean_area"
SERVICE_CLEAN_POINT = "clean_point"
SERVICE_CLEAN_SEGMENT = "clean_segment"
SERVICE_OBS_CLEAN_ZONE = "xiaomi_clean_zone"
SERVICE_OBS_CLEAN_POINT = "xiaomi_clean_point"

ATTR_ZONE_ARRAY = "zone"
ATTR_ZONE_REPEATER = "repeats"
ATTR_AREA_ARRAY = "area"
ATTR_AREA_REPEATER = "repeats"
ATTR_POINT = "point"
ATTR_SEGMENTS = "segments"

VACUUM_SERVICE_SCHEMA = vol.Schema({vol.Optional(ATTR_ENTITY_ID): cv.comp_entity_ids})
SERVICE_SCHEMA_CLEAN_ZONE = VACUUM_SERVICE_SCHEMA.extend(
    {
        vol.Required(ATTR_ZONE_ARRAY): vol.All(
            list,
            [
                vol.ExactSequence(
                    [vol.Coerce(float), vol.Coerce(float), vol.Coerce(float), vol.Coerce(float)]
                )
            ],
        ),
        vol.Required(ATTR_ZONE_REPEATER): vol.All(vol.Coerce(int), vol.Clamp(min=1, max=3)),
    }
)
SERVICE_SCHEMA_CLEAN_AREA = VACUUM_SERVICE_SCHEMA.extend(
    {
        vol.Required(ATTR_AREA_ARRAY): vol.All(
            list,
            [vol.ExactSequence([vol.Coerce(float)] * 8)],
        ),
        vol.Required(ATTR_AREA_REPEATER): vol.All(vol.Coerce(int), vol.Clamp(min=1, max=3)),
    }
)
SERVICE_SCHEMA_CLEAN_POINT = VACUUM_SERVICE_SCHEMA.extend(
    {
        vol.Required(ATTR_POINT): vol.ExactSequence([vol.Coerce(float), vol.Coerce(float)])
    }
)
SERVICE_SCHEMA_CLEAN_SEGMENT = VACUUM_SERVICE_SCHEMA.extend(
    {
        vol.Required(ATTR_SEGMENTS): vol.Any(vol.Coerce(int), [vol.Coerce(int)])
    }
)

SERVICE_TO_METHOD = {
    SERVICE_CLEAN_ZONE: {"method": "async_clean_zone", "schema": SERVICE_SCHEMA_CLEAN_ZONE},
    SERVICE_CLEAN_AREA: {"method": "async_clean_area", "schema": SERVICE_SCHEMA_CLEAN_AREA},
    SERVICE_CLEAN_POINT: {"method": "async_clean_point", "schema": SERVICE_SCHEMA_CLEAN_POINT},
    SERVICE_CLEAN_SEGMENT: {"method": "async_clean_segment", "schema": SERVICE_SCHEMA_CLEAN_SEGMENT},
    SERVICE_OBS_CLEAN_ZONE: {"method": "async_clean_zone", "schema": SERVICE_SCHEMA_CLEAN_ZONE},
    SERVICE_OBS_CLEAN_POINT: {"method": "async_clean_point", "schema": SERVICE_SCHEMA_CLEAN_POINT},
}

FAN_SPEEDS = {"Silent": 0, "Standard": 1, "Medium": 2, "Turbo": 3}

# Supported features using the VacuumEntityFeature enum
SUPPORT_VIOMI = (
    VacuumEntityFeature.STATE
    | VacuumEntityFeature.PAUSE
    | VacuumEntityFeature.STOP
    | VacuumEntityFeature.RETURN_HOME
    | VacuumEntityFeature.FAN_SPEED
    | VacuumEntityFeature.LOCATE
    | VacuumEntityFeature.SEND_COMMAND
    | VacuumEntityFeature.BATTERY
    | VacuumEntityFeature.START
)

# Map internal run_state codes to VacuumActivity enum values
STATE_CODE_TO_ACTIVITY = {
    0: VacuumActivity.IDLE,
    1: VacuumActivity.IDLE,
    2: VacuumActivity.PAUSED,
    3: VacuumActivity.CLEANING,
    4: VacuumActivity.RETURNING,
    5: VacuumActivity.DOCKED,
    6: VacuumActivity.CLEANING,  # Vacuum & Mop
    7: VacuumActivity.CLEANING,  # Mop only
}

ALL_PROPS = [
    "run_state",
    "mode",
    "err_state",
    "battary_life",
    "box_type",
    "mop_type",
    "s_time",
    "s_area",
    "suction_grade",
    "water_grade",
    "remember_map",
    "has_map",
    "is_mop",
    "has_newmap",
    "hw_info",
    "sw_info",
    "start_time",
    "order_time",
    "v_state",
    "zone_data",
    "repeat_state",
    "light_state",
    "is_charge",
    "is_work",
]

VACUUM_CARD_PROPS_REFERENCES = {
    'cleaned_area': 's_area',
    'cleaning_time': 's_time'
}

# -------------------------------------------------------------------
# SETUP PLATFORM & SERVICES
# -------------------------------------------------------------------

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Viomi Vacuum V8 robot platform."""
    if DATA_KEY not in hass.data:
        hass.data[DATA_KEY] = {}

    host = config[CONF_HOST]
    token = config[CONF_TOKEN]
    name = config[CONF_NAME]

    _LOGGER.info("Initializing Viomi Vacuum at host %s with token %s...", host, token[:5])
    vacuum_device = ViomiVacuum(host, token)
    device_entity = ViomiVacuumEntity(name, vacuum_device)
    hass.data[DATA_KEY][host] = device_entity

    async_add_entities([device_entity], update_before_add=True)

    async def async_service_handler(service):
        """Handle service calls by mapping to entity methods."""
        method_info = SERVICE_TO_METHOD.get(service.service)
        if not method_info:
            _LOGGER.error("Unknown service: %s", service.service)
            return

        params = service.data.copy()
        # If no specific entity_id is provided, apply to all devices in hass.data[DATA_KEY]
        entity_ids = params.pop(ATTR_ENTITY_ID, list(hass.data[DATA_KEY].keys()))
        update_tasks = []

        for device in hass.data[DATA_KEY].values():
            if device.entity_id in entity_ids and hasattr(device, method_info["method"]):
                await getattr(device, method_info["method"])(**params)
                update_tasks.append(asyncio.create_task(device.async_update_ha_state(True)))
        if update_tasks:
            await asyncio.gather(*update_tasks)

    # Register all defined services
    for service_name, method_info in SERVICE_TO_METHOD.items():
        schema = method_info.get("schema", VACUUM_SERVICE_SCHEMA)
        hass.services.async_register(DOMAIN, service_name, async_service_handler, schema=schema)


# -------------------------------------------------------------------
# ENTITY IMPLEMENTATION
# -------------------------------------------------------------------

class ViomiVacuumEntity(StateVacuumEntity):
    """Representation of a Viomi Vacuum V8 robot."""

    def __init__(self, name: str, vacuum: ViomiVacuum) -> None:
        """Initialize the vacuum entity."""
        self._name = name
        self._vacuum = vacuum
        self._last_clean_point = None
        self.vacuum_state = None
        self._available = False

    @property
    def name(self) -> str:
        """Return the entity name."""
        return self._name

    @property
    def activity(self):
        """
        Return the current vacuum activity as a VacuumActivity enum value.

        This is derived from the internal 'run_state' property.
        """
        if self.vacuum_state is not None:
            try:
                state_code = int(self.vacuum_state.get('run_state', -1))
                return STATE_CODE_TO_ACTIVITY.get(state_code)
            except (ValueError, KeyError) as exc:
                _LOGGER.error("Error parsing run_state (%s): %s", self.vacuum_state.get('run_state'), exc)
                return None
        return None

    @property
    def state(self) -> str | None:
        """
        For backward compatibility, return the vacuum state as a string.

        The new Home Assistant standard is to expose the activity property,
        which should be a VacuumActivity enum.
        """
        activity = self.activity
        return activity.value if activity else None

    @property
    def battery_level(self) -> int | None:
        """Return the battery level from the fetched state."""
        if self.vacuum_state is not None:
            return self.vacuum_state.get('battary_life')
        return None

    @property
    def fan_speed(self) -> str | None:
        """Return the current fan speed as a friendly name."""
        if self.vacuum_state is not None:
            speed = self.vacuum_state.get('suction_grade')
            for key, val in FAN_SPEEDS.items():
                if val == speed:
                    return key
            return str(speed)
        return None

    @property
    def fan_speed_list(self) -> list:
        """Return a list of supported fan speed names."""
        return sorted(FAN_SPEEDS.keys(), key=lambda k: FAN_SPEEDS[k])

    @property
    def extra_state_attributes(self) -> dict:
        """Return all state attributes, including a human‐readable status."""
        attrs = {}
        if self.vacuum_state is not None:
            attrs.update(self.vacuum_state)
            try:
                attrs['status'] = self.activity.value
            except Exception as exc:
                _LOGGER.error("Failed to set status attribute: %s", exc)
                attrs['status'] = f"Undefined state {self.vacuum_state.get('run_state')}"
        return attrs

    @property
    def available(self) -> bool:
        """Return True if the vacuum is available."""
        return self._available

    @property
    def supported_features(self) -> VacuumEntityFeature:
        """Return supported features as a combination of VacuumEntityFeature flags."""
        return SUPPORT_VIOMI

    async def _try_command(self, error_msg: str, func, *args, **kwargs) -> bool:
        """
        Execute a command on the vacuum and log errors if they occur.
        """
        try:
            await self.hass.async_add_executor_job(partial(func, *args, **kwargs))
            return True
        except DeviceException as exc:
            _LOGGER.error(error_msg, exc)
            return False

    async def async_start(self):
        """Start or resume cleaning."""
        mode = self.vacuum_state.get('mode')
        is_mop = self.vacuum_state.get('is_mop')
        action_mode = 0

        if mode == 4 and self._last_clean_point is not None:
            method = 'set_pointclean'
            param = [1, self._last_clean_point[0], self._last_clean_point[1]]
        else:
            if mode == 2:
                action_mode = 2
            else:
                action_mode = 3 if is_mop == 2 else is_mop
            if mode == 3:
                method = 'set_mode'
                param = [3, 1]
            else:
                method = 'set_mode_withroom'
                param = [action_mode, 1, 0]
        await self._try_command("Unable to start the vacuum: %s", self._vacuum.raw_command, method, param)

    async def async_pause(self):
        """Pause the cleaning task."""
        mode = self.vacuum_state.get('mode')
        is_mop = self.vacuum_state.get('is_mop')
        action_mode = 0

        if mode == 4 and self._last_clean_point is not None:
            method = 'set_pointclean'
            param = [3, self._last_clean_point[0], self._last_clean_point[1]]
        else:
            if mode == 2:
                action_mode = 2
            else:
                action_mode = 3 if is_mop == 2 else is_mop
            if mode == 3:
                method = 'set_mode'
                param = [3, 3]
            else:
                method = 'set_mode_withroom'
                param = [action_mode, 3, 0]
        await self._try_command("Unable to pause the vacuum: %s", self._vacuum.raw_command, method, param)

    async def async_stop(self, **kwargs):
        """Stop cleaning without returning to base."""
        mode = self.vacuum_state.get('mode')
        if mode == 3:
            method = 'set_mode'
            param = [3, 0]
        elif mode == 4:
            method = 'set_pointclean'
            param = [0, 0, 0]
            self._last_clean_point = None
        else:
            method = 'set_mode'
            param = [0]
        await self._try_command("Unable to stop the vacuum: %s", self._vacuum.raw_command, method, param)

    async def async_set_fan_speed(self, fan_speed, **kwargs):
        """Set the fan speed of the vacuum."""
        if isinstance(fan_speed, str) and fan_speed.capitalize() in FAN_SPEEDS:
            fan_speed_value = FAN_SPEEDS[fan_speed.capitalize()]
        else:
            try:
                fan_speed_value = int(fan_speed)
            except ValueError as exc:
                _LOGGER.error("Fan speed step not recognized (%s). Valid speeds: %s", exc, self.fan_speed_list)
                return
        await self._try_command("Unable to set fan speed: %s", self._vacuum.raw_command, 'set_suction', [fan_speed_value])

    async def async_return_to_base(self, **kwargs):
        """Command the vacuum to return to its dock."""
        await self._try_command("Unable to return home: %s", self._vacuum.raw_command, 'set_charge', [1])

    async def async_locate(self, **kwargs):
        """Locate the vacuum."""
        await self._try_command("Unable to locate vacuum: %s", self._vacuum.raw_command, 'set_resetpos', [1])

    async def async_send_command(self, command, params=None, **kwargs):
        """
        Send a raw command to the vacuum.

        If the parameters come in as a single string that represents a list,
        they are safely evaluated using ast.literal_eval.
        """
        if isinstance(params, list) and len(params) == 1 and isinstance(params[0], str):
            param_str = params[0]
            if '[' in param_str and ']' in param_str:
                try:
                    params = ast.literal_eval(param_str)
                except Exception as exc:
                    _LOGGER.error("Error parsing parameters: %s", exc)
                    return
            elif param_str.isnumeric():
                params = [int(param_str)]
        await self._try_command("Unable to send command: %s", self._vacuum.raw_command, command, params)

    def update(self):
        """
        Fetch the current state from the device and update attributes.
        
        If the received state is incomplete, log a warning and mark the entity unavailable.
        Also, if the vacuum’s mode does not match the expected mop setting, issue a corrective command.
        """
        try:
            state = self._vacuum.raw_command('get_prop', ALL_PROPS)
            if not state or len(state) != len(ALL_PROPS):
                _LOGGER.warning("Incomplete state received: %s", state)
                self._available = False
                return
            self.vacuum_state = dict(zip(ALL_PROPS, state))
            for ref_key, orig_key in VACUUM_CARD_PROPS_REFERENCES.items():
                self.vacuum_state[ref_key] = self.vacuum_state.get(orig_key)
            self._available = True

            # Automatic mop mode correction based on box_type and mop_type
            current_mode = int(self.vacuum_state.get('is_mop', 0))
            box_type = int(self.vacuum_state.get('box_type', 0))
            has_mop = bool(self.vacuum_state.get('mop_type'))
            new_mode = None
            if box_type == 3:
                new_mode = 1 if has_mop else 0
            elif box_type == 2:
                new_mode = 2
            elif box_type == 1:
                new_mode = 0
            if new_mode is not None and new_mode != current_mode:
                _LOGGER.warning("Adjusting mop mode from %s to %s", current_mode, new_mode)
                self._vacuum.raw_command('set_mop', [new_mode])
                # Schedule an update after the corrective command
                asyncio.create_task(self.hass.async_add_executor_job(self.update))
        except OSError as exc:
            _LOGGER.error("OSError while fetching state: %s", exc)
            self._available = False
        except DeviceException as exc:
            _LOGGER.warning("DeviceException while fetching state: %s", exc)

    async def async_clean_zone(self, zone, repeats=1):
        """Clean a specified zone for a number of repeats."""
        result = []
        i = 0
        for z in zone:
            x1, y2, x2, y1 = z
            res = '_'.join(str(val) for val in [i, 0, x1, y1, x1, y2, x2, y2, x2, y1])
            for _ in range(repeats):
                result.append(res)
                i += 1
        result = [i] + result
        if await self._try_command("Unable to clean zone (upload map): %s", self._vacuum.raw_command, 'set_uploadmap', [1]):
            if await self._try_command("Unable to set zone: %s", self._vacuum.raw_command, 'set_zone', result):
                await self._try_command("Unable to start cleaning zone: %s", self._vacuum.raw_command, 'set_mode', [3, 1])

    async def async_clean_area(self, area, repeats=1):
        """Clean a specified area for a number of repeats."""
        result = []
        i = 0
        for a in area:
            coords = list(a)
            if len(coords) != 8:
                _LOGGER.error("Area definition must have 8 coordinates, got: %s", coords)
                return
            res = '_'.join(str(val) for val in [i, 0] + coords)
            for _ in range(repeats):
                result.append(res)
                i += 1
        result = [i] + result
        if await self._try_command("Unable to clean area (upload map): %s", self._vacuum.raw_command, 'set_uploadmap', [1]):
            if await self._try_command("Unable to set area: %s", self._vacuum.raw_command, 'set_zone', result):
                await self._try_command("Unable to start cleaning area: %s", self._vacuum.raw_command, 'set_mode', [3, 1])

    async def async_clean_point(self, point):
        """Clean a specific point."""
        x, y = point
        self._last_clean_point = point
        if await self._try_command("Unable to clean point (upload map): %s", self._vacuum.raw_command, 'set_uploadmap', [0]):
            await self._try_command("Unable to clean point (point clean): %s", self._vacuum.raw_command, 'set_pointclean', [1, x, y])

    async def async_clean_segment(self, segments):
        """Clean specified segment(s)."""
        if isinstance(segments, int):
            segments = [segments]
        if await self._try_command("Unable to clean segments (upload map): %s", self._vacuum.raw_command, 'set_uploadmap', [1]):
            params = [0, 1, len(segments)] + segments
            await self._try_command("Unable to clean segments (mode with room): %s", self._vacuum.raw_command, 'set_mode_withroom', params)
