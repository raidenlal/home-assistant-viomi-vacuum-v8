"""Support for the Viomi Vacuum V8 robot."""
import asyncio
import ast
from functools import partial
import logging
from typing import Any, Dict, List, Optional, Union

from miio import DeviceException, ViomiVacuum  # pylint: disable=import-error
import voluptuous as vol

from homeassistant.components.vacuum import (
    PLATFORM_SCHEMA,
    VacuumActivity,
    VacuumEntityFeature,
    StateVacuumEntity,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_HOST,
    CONF_NAME,
    CONF_TOKEN,
    STATE_OFF,
    STATE_ON,
)
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME: str = "Viomi Vacuum V8"
DOMAIN: str = "viomi_vacuum_v8"
DATA_KEY: str = "viomi_vacuum_v8"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_TOKEN): vol.All(cv.string, vol.Length(min=32, max=32)),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    },
    extra=vol.ALLOW_EXTRA,
)

# Service definitions
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
            [
                vol.ExactSequence(
                    [
                        vol.Coerce(float), vol.Coerce(float), vol.Coerce(float),
                        vol.Coerce(float), vol.Coerce(float), vol.Coerce(float),
                        vol.Coerce(float), vol.Coerce(float)
                    ]
                )
            ],
        ),
        vol.Required(ATTR_AREA_REPEATER): vol.All(vol.Coerce(int), vol.Clamp(min=1, max=3)),
    }
)
SERVICE_SCHEMA_CLEAN_POINT = VACUUM_SERVICE_SCHEMA.extend(
    {
        vol.Required(ATTR_POINT): vol.All(vol.ExactSequence([vol.Coerce(float), vol.Coerce(float)]))
    }
)
SERVICE_SCHEMA_CLEAN_SEGMENT = VACUUM_SERVICE_SCHEMA.extend(
    {vol.Required(ATTR_SEGMENTS): vol.Any(vol.Coerce(int), [vol.Coerce(int)])}
)

SERVICE_TO_METHOD: Dict[str, Dict[str, Any]] = {
    SERVICE_CLEAN_ZONE: {"method": "async_clean_zone", "schema": SERVICE_SCHEMA_CLEAN_ZONE},
    SERVICE_CLEAN_AREA: {"method": "async_clean_area", "schema": SERVICE_SCHEMA_CLEAN_AREA},
    SERVICE_CLEAN_POINT: {"method": "async_clean_point", "schema": SERVICE_SCHEMA_CLEAN_POINT},
    SERVICE_CLEAN_SEGMENT: {"method": "async_clean_segment", "schema": SERVICE_SCHEMA_CLEAN_SEGMENT},
    SERVICE_OBS_CLEAN_ZONE: {"method": "async_clean_zone", "schema": SERVICE_SCHEMA_CLEAN_ZONE},
    SERVICE_OBS_CLEAN_POINT: {"method": "async_clean_point", "schema": SERVICE_SCHEMA_CLEAN_POINT},
}

FAN_SPEEDS: Dict[str, int] = {"Silent": 0, "Standard": 1, "Medium": 2, "Turbo": 3}

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

STATE_CODE_TO_STATE: Dict[int, VacuumActivity] = {
    0: VacuumActivity.IDLE,
    1: VacuumActivity.IDLE,
    2: VacuumActivity.PAUSED,
    3: VacuumActivity.CLEANING,
    4: VacuumActivity.RETURNING,
    5: VacuumActivity.DOCKED,
    6: VacuumActivity.CLEANING,  # Vacuum & Mop
    7: VacuumActivity.CLEANING,  # Mop only
}

ALL_PROPS: List[str] = [
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
    "is_work"
]

VACUUM_CARD_PROPS_REFERENCES: Dict[str, str] = {
    "cleaned_area": "s_area",
    "cleaning_time": "s_time"
}


async def async_setup_platform(
    hass: Any, config: Dict[str, Any], async_add_entities: Any, discovery_info: Optional[Any] = None
) -> None:
    """Set up the Viomi Vacuum V8 robot platform."""
    if DATA_KEY not in hass.data:
        hass.data[DATA_KEY] = {}

    host: str = config[CONF_HOST]
    token: str = config[CONF_TOKEN]
    name: str = config[CONF_NAME]

    _LOGGER.info("Initializing with host %s (token %s...)", host, token[:5])

    vacuum = ViomiVacuum(host, token)
    device = ViomiVacuumEntity(name, vacuum)
    hass.data[DATA_KEY][host] = device

    async_add_entities([device], update_before_add=True)

    async def async_service_handler(service: Any) -> None:
        """Map services to methods on Viomi Vacuum V8."""
        method = SERVICE_TO_METHOD.get(service.service)
        params = service.data.copy()
        entity_ids = params.pop(ATTR_ENTITY_ID, hass.data[DATA_KEY].values())
        update_tasks = []

        for device in filter(lambda x: x.entity_id in entity_ids, hass.data[DATA_KEY].values()):
            if not hasattr(device, method["method"]):
                continue
            await getattr(device, method["method"])(**params)
            update_tasks.append(device.async_update_ha_state(True))
        if update_tasks:
            await asyncio.gather(*update_tasks)

    for vacuum_service in SERVICE_TO_METHOD:
        schema = SERVICE_TO_METHOD[vacuum_service].get("schema", VACUUM_SERVICE_SCHEMA)
        hass.services.async_register(DOMAIN, vacuum_service, async_service_handler, schema=schema)


class ViomiVacuumEntity(StateVacuumEntity):
    """Representation of a Viomi Vacuum V8 robot."""

    def __init__(self, name: str, vacuum: ViomiVacuum) -> None:
        """Initialize the device handler."""
        self._name: str = name
        self._vacuum: ViomiVacuum = vacuum
        self._last_clean_point: Optional[List[float]] = None
        self.vacuum_state: Optional[Dict[str, Any]] = None
        self._available: bool = False

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return self._name

    @property
    def state(self) -> Optional[VacuumActivity]:
        """Return the state."""
        if self.vacuum_state is not None:
            try:
                return STATE_CODE_TO_STATE[int(self.vacuum_state["run_state"])]
            except KeyError:
                _LOGGER.error("STATE not supported, state_code: %s", self.vacuum_state["run_state"])
        return None

    @property
    def battery_level(self) -> Optional[Any]:
        """Return the battery level of the device."""
        if self.vacuum_state is not None:
            return self.vacuum_state.get("battary_life")
        return None

    @property
    def fan_speed(self) -> Optional[Union[str, int]]:
        """Return the fan speed of the device."""
        if self.vacuum_state is not None:
            speed = self.vacuum_state.get("suction_grade")
            if speed in FAN_SPEEDS.values():
                return next((key for key, value in FAN_SPEEDS.items() if value == speed), speed)
            return speed
        return None

    @property
    def fan_speed_list(self) -> List[str]:
        """Get the list of available fan speed steps of the device."""
        return sorted(FAN_SPEEDS.keys(), key=lambda s: FAN_SPEEDS[s])

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the specific state attributes of this device."""
        attrs: Dict[str, Any] = {}
        if self.vacuum_state is not None:
            attrs.update(self.vacuum_state)
            try:
                attrs["status"] = STATE_CODE_TO_STATE[int(self.vacuum_state["run_state"])]
            except KeyError:
                _LOGGER.error("Definition missing for state %s", self.vacuum_state.get("run_state"))
        return attrs

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    @property
    def supported_features(self) -> VacuumEntityFeature:
        """Flag vacuum cleaner robot features that are supported."""
        return SUPPORT_VIOMI

    async def _try_command(self, mask_error: str, func: Any, *args: Any, **kwargs: Any) -> bool:
        """Call a vacuum command handling error messages."""
        try:
            await self.hass.async_add_executor_job(partial(func, *args, **kwargs))
            return True
        except DeviceException as exc:
            _LOGGER.error(mask_error, exc, exc_info=True)
            return False

    async def async_start(self) -> None:
        """Start or resume the cleaning task."""
        mode = self.vacuum_state["mode"]
        is_mop = self.vacuum_state["is_mop"]
        actionMode = 0

        if mode == 4 and self._last_clean_point is not None:
            method = "set_pointclean"
            param = [1, self._last_clean_point[0], self._last_clean_point[1]]
        else:
            if mode == 2:
                actionMode = 2
            else:
                actionMode = 3 if is_mop == 2 else is_mop
            if mode == 3:
                method = "set_mode"
                param = [3, 1]
            else:
                method = "set_mode_withroom"
                param = [actionMode, 1, 0]
        await self._try_command("Unable to start the vacuum: %s", self._vacuum.raw_command, method, param)

    async def async_pause(self) -> None:
        """Pause the cleaning task."""
        mode = self.vacuum_state["mode"]
        is_mop = self.vacuum_state["is_mop"]
        actionMode = 0

        if mode == 4 and self._last_clean_point is not None:
            method = "set_pointclean"
            param = [3, self._last_clean_point[0], self._last_clean_point[1]]
        else:
            if mode == 2:
                actionMode = 2
            else:
                actionMode = 3 if is_mop == 2 else is_mop
            if mode == 3:
                method = "set_mode"
                param = [3, 3]
            else:
                method = "set_mode_withroom"
                param = [actionMode, 3, 0]
        await self._try_command("Unable to set pause: %s", self._vacuum.raw_command, method, param)

    async def async_stop(self, **kwargs: Any) -> None:
        """Stop the vacuum cleaner."""
        mode = self.vacuum_state["mode"]
        if mode == 3:
            method = "set_mode"
            param = [3, 0]
        elif mode == 4:
            method = "set_pointclean"
            param = [0, 0, 0]
            self._last_clean_point = None
        else:
            method = "set_mode"
            param = [0]
        await self._try_command("Unable to stop: %s", self._vacuum.raw_command, method, param)

    async def async_set_fan_speed(self, fan_speed: Union[str, int], **kwargs: Any) -> None:
        """Set fan speed."""
        if isinstance(fan_speed, str) and fan_speed.capitalize() in FAN_SPEEDS:
            fan_speed = FAN_SPEEDS[fan_speed.capitalize()]
        else:
            try:
                fan_speed = int(fan_speed)
            except ValueError as exc:
                _LOGGER.error("Fan speed step not recognized (%s). Valid speeds are: %s", exc, self.fan_speed_list)
                return
        await self._try_command("Unable to set fan speed: %s", self._vacuum.raw_command, "set_suction", [fan_speed])

    async def async_return_to_base(self, **kwargs: Any) -> None:
        """Set the vacuum cleaner to return to the dock."""
        await self._try_command("Unable to return home: %s", self._vacuum.raw_command, "set_charge", [1])

    async def async_locate(self, **kwargs: Any) -> None:
        """Locate the vacuum cleaner."""
        await self._try_command("Unable to locate: %s", self._vacuum.raw_command, "set_resetpos", [1])

    async def async_send_command(self, command: str, params: Optional[List[Any]] = None, **kwargs: Any) -> None:
        """Send raw command."""
        if isinstance(params, list) and len(params) == 1 and isinstance(params[0], str):
            if "[" in params[0] and "]" in params[0]:
                try:
                    params = ast.literal_eval(params[0])
                except Exception as exc:
                    _LOGGER.error("Error parsing params: %s", exc, exc_info=True)
            elif params[0].isnumeric():
                params[0] = int(params[0])
        await self._try_command("Unable to send command to the vacuum: %s", self._vacuum.raw_command, command, params)

    def update(self) -> None:
        """Fetch state from the device."""
        try:
            state = self._vacuum.raw_command("get_prop", ALL_PROPS)
            self.vacuum_state = dict(zip(ALL_PROPS, state))
            for prop in VACUUM_CARD_PROPS_REFERENCES.keys():
                self.vacuum_state[prop] = self.vacuum_state[VACUUM_CARD_PROPS_REFERENCES[prop]]
            self._available = True
            current_mode = int(self.vacuum_state["is_mop"])
            box_type = int(self.vacuum_state["box_type"])
            has_mop = bool(self.vacuum_state["mop_type"])

            new_mode: Optional[int] = None
            if box_type == 3:
                new_mode = 1 if has_mop else 0
            elif box_type == 2:
                new_mode = 2
            elif box_type == 1:
                new_mode = 0

            if new_mode is not None and new_mode != current_mode:
                _LOGGER.info("Adjusting mop mode from %s to %s", current_mode, new_mode)
                self._vacuum.raw_command("set_mop", [new_mode])
                # Do not recursively call update() to prevent infinite recursion.
        except OSError as exc:
            _LOGGER.error("Got OSError while fetching the state: %s", exc, exc_info=True)
        except DeviceException as exc:
            _LOGGER.warning("Got exception while fetching the state: %s", exc, exc_info=True)

	async def async_clean_zone(self, zone: List[List[float]], repeats: int = 1) -> None:
		"""Clean selected zone for the number of repeats indicated."""
		result: List[str] = []
		i = 0
		for z in zone:
			x1, y2, x2, y1 = z
			res = "_".join(str(x) for x in [i, 0, x1, y1, x1, y2, x2, y2, x2, y1])
			for _ in range(repeats):
				result.append(res)
				i += 1
		result = [str(i)] + result

		# Execute commands sequentially with error handling
		if not await self._try_command("Unable to upload map: %s", self._vacuum.raw_command, "set_uploadmap", [1]):
			_LOGGER.error("Failed to upload map. Aborting zone cleaning.")
			return

		if not await self._try_command("Unable to set zone: %s", self._vacuum.raw_command, "set_zone", result):
			_LOGGER.error("Failed to set cleaning zone. Aborting.")
			return

		if not await self._try_command("Unable to set cleaning mode: %s", self._vacuum.raw_command, "set_mode", [3, 1]):
			_LOGGER.error("Failed to set cleaning mode. Aborting.")

	async def async_clean_area(self, area: List[List[float]], repeats: int = 1) -> None:
		"""Clean selected area for the number of repeats indicated."""
		result: List[str] = []
		i = 0
		for a in area:
			x1, y1, x2, y2, x3, y3, x4, y4 = a
			res = "_".join(str(x) for x in [i, 0, x1, y1, x2, y2, x3, y3, x4, y4])
			for _ in range(repeats):
				result.append(res)
				i += 1
		result = [str(i)] + result

		# Execute commands sequentially with error handling
		if not await self._try_command("Unable to clean area (upload map): %s", self._vacuum.raw_command, "set_uploadmap", [1]):
			_LOGGER.error("Failed to upload map. Aborting area cleaning.")
			return

		if not await self._try_command("Unable to clean area (set zone): %s", self._vacuum.raw_command, "set_zone", result):
			_LOGGER.error("Failed to set cleaning zone. Aborting.")
			return

		if not await self._try_command("Unable to clean area (set mode): %s", self._vacuum.raw_command, "set_mode", [3, 1]):
			_LOGGER.error("Failed to set cleaning mode. Aborting.")

	async def async_clean_point(self, point: List[float]) -> None:
		"""Clean selected point."""
		x, y = point
		self._last_clean_point = point

		# Execute commands sequentially with error handling
		if not await self._try_command("Unable to upload map: %s", self._vacuum.raw_command, "set_uploadmap", [0]):
			_LOGGER.error("Failed to upload map. Aborting point cleaning.")
			return

		if not await self._try_command("Unable to clean point: %s", self._vacuum.raw_command, "set_pointclean", [1, x, y]):
			_LOGGER.error("Failed to set point clean mode. Aborting.")

	async def async_clean_segment(self, segments: Union[int, List[int]]) -> None:
		"""Clean selected segment(s) (rooms)."""
		if isinstance(segments, int):
			segments = [segments]

		# Execute commands sequentially with error handling
		if not await self._try_command("Unable to clean segments (upload map): %s", self._vacuum.raw_command, "set_uploadmap", [1]):
			_LOGGER.error("Failed to upload map. Aborting segment cleaning.")
			return

		if not await self._try_command(
			"Unable to clean segments (set mode with room): %s",
			self._vacuum.raw_command,
			"set_mode_withroom",
			[0, 1, len(segments)] + segments,
		):
			_LOGGER.error("Failed to set mode with room. Aborting.")

    async def async_update(self) -> None:
        """Asynchronously update the state of the entity."""
        await self.hass.async_add_executor_job(self.update)
