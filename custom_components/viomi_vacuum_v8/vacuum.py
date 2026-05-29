"""Support for the Viomi Vacuum V8 (STYJ02YM) robot."""

import ast
import logging
from datetime import timedelta
from functools import partial

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST, CONF_NAME, CONF_TOKEN
from homeassistant.components.vacuum import (
    PLATFORM_SCHEMA,
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.helpers.discovery import async_load_platform
from miio import DeviceException, ViomiVacuum  # pylint: disable=import-error

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "Viomi Vacuum V8"
DOMAIN = "viomi_vacuum_v8"
DATA_KEY = "viomi_vacuum_v8"
SCAN_INTERVAL = timedelta(seconds=30)

# ---------------------------------------------------------------------------
# Platform schema
# ---------------------------------------------------------------------------

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_TOKEN): vol.All(cv.string, vol.Length(min=32, max=32)),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    },
    extra=vol.ALLOW_EXTRA,
)

# ---------------------------------------------------------------------------
# Service definitions
# ---------------------------------------------------------------------------

SERVICE_CLEAN_ZONE = "clean_zone"
SERVICE_CLEAN_AREA = "clean_area"
SERVICE_CLEAN_POINT = "clean_point"
SERVICE_CLEAN_SEGMENT = "clean_segment"
SERVICE_OBS_CLEAN_ZONE = "xiaomi_clean_zone"
SERVICE_OBS_CLEAN_POINT = "xiaomi_clean_point"

ATTR_ZONE = "zone"
ATTR_AREA = "area"
ATTR_REPEATS = "repeats"
ATTR_POINT = "point"
ATTR_SEGMENTS = "segments"

VACUUM_SERVICE_SCHEMA = vol.Schema(
    {vol.Optional(ATTR_ENTITY_ID): cv.comp_entity_ids}
)
SERVICE_SCHEMA_CLEAN_ZONE = VACUUM_SERVICE_SCHEMA.extend(
    {
        vol.Required(ATTR_ZONE): vol.All(
            list,
            [
                vol.ExactSequence(
                    [vol.Coerce(float), vol.Coerce(float),
                     vol.Coerce(float), vol.Coerce(float)]
                )
            ],
        ),
        vol.Required(ATTR_REPEATS): vol.All(
            vol.Coerce(int), vol.Clamp(min=1, max=3)
        ),
    }
)
SERVICE_SCHEMA_CLEAN_AREA = VACUUM_SERVICE_SCHEMA.extend(
    {
        vol.Required(ATTR_AREA): vol.All(
            list, [vol.ExactSequence([vol.Coerce(float)] * 8)]
        ),
        vol.Required(ATTR_REPEATS): vol.All(
            vol.Coerce(int), vol.Clamp(min=1, max=3)
        ),
    }
)
SERVICE_SCHEMA_CLEAN_POINT = VACUUM_SERVICE_SCHEMA.extend(
    {
        vol.Required(ATTR_POINT): vol.ExactSequence(
            [vol.Coerce(float), vol.Coerce(float)]
        )
    }
)
SERVICE_SCHEMA_CLEAN_SEGMENT = VACUUM_SERVICE_SCHEMA.extend(
    {vol.Required(ATTR_SEGMENTS): vol.Any(vol.Coerce(int), [vol.Coerce(int)])}
)

SERVICE_TO_METHOD = {
    SERVICE_CLEAN_ZONE: {
        "method": "async_clean_zone",
        "schema": SERVICE_SCHEMA_CLEAN_ZONE,
    },
    SERVICE_CLEAN_AREA: {
        "method": "async_clean_area",
        "schema": SERVICE_SCHEMA_CLEAN_AREA,
    },
    SERVICE_CLEAN_POINT: {
        "method": "async_clean_point",
        "schema": SERVICE_SCHEMA_CLEAN_POINT,
    },
    SERVICE_CLEAN_SEGMENT: {
        "method": "async_clean_segment",
        "schema": SERVICE_SCHEMA_CLEAN_SEGMENT,
    },
    # Legacy aliases (kept for backward compatibility)
    SERVICE_OBS_CLEAN_ZONE: {
        "method": "async_clean_zone",
        "schema": SERVICE_SCHEMA_CLEAN_ZONE,
    },
    SERVICE_OBS_CLEAN_POINT: {
        "method": "async_clean_point",
        "schema": SERVICE_SCHEMA_CLEAN_POINT,
    },
}

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FAN_SPEEDS: dict[str, int] = {
    "Silent": 0,
    "Standard": 1,
    "Medium": 2,
    "Turbo": 3,
}

SUPPORT_VIOMI = (
    VacuumEntityFeature.STATE
    | VacuumEntityFeature.PAUSE
    | VacuumEntityFeature.STOP
    | VacuumEntityFeature.RETURN_HOME
    | VacuumEntityFeature.FAN_SPEED
    | VacuumEntityFeature.LOCATE
    | VacuumEntityFeature.SEND_COMMAND
    | VacuumEntityFeature.START
)

STATE_CODE_TO_ACTIVITY: dict[int, VacuumActivity] = {
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

VACUUM_CARD_PROPS_REFERENCES: dict[str, str] = {
    "cleaned_area": "s_area",
    "cleaning_time": "s_time",
}

# ---------------------------------------------------------------------------
# Platform setup
# ---------------------------------------------------------------------------


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Viomi Vacuum V8 robot platform."""
    if DATA_KEY not in hass.data:
        hass.data[DATA_KEY] = {}

    host = config[CONF_HOST]
    token = config[CONF_TOKEN]
    name = config[CONF_NAME]

    _LOGGER.info("Initializing Viomi Vacuum at %s (token: %s…)", host, token[:5])
    vacuum_device = ViomiVacuum(host, token)
    entity = ViomiVacuumEntity(name, vacuum_device)
    hass.data[DATA_KEY][host] = entity

    async_add_entities([entity], update_before_add=False)

    # Load companion battery sensor
    hass.async_create_task(
        async_load_platform(hass, "sensor", DOMAIN, {}, config)
    )

    async def async_service_handler(service):
        """Dispatch service calls to the appropriate entity method."""
        method_info = SERVICE_TO_METHOD.get(service.service)
        if not method_info:
            _LOGGER.error("Unknown service: %s", service.service)
            return

        params = dict(service.data)
        entity_ids = params.pop(ATTR_ENTITY_ID, None)
        target_devices = [
            dev
            for dev in hass.data[DATA_KEY].values()
            if entity_ids is None or dev.entity_id in entity_ids
        ]

        for device in target_devices:
            method = getattr(device, method_info["method"], None)
            if method:
                await method(**params)

        for device in target_devices:
            await device.async_update_ha_state(True)

    for service_name, method_info in SERVICE_TO_METHOD.items():
        hass.services.async_register(
            DOMAIN,
            service_name,
            async_service_handler,
            schema=method_info["schema"],
        )


# ---------------------------------------------------------------------------
# Entity
# ---------------------------------------------------------------------------


class ViomiVacuumEntity(StateVacuumEntity):
    """Representation of a Viomi Vacuum V8 robot."""

    def __init__(self, name: str, vacuum: ViomiVacuum) -> None:
        """Initialize the vacuum entity."""
        self._attr_name = name
        self._vacuum = vacuum
        self._last_clean_point: list[float] | None = None
        self.vacuum_state: dict | None = None
        self._attr_available = False

    # ------------------------------------------------------------------
    # State properties
    # ------------------------------------------------------------------

    @property
    def activity(self) -> VacuumActivity | None:
        """Return the current vacuum activity derived from run_state."""
        if self.vacuum_state is None:
            return None
        try:
            state_code = int(self.vacuum_state.get("run_state", -1))
            return STATE_CODE_TO_ACTIVITY.get(state_code)
        except (ValueError, TypeError):
            _LOGGER.warning(
                "Unexpected run_state value: %s",
                self.vacuum_state.get("run_state"),
            )
            return None

    @property
    def fan_speed(self) -> str | None:
        """Return the current fan speed as a friendly name."""
        if self.vacuum_state is None:
            return None
        speed = self.vacuum_state.get("suction_grade")
        for label, value in FAN_SPEEDS.items():
            if value == speed:
                return label
        return str(speed)

    @property
    def fan_speed_list(self) -> list[str]:
        """Return supported fan speed names ordered by intensity."""
        return sorted(FAN_SPEEDS, key=FAN_SPEEDS.get)  # type: ignore[arg-type]

    @property
    def supported_features(self) -> VacuumEntityFeature:
        """Return supported features."""
        return SUPPORT_VIOMI

    @property
    def extra_state_attributes(self) -> dict:
        """Return device state attributes for the UI."""
        attrs: dict = {}
        if self.vacuum_state is None:
            return attrs
        attrs.update(self.vacuum_state)
        activity = self.activity
        attrs["status"] = (
            activity.value if activity
            else f"Unknown ({self.vacuum_state.get('run_state')})"
        )
        return attrs

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def _try_command(self, error_msg: str, func, *args, **kwargs) -> bool:
        """Execute a vacuum command; log and return False on failure."""
        try:
            await self.hass.async_add_executor_job(partial(func, *args, **kwargs))
            return True
        except DeviceException as exc:
            _LOGGER.error(error_msg, exc)
            return False

    async def async_start(self) -> None:
        """Start or resume cleaning."""
        mode = self.vacuum_state.get("mode")
        is_mop = self.vacuum_state.get("is_mop")

        if mode == 4 and self._last_clean_point is not None:
            method = "set_pointclean"
            param = [1, self._last_clean_point[0], self._last_clean_point[1]]
        elif mode == 3:
            method = "set_mode"
            param = [3, 1]
        else:
            action_mode = 2 if mode == 2 else (3 if is_mop == 2 else is_mop)
            method = "set_mode_withroom"
            param = [action_mode, 1, 0]

        await self._try_command(
            "Unable to start the vacuum: %s",
            self._vacuum.raw_command, method, param,
        )

    async def async_pause(self) -> None:
        """Pause the cleaning task."""
        mode = self.vacuum_state.get("mode")
        is_mop = self.vacuum_state.get("is_mop")

        if mode == 4 and self._last_clean_point is not None:
            method = "set_pointclean"
            param = [3, self._last_clean_point[0], self._last_clean_point[1]]
        elif mode == 3:
            method = "set_mode"
            param = [3, 3]
        else:
            action_mode = 2 if mode == 2 else (3 if is_mop == 2 else is_mop)
            method = "set_mode_withroom"
            param = [action_mode, 3, 0]

        await self._try_command(
            "Unable to pause the vacuum: %s",
            self._vacuum.raw_command, method, param,
        )

    async def async_stop(self, **kwargs) -> None:
        """Stop cleaning without returning to base."""
        mode = self.vacuum_state.get("mode")
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

        await self._try_command(
            "Unable to stop the vacuum: %s",
            self._vacuum.raw_command, method, param,
        )

    async def async_set_fan_speed(self, fan_speed: str, **kwargs) -> None:
        """Set the fan speed."""
        if isinstance(fan_speed, str) and fan_speed.capitalize() in FAN_SPEEDS:
            speed_value = FAN_SPEEDS[fan_speed.capitalize()]
        else:
            try:
                speed_value = int(fan_speed)
            except (ValueError, TypeError):
                _LOGGER.error(
                    "Invalid fan speed '%s'. Valid: %s", fan_speed, self.fan_speed_list
                )
                return

        await self._try_command(
            "Unable to set fan speed: %s",
            self._vacuum.raw_command, "set_suction", [speed_value],
        )

    async def async_return_to_base(self, **kwargs) -> None:
        """Return to dock."""
        await self._try_command(
            "Unable to return home: %s",
            self._vacuum.raw_command, "set_charge", [1],
        )

    async def async_locate(self, **kwargs) -> None:
        """Locate the vacuum (audible signal)."""
        await self._try_command(
            "Unable to locate vacuum: %s",
            self._vacuum.raw_command, "set_resetpos", [1],
        )

    async def async_send_command(self, command: str, params=None, **kwargs) -> None:
        """Send a raw miio command to the vacuum."""
        if isinstance(params, list) and len(params) == 1 and isinstance(params[0], str):
            param_str = params[0]
            if "[" in param_str and "]" in param_str:
                try:
                    params = ast.literal_eval(param_str)
                except (ValueError, SyntaxError) as exc:
                    _LOGGER.error("Error parsing parameters: %s", exc)
                    return
            elif param_str.isnumeric():
                params = [int(param_str)]

        await self._try_command(
            "Unable to send command: %s",
            self._vacuum.raw_command, command, params,
        )

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def update(self) -> None:
        """Fetch state from the device."""
        try:
            state = self._vacuum.raw_command("get_prop", ALL_PROPS)
            if not state or len(state) != len(ALL_PROPS):
                _LOGGER.warning("Incomplete state received: %s", state)
                self._attr_available = False
                return

            self.vacuum_state = dict(zip(ALL_PROPS, state))
            for ref_key, orig_key in VACUUM_CARD_PROPS_REFERENCES.items():
                self.vacuum_state[ref_key] = self.vacuum_state.get(orig_key)
            self._attr_available = True

            self._correct_mop_mode()

        except OSError as exc:
            _LOGGER.error("Connection error: %s", exc)
            self._attr_available = False
        except DeviceException as exc:
            _LOGGER.warning("Device error while fetching state: %s", exc)
            self._attr_available = False

    def _correct_mop_mode(self) -> None:
        """Auto-correct mop mode based on detected box_type and mop_type."""
        try:
            current_mode = int(self.vacuum_state.get("is_mop", 0))
            box_type = int(self.vacuum_state.get("box_type", 0))
            has_mop = bool(self.vacuum_state.get("mop_type"))
        except (ValueError, TypeError):
            return

        if box_type == 3:
            expected = 1 if has_mop else 0
        elif box_type == 2:
            expected = 2
        elif box_type == 1:
            expected = 0
        else:
            return

        if expected != current_mode:
            _LOGGER.info("Adjusting mop mode from %s to %s", current_mode, expected)
            try:
                self._vacuum.raw_command("set_mop", [expected])
            except DeviceException as exc:
                _LOGGER.warning("Failed to adjust mop mode: %s", exc)

    # ------------------------------------------------------------------
    # Custom services
    # ------------------------------------------------------------------

    async def async_clean_zone(self, zone, repeats=1) -> None:
        """Clean specified zone(s)."""
        result = []
        idx = 0
        for z in zone:
            x1, y2, x2, y1 = z
            res = "_".join(
                str(v) for v in [idx, 0, x1, y1, x1, y2, x2, y2, x2, y1]
            )
            for _ in range(repeats):
                result.append(res)
                idx += 1
        result = [idx] + result

        if await self._try_command(
            "Unable to upload map: %s", self._vacuum.raw_command, "set_uploadmap", [1]
        ):
            if await self._try_command(
                "Unable to set zone: %s", self._vacuum.raw_command, "set_zone", result
            ):
                await self._try_command(
                    "Unable to start zone clean: %s",
                    self._vacuum.raw_command, "set_mode", [3, 1],
                )

    async def async_clean_area(self, area, repeats=1) -> None:
        """Clean specified area(s) defined by 8 coordinates each."""
        result = []
        idx = 0
        for coords in area:
            coords = list(coords)
            if len(coords) != 8:
                _LOGGER.error(
                    "Area must have 8 coordinates, got %d: %s", len(coords), coords
                )
                return
            res = "_".join(str(v) for v in [idx, 0] + coords)
            for _ in range(repeats):
                result.append(res)
                idx += 1
        result = [idx] + result

        if await self._try_command(
            "Unable to upload map: %s", self._vacuum.raw_command, "set_uploadmap", [1]
        ):
            if await self._try_command(
                "Unable to set area: %s", self._vacuum.raw_command, "set_zone", result
            ):
                await self._try_command(
                    "Unable to start area clean: %s",
                    self._vacuum.raw_command, "set_mode", [3, 1],
                )

    async def async_clean_point(self, point) -> None:
        """Clean a specific point (spot cleaning)."""
        x, y = point
        self._last_clean_point = point
        if await self._try_command(
            "Unable to upload map: %s", self._vacuum.raw_command, "set_uploadmap", [0]
        ):
            await self._try_command(
                "Unable to start point clean: %s",
                self._vacuum.raw_command, "set_pointclean", [1, x, y],
            )

    async def async_clean_segment(self, segments) -> None:
        """Clean specified room segment(s)."""
        if isinstance(segments, int):
            segments = [segments]
        if await self._try_command(
            "Unable to upload map: %s", self._vacuum.raw_command, "set_uploadmap", [1]
        ):
            params = [0, 1, len(segments)] + segments
            await self._try_command(
                "Unable to start segment clean: %s",
                self._vacuum.raw_command, "set_mode_withroom", params,
            )
