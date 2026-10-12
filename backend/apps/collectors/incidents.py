"""Group collision events into incidents. Pure functions with no database.

Policy (GAP_SECONDS = 3):
- A collision event joins an open incident when it involves a car of that incident and comes
  at most GAP_SECONDS after the last event of that incident.
- AC sends one event for each car in a car-to-car contact. Both events share the cars, so
  they join the same incident. A repeated packet joins the same incident too.
- One event can join two open incidents (a car hits a car of each). Then the two incidents
  become one.
"""

from dataclasses import dataclass, field
from datetime import datetime

GAP_SECONDS = 3.0


@dataclass
class Collision:
    id: int
    at: datetime
    kind: str  # "collision_car" or "collision_env"
    car: str  # The GUID, or "car:<id>" when the GUID is not known.
    other: str | None
    speed_kmh: float
    x: float | None
    z: float | None
    attempt: int
    lap: int | None


@dataclass
class Incident:
    events: list[Collision] = field(default_factory=list)
    cars: set[str] = field(default_factory=set)

    @property
    def key(self) -> int:
        return self.events[0].id

    @property
    def last_at(self) -> datetime:
        return self.events[-1].at

    @property
    def kind(self) -> str:
        return "car" if any(e.kind == "collision_car" for e in self.events) else "env"

    @property
    def max_speed(self) -> float:
        return max(e.speed_kmh for e in self.events)

    def add(self, event: Collision) -> None:
        self.events.append(event)
        self.cars.add(event.car)
        if event.other:
            self.cars.add(event.other)


def group(collisions: list[Collision], gap_seconds: float = GAP_SECONDS) -> list[Incident]:
    incidents: list[Incident] = []
    open_: list[Incident] = []
    for event in sorted(collisions, key=lambda e: (e.at, e.id)):
        open_ = [i for i in open_ if (event.at - i.last_at).total_seconds() <= gap_seconds]
        cars = {event.car} | ({event.other} if event.other else set())
        matches = [i for i in open_ if i.cars & cars]
        if not matches:
            incident = Incident()
            incidents.append(incident)
            open_.append(incident)
        else:
            incident = matches[0]
            for other in matches[1:]:  # The event connects two incidents.
                for moved in other.events:
                    incident.add(moved)
                incident.events.sort(key=lambda e: (e.at, e.id))
                incidents.remove(other)
                open_.remove(other)
        incident.add(event)
    return incidents
