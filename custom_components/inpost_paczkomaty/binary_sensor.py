import logging

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)

from .const import ENTRY_PHONE_NUMBER_CONFIG
from .sensor import ParcelLockerDeviceSensor

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    tracked_lockers = entry.options.get("lockers", [])
    phone_number = entry.data.get(ENTRY_PHONE_NUMBER_CONFIG)

    coordinator = entry.runtime_data

    _LOGGER.debug("Creating binary sensors for lockers %s", tracked_lockers)

    await coordinator.async_config_entry_first_refresh()

    # Parse lockers - handle both old format (list of codes) and new format (list of dicts)
    locker_ids = []
    if tracked_lockers:
        if isinstance(tracked_lockers[0], dict):
            # New format: [{"code": "GDA117M", ...}]
            locker_ids = [locker["code"] for locker in tracked_lockers]
        else:
            # Old format: ["GDA117M"] - backwards compatibility
            locker_ids = tracked_lockers

    entities = []
    for locker_id in locker_ids:
        entities.append(
            ParcelLockerBinarySensor(
                coordinator,
                phone_number,
                locker_id,
                "en_route",
                lambda data, locker_id: getattr(
                    data.en_route.get(locker_id), "count", 0
                )
                > 0,
            )
        )
        entities.append(
            ParcelLockerBinarySensor(
                coordinator,
                phone_number,
                locker_id,
                "ready_for_pickup_count",
                lambda data, locker_id: getattr(
                    data.ready_for_pickup.get(locker_id), "count", 0
                )
                > 0,
            )
        )

    async_add_entities(entities)


class ParcelLockerBinarySensor(BinarySensorEntity, ParcelLockerDeviceSensor):
    @property
    def is_on(self) -> bool:
        return bool(self._sensor_data)

    @property
    def device_class(self):
        return BinarySensorDeviceClass.OCCUPANCY
