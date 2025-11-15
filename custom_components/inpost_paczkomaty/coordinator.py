"""InPost API data coordinator."""

import asyncio
import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MailbayInpostApi, MailbayHaInstanceLockersStatuses

_LOGGER = logging.getLogger(__name__)

class InpostDataCoordinator(DataUpdateCoordinator):
    def __init__(
            self, hass: HomeAssistant, mailbay_api_client: MailbayInpostApi
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Inpost Paczkomaty data coordinator",
            update_interval=timedelta(seconds=30),
        )
        self.mailbay_api_client = mailbay_api_client

    async def _async_update_data(self):
        try:
            async with asyncio.timeout(10):
                raw_data: MailbayHaInstanceLockersStatuses = await self.mailbay_api_client.get_lockers_statuses()

                en_route_by_locker = {}
                ready_by_locker = {}
                for parcel in raw_data.en_route:
                    en_route_by_locker.setdefault(parcel.locker.id, []).append(parcel)
                for parcel in raw_data.ready_to_pickup:
                    ready_by_locker.setdefault(parcel.locker.id, []).append(parcel)

                sensors_data = {}
                for locker_id, count in raw_data.locker_counts.items():
                    en_route = en_route_by_locker.get(locker_id, [])
                    ready = ready_by_locker.get(locker_id, [])

                    sensors_data[locker_id] = {
                        "parcels_ready": len(ready) > 0,
                        "parcels_ready_count": len(ready),
                        "parcels_en_route": len(en_route) > 0,
                        "parcels_en_route_count": len(en_route),
                        "locker_id": locker_id,
                        "locker_name": ready[0].locker.name if ready else (
                            en_route[0].locker.name if en_route else locker_id),
                        #Below elem is stored as extra_attributes in sensor so IT MUST be dict instead of list
                        #see ParcelLockerJsonSensor at sensor.py
                        "parcels_json": {
                            p.parcel_id: {
                                "status": p.status,
                                "parcel_id": p.parcel_id,
                                "status_title": p.status_title,
                                "status_description": p.status_description,
                            }
                            for p in ready + en_route
                        },
                    }

                return sensors_data

        except Exception as err:
            _LOGGER.error("Cannot read parcels from Mailbay API: %s", err)
            raise UpdateFailed("Error communicating with API") from err
