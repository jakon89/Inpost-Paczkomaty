"""Data models for InPost Paczkomaty integration."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .exceptions import parse_api_error


@dataclass
class HaInstance:
    """Home Assistant instance configuration."""

    ha_id: str
    secret: str


@dataclass
class ParcelItem:
    """Individual parcel item information."""

    id: str
    phone: str | None
    code: str | None
    status: str
    status_desc: str


@dataclass
class Locker:
    """Parcel locker with parcels."""

    locker_id: str
    count: int
    parcels: List[ParcelItem]


@dataclass
class ParcelListItem:
    """Parcel item for list display in dashboard markdown card."""

    shipment_number: str
    sender_name: Optional[str]
    status: str
    status_description: str
    shipment_type: str  # "parcel" or "courier"
    parcel_size: Optional[str]
    ownership_status: Optional[str]

    # Receiver info
    phone_number: Optional[str]  # Receiver phone number (e.g., "+48987654321")

    # Pickup point info
    pickup_point_name: Optional[str]  # Locker name (e.g., "GDA117M") or None
    pickup_point_address: Optional[str]  # Formatted address
    pickup_point_description: Optional[str]  # Location description
    pickup_point_city: Optional[str]
    pickup_point_street: Optional[str]
    pickup_point_building: Optional[str]
    pickup_point_post_code: Optional[str]

    # Codes for pickup (only for READY_TO_PICKUP)
    open_code: Optional[str]
    qr_code: Optional[str]

    # Dates
    stored_date: Optional[str]  # ISO date string

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for sensor attributes."""
        return {
            "shipment_number": self.shipment_number,
            "sender_name": self.sender_name,
            "status": self.status,
            "status_description": self.status_description,
            "shipment_type": self.shipment_type,
            "parcel_size": self.parcel_size,
            "ownership_status": self.ownership_status,
            "phone_number": self.phone_number,
            "pickup_point_name": self.pickup_point_name,
            "pickup_point_address": self.pickup_point_address,
            "pickup_point_description": self.pickup_point_description,
            "pickup_point_city": self.pickup_point_city,
            "pickup_point_street": self.pickup_point_street,
            "pickup_point_building": self.pickup_point_building,
            "pickup_point_post_code": self.pickup_point_post_code,
            "open_code": self.open_code,
            "qr_code": self.qr_code,
            "stored_date": self.stored_date,
        }


@dataclass
class ParcelsSummary:
    """Summary of all parcels by status."""

    all_count: int
    ready_for_pickup_count: int
    en_route_count: int
    ready_for_pickup: Dict[str, Locker]
    en_route: Dict[str, Locker]
    carbon_footprint_stats: Optional["CarbonFootprintStats"] = None
    # Lists for dashboard display
    ready_for_pickup_list: List["ParcelListItem"] = field(default_factory=list)
    en_route_list: List["ParcelListItem"] = field(default_factory=list)


@dataclass
class InPostParcelLockerPointCoordinates:
    """
    Represents the coordinates of an InPost parcel locker point.

    Attributes:
        a (float): The latitude coordinate.
        o (float): The longitude coordinate.
    """

    a: float
    o: float


@dataclass
class InPostParcelLocker:
    """InPost parcel locker point details."""

    n: str  # Locker code
    t: int
    d: str  # Locker description (like "obiekt mieszkalny", "Przy sklepie Netto", etc.)
    m: str
    q: int | str
    f: str
    c: str  # Locker city (like "Gdańsk", "Warszawa", etc.)
    g: str  # Locker gmina (like "Gdańsk", "Warszawa", etc.)
    e: str  # Locker street (like "Wieżycka", "Rakoczego", etc.)
    r: str  # Locker province (like "pomorskie", "mazowieckie", etc.)
    o: str  # Locker zip code (like "80-180", "80-288", etc.)
    b: str  # Locker building number (like "8", "13", etc.)
    h: str
    i: str
    l: InPostParcelLockerPointCoordinates  # noqa: E741
    p: int
    s: int


@dataclass
class ParcelLockerListResponse:
    """Response from InPost parcel lockers public endpoint."""

    date: str
    page: int
    total_pages: int
    items: List[InPostParcelLocker]


# =============================================================================
# Official InPost API Response Models
# =============================================================================


@dataclass
class ApiLocation:
    """Geographic coordinates from InPost API."""

    latitude: float
    longitude: float


@dataclass
class ApiAddressDetails:
    """Address details from InPost API."""

    post_code: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    street: Optional[str] = None
    building_number: Optional[str] = None
    country: Optional[str] = None


@dataclass
class ApiPickUpPoint:
    """Pickup point details from InPost API."""

    name: str
    location: Optional[ApiLocation] = None
    location_description: Optional[str] = None
    opening_hours: Optional[str] = None
    address_details: Optional[ApiAddressDetails] = None
    image_url: Optional[str] = None
    point_type: Optional[str] = None
    easy_access_zone: bool = False
    type: Optional[List[str]] = None  # e.g., ["parcel_locker"]

    @property
    def is_parcel_locker(self) -> bool:
        """Check if this pickup point is a parcel locker."""
        if self.type:
            return "parcel_locker" in self.type
        return False


@dataclass
class ApiCarbonFootprint:
    """Carbon footprint data from InPost API."""

    box_machine_delivery: Optional[str] = None  # CO2 in kg for locker delivery
    address_delivery: Optional[str] = None  # CO2 in kg for courier delivery
    change_delivery_type_percent: Optional[str] = None
    change_delivery_type_value: Optional[str] = None
    redirection_url: Optional[str] = None


@dataclass
class ApiPhoneNumber:
    """Phone number with prefix from InPost API."""

    prefix: str
    value: str


@dataclass
class ApiReceiver:
    """Receiver information from InPost API."""

    name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[ApiPhoneNumber] = None


@dataclass
class ApiSender:
    """Sender information from InPost API."""

    name: Optional[str] = None


@dataclass
class ApiParcel:
    """Individual parcel from InPost API response."""

    shipment_number: str
    status: str
    shipment_type: str = "parcel"
    open_code: Optional[str] = None
    qr_code: Optional[str] = None
    stored_date: Optional[str] = None
    pick_up_date: Optional[str] = None
    pick_up_point: Optional[ApiPickUpPoint] = None
    status_group: Optional[str] = None
    parcel_size: Optional[str] = None
    receiver: Optional[ApiReceiver] = None
    sender: Optional[ApiSender] = None
    ownership_status: Optional[str] = None
    carbon_footprint: Optional[ApiCarbonFootprint] = None

    @property
    def locker_id(self) -> Optional[str]:
        """Get the locker ID from pickup point."""
        if self.pick_up_point:
            return self.pick_up_point.name
        return None

    @property
    def phone(self) -> Optional[str]:
        """Get receiver phone number."""
        if self.receiver and self.receiver.phone_number:
            return (
                f"{self.receiver.phone_number.prefix}{self.receiver.phone_number.value}"
            )
        return None

    @property
    def status_description(self) -> str:
        """Get human-readable status description."""
        status_map = {
            "READY_TO_PICKUP": "Gotowa do odbioru",
            "DELIVERED": "Doręczona",
            "OUT_FOR_DELIVERY": "Wydana do doręczenia",
            "ADOPTED_AT_SOURCE_BRANCH": "Przyjęta w Centrum Logistycznym",
            "SENT_FROM_SOURCE_BRANCH": "W trasie",
            "TAKEN_BY_COURIER": "Odebrana przez Kuriera",
            "CONFIRMED": "Przesyłka utworzona",
            "DISPATCHED_BY_SENDER": "Nadana",
            "PICKUP_REMINDER_SENT": "Przypomnienie o odbiorze",
        }
        return status_map.get(self.status, self.status)

    def to_parcel_item(self) -> "ParcelItem":
        """Convert to ParcelItem for ParcelsSummary."""
        return ParcelItem(
            id=self.shipment_number,
            phone=self.phone,
            code=self.open_code,
            status=self.status,
            status_desc=self.status_description,
        )

    def to_parcel_list_item(self) -> "ParcelListItem":
        """Convert to ParcelListItem for dashboard display."""
        # Build pickup point info
        pickup_name = None
        pickup_address = None
        pickup_description = None
        pickup_city = None
        pickup_street = None
        pickup_building = None
        pickup_post_code = None

        if self.pick_up_point:
            pickup_name = self.pick_up_point.name
            pickup_description = self.pick_up_point.location_description

            if self.pick_up_point.address_details:
                addr = self.pick_up_point.address_details
                pickup_city = addr.city
                pickup_street = addr.street
                pickup_building = addr.building_number
                pickup_post_code = addr.post_code

                # Build formatted address
                parts = []
                if addr.street:
                    street_part = addr.street
                    if addr.building_number:
                        street_part += f" {addr.building_number}"
                    parts.append(street_part)
                if addr.city:
                    city_part = addr.city
                    if addr.post_code:
                        city_part = f"{addr.post_code} {city_part}"
                    parts.append(city_part)
                pickup_address = ", ".join(parts)

        return ParcelListItem(
            shipment_number=self.shipment_number,
            sender_name=self.sender.name if self.sender else None,
            status=self.status,
            status_description=self.status_description,
            shipment_type=self.shipment_type,
            parcel_size=self.parcel_size,
            ownership_status=self.ownership_status,
            phone_number=self.phone,
            pickup_point_name=pickup_name,
            pickup_point_address=pickup_address,
            pickup_point_description=pickup_description,
            pickup_point_city=pickup_city,
            pickup_point_street=pickup_street,
            pickup_point_building=pickup_building,
            pickup_point_post_code=pickup_post_code,
            open_code=self.open_code,
            qr_code=self.qr_code,
            stored_date=self.stored_date,
        )

    @property
    def effective_carbon_footprint(self) -> Optional[float]:
        """Get the effective carbon footprint based on pickup point type.

        Uses boxMachineDelivery if pickup point is a parcel locker,
        otherwise uses addressDelivery.

        Returns:
            Carbon footprint value in kg CO2 or None if not available.
        """
        if not self.carbon_footprint:
            return None

        # Use parcel locker value if pickup point is a parcel locker
        if self.pick_up_point and self.pick_up_point.is_parcel_locker:
            value = self.carbon_footprint.box_machine_delivery
        else:
            value = self.carbon_footprint.address_delivery

        if value:
            try:
                return float(value)
            except (ValueError, TypeError):
                return None
        return None

    @property
    def pick_up_date_parsed(self) -> Optional[datetime]:
        """Parse pick_up_date string to datetime object.

        Returns:
            Datetime object or None if not available or invalid.
        """
        if not self.pick_up_date:
            return None
        try:
            # Handle ISO format with Z suffix
            date_str = self.pick_up_date.replace("Z", "+00:00")
            return datetime.fromisoformat(date_str)
        except (ValueError, TypeError):
            return None


@dataclass
class TrackedParcelsResponse:
    """Response from InPost tracked parcels API."""

    more: bool
    updated_until: Optional[str] = None
    parcels: List[ApiParcel] = field(default_factory=list)


@dataclass
class DailyCarbonFootprint:
    """Daily carbon footprint data for statistics."""

    date: str  # Date in YYYY-MM-DD format
    value: float  # CO2 in kg
    parcel_count: int  # Number of parcels for this day


@dataclass
class CarbonFootprintStats:
    """Carbon footprint statistics for parcels."""

    total_co2_kg: float  # Total cumulative CO2 in kg
    total_parcels: int  # Total number of delivered parcels counted
    daily_data: List[DailyCarbonFootprint]  # Daily breakdown for graphs

    @property
    def total_co2_grams(self) -> float:
        """Get total CO2 in grams."""
        return self.total_co2_kg * 1000


# Status constants for parcel filtering
EN_ROUTE_STATUSES = frozenset(
    {
        "OUT_FOR_DELIVERY",
        "ADOPTED_AT_SOURCE_BRANCH",
        "SENT_FROM_SOURCE_BRANCH",
        "TAKEN_BY_COURIER",
        "CONFIRMED",
        "DISPATCHED_BY_SENDER",
    }
)


# =============================================================================
# User Profile API Response Models
# =============================================================================


@dataclass
class ProfileDeliveryPoint:
    """Delivery point (parcel locker) from user profile."""

    name: str
    type: str = "PL"
    address_lines: List[str] = field(default_factory=list)
    active: bool = True
    preferred: bool = False

    @property
    def description(self) -> str:
        """Get formatted description from address lines."""
        return ", ".join(self.address_lines) if self.address_lines else ""


@dataclass
class ProfileDeliveryPoints:
    """Container for delivery points in profile."""

    items: List[ProfileDeliveryPoint] = field(default_factory=list)


@dataclass
class ProfileDeliveryAddressDetails:
    """Address details in profile delivery address."""

    post_code: Optional[str] = None
    city: Optional[str] = None
    street: Optional[str] = None
    building: Optional[str] = None
    flat: Optional[str] = None
    country_code: Optional[str] = None


@dataclass
class ProfileDeliveryAddressData:
    """Data for a delivery address."""

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    details: Optional[ProfileDeliveryAddressDetails] = None


@dataclass
class ProfileDeliveryAddress:
    """Delivery address from user profile."""

    id: str
    data: Optional[ProfileDeliveryAddressData] = None


@dataclass
class ProfileDeliveryAddresses:
    """Container for delivery addresses in profile."""

    items: List[ProfileDeliveryAddress] = field(default_factory=list)


@dataclass
class ProfileDelivery:
    """Delivery settings from user profile."""

    points: Optional[ProfileDeliveryPoints] = None
    addresses: Optional[ProfileDeliveryAddresses] = None
    preferred_delivery_type: Optional[str] = None


@dataclass
class ProfilePersonal:
    """Personal information from user profile."""

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    email_verified: bool = False
    phone_number: Optional[str] = None
    phone_number_prefix: Optional[str] = None


@dataclass
class UserProfile:
    """User profile from InPost API."""

    personal: Optional[ProfilePersonal] = None
    delivery: Optional[ProfileDelivery] = None
    shopping_active: bool = False

    def get_favorite_locker_codes(self) -> List[str]:
        """Get list of favorite/active locker codes.

        Returns:
            List of locker codes that are active, with preferred ones first.
        """
        if not self.delivery or not self.delivery.points:
            return []

        # Sort: preferred first, then active ones
        points = sorted(
            self.delivery.points.items,
            key=lambda p: (not p.preferred, not p.active),
        )

        return [p.name for p in points if p.active]


# =============================================================================
# Authentication Flow Models
# =============================================================================


@dataclass
class HttpResponse:
    """HTTP response data container."""

    body: Any
    status: int
    cookies: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)

    @property
    def is_error(self) -> bool:
        """Check if response indicates an error."""
        return self.status >= 400

    def raise_for_error(self) -> None:
        """
        Raise an InPostApiError if the response contains an error.

        Raises:
            InPostApiError: If the response body contains error information.
        """
        error = parse_api_error(self.body, self.status)
        if error:
            raise error


@dataclass
class AuthTokens:
    """OAuth2 token data container."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 7199
    scope: str = "openid"
    id_token: Optional[str] = None


@dataclass
class AuthStep:
    """Authentication step status container."""

    step: str
    raw_response: dict = field(default_factory=dict)

    @property
    def is_onboarded(self) -> bool:
        """Check if user has completed onboarding."""
        return self.step == "ONBOARDED"

    @property
    def requires_phone(self) -> bool:
        """Check if phone number input is required."""
        return self.step == "PROVIDE_PHONE_NUMBER_FOR_LOGIN"

    @property
    def requires_otp(self) -> bool:
        """Check if OTP code input is required."""
        return self.step == "PROVIDE_PHONE_CODE"

    @property
    def requires_email(self) -> tuple[bool, Optional[str]]:
        """Check if email confirmation is required and return hashed email."""
        if self.step == "PROVIDE_EXISTING_EMAIL_ADDRESS":
            return True, self.raw_response.get("hashedEmail", "")
        return False, None
