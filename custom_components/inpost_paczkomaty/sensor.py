import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    tracked_lockers = entry.options.get("lockers", [])
    coordinator = entry.runtime_data

    _LOGGER.debug("Creating sensors for lockers %s", tracked_lockers)

    # Make sure coordinator has fetched first update
    await coordinator.async_config_entry_first_refresh()

    entities = []
    for locker_id in tracked_lockers:
        entities.append(ParcelLockerNumericSensor(coordinator, locker_id, "parcels_ready_count"))
        entities.append(ParcelLockerNumericSensor(coordinator, locker_id, "parcels_en_route_count"))
        entities.append(ParcelLockerStringSensor(coordinator, locker_id, "locker_id"))
        entities.append(ParcelLockerStringSensor(coordinator, locker_id, "locker_name"))
        entities.append(ParcelLockerJsonSensor(coordinator, locker_id, "parcels_json"))

    async_add_entities(entities)

class ParcelLockerDeviceSensor(CoordinatorEntity):
    """Base class for all parcel locker sensors."""

    def __init__(self, coordinator, locker_id, key):
        super().__init__(coordinator)
        self._locker_id = locker_id
        self._key = key

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._locker_id)},
            "name": f"Paczkomat {self._locker_id}",
            "manufacturer": "InPost",
        }

    @property
    def unique_id(self):
        # Must be unique per sensor (per locker + sensor type)
        return f"{DOMAIN}_{self._locker_id}_{self._key}"

    @property
    def name(self):
        return f"{self._locker_id} - {self._key.replace('_', ' ').title()}"

    @property
    def _sensor_data(self):
        """Return the latest value from coordinator data for this locker."""
        return self.coordinator.data.get(self._locker_id, {}).get(self._key)


class ParcelLockerNumericSensor(ParcelLockerDeviceSensor, SensorEntity):
    @property
    def native_value(self):
        return self._sensor_data or 0


class ParcelLockerStringSensor(ParcelLockerDeviceSensor, SensorEntity):
    @property
    def native_value(self):
        value = self._sensor_data
        return str(value) if value is not None else self._locker_id


class ParcelLockerJsonSensor(ParcelLockerDeviceSensor, SensorEntity):
    @property
    def native_value(self):
        return "ready"

    @property
    def extra_state_attributes(self):
        """Return full JSON info for the locker."""
        data = self.coordinator.data.get(self._locker_id, {})
        return data.get("parcels_json", {})

