from dataclasses import dataclass
from typing import Dict, List


@dataclass
class HaInstance:
    ha_id: str
    secret: str


@dataclass
class ParcelItem:
    id: str
    phone: str | None
    code: str | None
    status: str
    status_desc: str


@dataclass
class Locker:
    locker_id: str
    count: int
    parcels: List[ParcelItem]


@dataclass
class ParcelsSummary:
    all_count: int
    ready_for_pickup_count: int
    en_route_count: int
    ready_for_pickup: Dict[str, Locker]
    en_route: Dict[str, Locker]


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
