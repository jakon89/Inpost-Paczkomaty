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

    # Global sensors
    entities.append(AllParcelsCount(coordinator, entry.entry_id))
    entities.append(EnRouteParcelsCount(coordinator, entry.entry_id))
    entities.append(ReadyForPickupParcelsCount(coordinator, entry.entry_id))

    for locker_id in tracked_lockers:
        # Per locker sensor
        entities.append(
            ParcelLockerNumericSensor(
                coordinator,
                locker_id,
                "en_route_count",
                lambda data, locker_id: (
                    getattr(data.en_route.get(locker_id), "count", 0)
                    if data.en_route.get(locker_id) is not None
                    else 0
                ),
            )
        )
        entities.append(
            ParcelLockerNumericSensor(
                coordinator,
                locker_id,
                "ready_for_pickup_count",
                lambda data, locker_id: (
                    getattr(data.ready_for_pickup.get(locker_id), "count", 0)
                    if data.en_route.get(locker_id) is not None
                    else 0
                ),
            )
        )
        entities.append(
            ParcelLockerIdSensor(
                coordinator, locker_id, "locker_id", lambda data, locker_id: locker_id
            )
        )

    async_add_entities(entities)


class AllParcelsCount(CoordinatorEntity, SensorEntity):
    """Sensor not bound to any device."""

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator)
        self._attr_name = "All InPost parcels count"

    @property
    def device_info(self):
        # No device to place it under the integration only
        return None

    @property
    def native_value(self):
        return self.coordinator.data.all_count


class EnRouteParcelsCount(CoordinatorEntity, SensorEntity):
    """Sensor not bound to any device."""

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator)
        self._attr_name = "En Route InPost parcels count"

    @property
    def device_info(self):
        return None

    @property
    def native_value(self):
        return self.coordinator.data.en_route_count


class ReadyForPickupParcelsCount(CoordinatorEntity, SensorEntity):
    """Sensor not bound to any device."""

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator)
        self._attr_name = "Ready For Pickup InPost parcels count"

    @property
    def device_info(self):
        return None

    @property
    def native_value(self):
        return self.coordinator.data.ready_for_pickup_count


class ParcelLockerDeviceSensor(CoordinatorEntity):
    """Base class for all parcel locker sensors."""

    def __init__(self, coordinator, locker_id, key, _value_fn=None):
        super().__init__(coordinator)
        self._locker_id = locker_id
        self._key = key
        self._value_fn = _value_fn

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
        return f"{self._key.replace('_', ' ').title()}"

    @property
    def _sensor_data(self):
        """Return the latest value from coordinator data for this locker."""

        data = self.coordinator.data

        if self._value_fn is not None:
            try:
                return self._value_fn(data, self._locker_id)
            except Exception as e:
                _LOGGER.error("Custom value_fn failed for %s: %s", self.unique_id, e)
                return None

        return None


class ParcelLockerNumericSensor(ParcelLockerDeviceSensor, SensorEntity):
    @property
    def native_value(self):
        return self._sensor_data or 0


class ParcelLockerIdSensor(ParcelLockerDeviceSensor, SensorEntity):
    @property
    def native_value(self):
        return str(self._locker_id)
