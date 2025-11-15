# InPost Paczkomaty - Home Assistant Integration

Track [InPost](https://inpost.pl/) parcels sent to *Paczkomat®* (parcel lockers) and monitor the occupancy of your configured lockers.

> **Note:** Only **en route** or **available** parcels are tracked. Parcels that have already been picked up are ignored.

---

## How It Works

Home Assistant tracks your parcels using email updates from InPost. Importantly, **we do not access your inbox directly**.

Instead, you set up a **forwarding rule** in your email client to automatically forward all InPost notifications to a **private, dedicated email address** hosted via [Mailbay](https://mailbay.io).

Once an email is forwarded:

1. **Mailbay processes** the email, extracting the parcel data and storing it securely in a database.
2. **Home Assistant polls** the stored parcel data.
3. The integration **computes and displays** the status of your parcels, including which lockers are occupied and the current status of each parcel.

This approach ensures your email remains private while allowing automated parcel tracking in Home Assistant.

---

## Installation

### HACS

1. Ensure HACS is installed.
2. Add the custom repository.
3. Search for and install the **InPost Paczkomaty** integration.
4. Restart Home Assistant.
5. Go to **Integrations** and add the InPost Paczkomaty integration.
    - Setup parcel lockers you want to monitor. They can be updated later as well.
6. Copy your unique *forwarding email address* from the integration page:
![sample forwarding email](docs/img/integration-page.png "Title")

7. Setup *forwarding rule* in your email client to pass all Inpost emails to the *forwarding email address*
   - TODO

### Manual Installation

1. Download the latest release.
2. Unpack the release and copy the `custom_components/inpost_paczkomaty` directory into the `custom_components` folder of your Home Assistant installation.
3. Restart Home Assistant.
4. Go to **Integrations** and add the InPost Paczkomaty integration.

---

## Entities

For each tracked parcel locker, the integration creates the following entities:

| Platform        | Entity                                   | Description                                                                                   |
|-----------------|------------------------------------------|-----------------------------------------------------------------------------------------------|
| `sensor`        | `[LOCKER_ID]_locker_id`                  | ID of the locker                                                                              |
| `sensor`        | `[LOCKER_ID]_locker_name`                | Name of the locker                                                                            |
| `binary_sensor` | `[LOCKER_ID]_parcels_ready`             | `True` if any parcels are available for pickup in the locker                                   |
| `sensor`        | `[LOCKER_ID]_parcels_ready_count`       | Number of parcels available for pickup in the locker                                          |
| `binary_sensor` | `[LOCKER_ID]_parcels_en_route`          | `True` if any parcels are en route to the locker                                             |
| `sensor`        | `[LOCKER_ID]_parcels_en_route_count`    | Number of parcels currently en route to the locker                                           |
| `sensor`        | `[LOCKER_ID]_parcels_json`               | Detailed information about parcels en route or ready for pickup in the locker                |

---

### Sample `[LOCKER_ID]_parcels_json` Structure

```json
{
  "633300982462560127362573": {
    "parcel_id": "633300982462560127362573",
    "status": "delivered",
    "status_title": "Dostarczona",
    "status_description": "Podróż przesyłki od Nadawcy do Odbiorcy zakończyła się.",
    "locker_id": "LOCKER_ID",
    "locker_name": "Locker Name"
  }
}
```

#### Disclaimers

- Some parts of the codebase were *heavily* inspired aka copied from InPost-Air
- [Mailbay](https://mailbay.io), the service providing the necessary backend, is owned by this integration author - [jakon89](https://github.com/jakon89)
- The service is free for up to 500 emails per Home Assistant instance.