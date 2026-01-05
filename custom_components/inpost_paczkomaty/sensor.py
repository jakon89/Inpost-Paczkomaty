import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfMass
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ENTRY_PHONE_NUMBER_CONFIG

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    tracked_lockers = entry.options.get("lockers", [])
    phone_number = entry.data.get(ENTRY_PHONE_NUMBER_CONFIG)

    coordinator = entry.runtime_data

    _LOGGER.debug("Creating sensors for lockers %s", tracked_lockers)

    # Make sure coordinator has fetched first update
    await coordinator.async_config_entry_first_refresh()

    # Parse lockers - handle both old format (list of codes) and new format (list of dicts)
    # Build a lookup map: code -> locker data
    lockers_map: dict[str, dict] = {}
    if tracked_lockers:
        if isinstance(tracked_lockers[0], dict):
            # New format: [{"code": "GDA117M", "description": "...", ...}]
            lockers_map = {locker["code"]: locker for locker in tracked_lockers}
        else:
            # Old format: ["GDA117M"] - backwards compatibility
            lockers_map = {code: {"code": code} for code in tracked_lockers}

    entities = []

    # Global sensors
    entities.append(AllParcelsCount(coordinator, phone_number))
    entities.append(EnRouteParcelsCount(coordinator, phone_number))
    entities.append(ReadyForPickupParcelsCount(coordinator, phone_number))

    # Carbon footprint sensors
    entities.append(TotalCarbonFootprintSensor(coordinator, phone_number))
    entities.append(TodayCarbonFootprintSensor(coordinator, phone_number))
    entities.append(CarbonFootprintStatisticsSensor(coordinator, phone_number))

    for locker_id, locker_data in lockers_map.items():
        # Per locker sensor
        entities.append(
            ParcelLockerNumericSensor(
                coordinator,
                phone_number,
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
                phone_number,
                locker_id,
                "ready_for_pickup_count",
                lambda data, locker_id: (
                    getattr(data.ready_for_pickup.get(locker_id), "count", 0)
                    if data.ready_for_pickup.get(locker_id) is not None
                    else 0
                ),
            )
        )
        entities.append(
            ParcelLockerIdSensor(
                coordinator,
                phone_number,
                locker_id,
                "locker_id",
                lambda data, locker_id: locker_id,
            )
        )
        entities.append(
            ParcelLockerDescriptionSensor(
                coordinator,
                phone_number,
                locker_id,
                "description",
                description=locker_data.get("description", ""),
            )
        )
        entities.append(
            ParcelLockerAddressSensor(
                coordinator,
                phone_number,
                locker_id,
                "address",
                city=locker_data.get("city", ""),
                street=locker_data.get("street", ""),
                building=locker_data.get("building", ""),
                zip_code=locker_data.get("zip_code", ""),
            )
        )
    async_add_entities(entities)


class AllParcelsCount(CoordinatorEntity, SensorEntity):
    """Sensor not bound to any device."""

    def __init__(self, coordinator, phone_number):
        super().__init__(coordinator)
        self._phone_number = phone_number
        self._attr_name = f"InPost {self._phone_number} all parcels count"

    @property
    def unique_id(self):
        return f"{DOMAIN}_{self._phone_number}_total_count"

    @property
    def device_info(self):
        # No device to place it under the integration only
        return None

    @property
    def native_value(self):
        return self.coordinator.data.all_count


class EnRouteParcelsCount(CoordinatorEntity, SensorEntity):
    """Sensor not bound to any device."""

    def __init__(self, coordinator, phone_number):
        super().__init__(coordinator)
        self._phone_number = phone_number
        self._attr_name = f"InPost {self._phone_number} en route parcels count"

    @property
    def unique_id(self):
        return f"{DOMAIN}_{self._phone_number}_en_route_count"

    @property
    def device_info(self):
        return None

    @property
    def native_value(self):
        return self.coordinator.data.en_route_count


class ReadyForPickupParcelsCount(CoordinatorEntity, SensorEntity):
    """Sensor not bound to any device."""

    def __init__(self, coordinator, phone_number):
        super().__init__(coordinator)
        self._phone_number = phone_number
        self._attr_name = f"InPost {self._phone_number} ready for pickup parcels count"

    @property
    def unique_id(self):
        return f"{DOMAIN}_{self._phone_number}_ready_for_pickup_count"

    @property
    def device_info(self):
        return None

    @property
    def native_value(self):
        return self.coordinator.data.ready_for_pickup_count


class ParcelLockerDeviceSensor(CoordinatorEntity):
    """Base class for all parcel locker sensors."""

    def __init__(self, coordinator, phone_number, locker_id, key, _value_fn=None):
        super().__init__(coordinator)
        self._phone_number = phone_number
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
        return f"{DOMAIN}_{self._phone_number}_{self._locker_id}_{self._key}"

    @property
    def name(self):
        return f"InPost {self._phone_number} {self._locker_id} {self._key.replace('_', ' ').title()}"

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


class ParcelLockerDescriptionSensor(ParcelLockerDeviceSensor, SensorEntity):
    """Sensor for parcel locker description."""

    def __init__(self, coordinator, phone_number, locker_id, key, description=""):
        super().__init__(coordinator, phone_number, locker_id, key)
        self._description = description

    @property
    def native_value(self):
        return self._description


class ParcelLockerAddressSensor(ParcelLockerDeviceSensor, SensorEntity):
    """Sensor for parcel locker address."""

    def __init__(
        self,
        coordinator,
        phone_number,
        locker_id,
        key,
        city="",
        street="",
        building="",
        zip_code="",
    ):
        super().__init__(coordinator, phone_number, locker_id, key)
        self._city = city
        self._street = street
        self._building = building
        self._zip_code = zip_code

    @property
    def native_value(self):
        return f"{self._city}, {self._zip_code}, {self._street} {self._building}"


# =============================================================================
# Carbon Footprint Sensors
# =============================================================================


class TotalCarbonFootprintSensor(CoordinatorEntity, SensorEntity):
    """Sensor for total cumulative carbon footprint from delivered parcels."""

    _attr_device_class = SensorDeviceClass.WEIGHT
    _attr_native_unit_of_measurement = UnitOfMass.KILOGRAMS
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:molecule-co2"

    def __init__(self, coordinator, phone_number):
        """Initialize the total carbon footprint sensor."""
        super().__init__(coordinator)
        self._phone_number = phone_number
        self._attr_name = f"InPost {self._phone_number} total carbon footprint"

    @property
    def unique_id(self):
        """Return unique ID for this sensor."""
        return f"{DOMAIN}_{self._phone_number}_total_carbon_footprint"

    @property
    def device_info(self):
        """Return device info."""
        return None

    @property
    def native_value(self) -> float:
        """Return the total carbon footprint in kg."""
        stats = self.coordinator.data.carbon_footprint_stats
        if stats:
            return stats.total_co2_kg
        return 0.0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        stats = self.coordinator.data.carbon_footprint_stats
        if stats:
            return {
                "total_parcels": stats.total_parcels,
                "total_co2_grams": stats.total_co2_grams,
                "unit_of_measurement": "kg CO₂",
            }
        return {}


class TodayCarbonFootprintSensor(CoordinatorEntity, SensorEntity):
    """Sensor for today's carbon footprint from delivered parcels."""

    _attr_device_class = SensorDeviceClass.WEIGHT
    _attr_native_unit_of_measurement = UnitOfMass.KILOGRAMS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:molecule-co2"

    def __init__(self, coordinator, phone_number):
        """Initialize today's carbon footprint sensor."""
        super().__init__(coordinator)
        self._phone_number = phone_number
        self._attr_name = f"InPost {self._phone_number} today carbon footprint"

    @property
    def unique_id(self):
        """Return unique ID for this sensor."""
        return f"{DOMAIN}_{self._phone_number}_today_carbon_footprint"

    @property
    def device_info(self):
        """Return device info."""
        return None

    @property
    def native_value(self) -> float:
        """Return today's carbon footprint in kg."""
        stats = self.coordinator.data.carbon_footprint_stats
        if not stats or not stats.daily_data:
            return 0.0

        today = datetime.now().strftime("%Y-%m-%d")
        for daily in stats.daily_data:
            if daily.date == today:
                return round(daily.value, 4)
        return 0.0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        stats = self.coordinator.data.carbon_footprint_stats
        if not stats or not stats.daily_data:
            return {}

        today = datetime.now().strftime("%Y-%m-%d")
        for daily in stats.daily_data:
            if daily.date == today:
                return {
                    "parcel_count": daily.parcel_count,
                    "date": daily.date,
                    "unit_of_measurement": "kg CO₂",
                }
        return {"parcel_count": 0, "date": today}


class CarbonFootprintStatisticsSensor(CoordinatorEntity, SensorEntity):
    """Sensor with daily carbon footprint statistics for graph visualization.

    This sensor provides daily breakdown data as attributes that can be used
    with ApexCharts, mini-graph-card, or other visualization cards.
    """

    _attr_icon = "mdi:chart-line"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfMass.KILOGRAMS

    def __init__(self, coordinator, phone_number):
        """Initialize the carbon footprint statistics sensor."""
        super().__init__(coordinator)
        self._phone_number = phone_number
        self._attr_name = f"InPost {self._phone_number} carbon footprint statistics"

    @property
    def unique_id(self):
        """Return unique ID for this sensor."""
        return f"{DOMAIN}_{self._phone_number}_carbon_footprint_statistics"

    @property
    def device_info(self):
        """Return device info."""
        return None

    @property
    def native_value(self) -> float:
        """Return the total carbon footprint as state value."""
        stats = self.coordinator.data.carbon_footprint_stats
        if stats:
            return stats.total_co2_kg
        return 0.0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return daily statistics and cumulative data for graphs.

        Attributes include:
        - daily_data: List of {date, value, parcel_count} for daily graphs
        - cumulative_data: List of {date, value} for cumulative graphs
        - total_co2_kg: Total carbon footprint
        - total_parcels: Total number of delivered parcels
        """
        stats = self.coordinator.data.carbon_footprint_stats
        if not stats:
            return {
                "daily_data": [],
                "cumulative_data": [],
                "total_co2_kg": 0.0,
                "total_parcels": 0,
            }

        # Build daily data list
        daily_data = [
            {
                "date": d.date,
                "value": round(d.value, 4),
                "parcel_count": d.parcel_count,
            }
            for d in stats.daily_data
        ]

        # Build cumulative data list
        cumulative_value = 0.0
        cumulative_data = []
        for d in stats.daily_data:
            cumulative_value += d.value
            cumulative_data.append(
                {
                    "date": d.date,
                    "value": round(cumulative_value, 4),
                }
            )

        return {
            "daily_data": daily_data,
            "cumulative_data": cumulative_data,
            "total_co2_kg": stats.total_co2_kg,
            "total_parcels": stats.total_parcels,
        }
