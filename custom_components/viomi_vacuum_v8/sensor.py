"""Battery sensor for Viomi Vacuum V8."""

import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import PERCENTAGE

from .vacuum import DATA_KEY

_LOGGER = logging.getLogger(__name__)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Viomi Vacuum battery sensor."""
    if DATA_KEY not in hass.data:
        return

    entities = [
        ViomiBatterySensor(vacuum_entity)
        for vacuum_entity in hass.data[DATA_KEY].values()
    ]

    if entities:
        async_add_entities(entities, update_before_add=False)

class ViomiBatterySensor(SensorEntity):
    """Battery level sensor for Viomi Vacuum V8."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, vacuum_entity) -> None:
        """Initialize the battery sensor."""
        self._vacuum_entity = vacuum_entity
        self._attr_name = f"{vacuum_entity.name} Battery"
        self._attr_unique_id = f"{vacuum_entity.name}_battery"

    @property
    def available(self) -> bool:
        """Return True if the vacuum is reachable."""
        return self._vacuum_entity.available

    @property
    def native_value(self) -> int | None:
        """Return the battery level percentage."""
        if self._vacuum_entity.vacuum_state is not None:
            return self._vacuum_entity.vacuum_state.get("battary_life")
        return None
