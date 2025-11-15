from dataclasses import dataclass
from typing import Dict, List


@dataclass
class MailbayHaInstance:
    ha_id: str
    secret: str
    domain: str

@dataclass
class Locker:
    """Represents a locker."""
    id: str
    name: str

@dataclass
class Parcel:
    """Represents a parcel currently en route (or available for pickup)."""
    status: str
    locker: Locker
    parcel_id: str
    status_description: str
    status_title: str

@dataclass
class MailbayHaInstanceLockersStatuses:
    """Represents the main tracking response object."""
    locker_counts: Dict[str, int]
    en_route: List[Parcel]
    ready_to_pickup: List[Parcel]

@dataclass
class InPostParcelLockerPointCoordinates:
    """
    Represents the coordinates of an InPost Air point.

    Attributes:
        a (float): The latitude coordinate.
        o (float): The longitude coordinate.
    """

    a: float
    o: float


@dataclass
class InPostParcelLocker:
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
