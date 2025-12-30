"""Data models for InPost Paczkomaty integration."""

from dataclasses import dataclass, field
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
class ParcelsSummary:
    """Summary of all parcels by status."""

    all_count: int
    ready_for_pickup_count: int
    en_route_count: int
    ready_for_pickup: Dict[str, Locker]
    en_route: Dict[str, Locker]


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

    n: str
    t: int
    d: str
    m: str
    q: int | str
    f: str
    c: str
    g: str
    e: str
    r: str
    o: str
    b: str
    h: str
    i: str
    l: InPostParcelLockerPointCoordinates  # noqa: E741
    p: int
    s: int


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


@dataclass
class TrackedParcelsResponse:
    """Response from InPost tracked parcels API."""

    updated_until: str
    more: bool
    parcels: List[ApiParcel] = field(default_factory=list)


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
