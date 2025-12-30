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
