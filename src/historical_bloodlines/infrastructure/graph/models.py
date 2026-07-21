from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PersonBox:
    person_id: UUID
    lines: tuple[str, ...]
    name_line_count: int
    width: float
    height: float


@dataclass(slots=True)
class PartnerComponent:
    id: int
    person_ids: tuple[UUID, ...]
    person_boxes: dict[UUID, PersonBox]
    person_offsets: dict[UUID, float]
    width: float
    height: float
    min_source_row: int


@dataclass(frozen=True, slots=True)
class FamilyView:
    parent_ids: tuple[UUID, ...]
    child_ids: tuple[UUID, ...]
    parent_component_id: int
    source_offset: float


@dataclass(frozen=True, slots=True)
class PersonPosition:
    center_x: float
    top_y: float
    width: float
    height: float

    @property
    def left(self) -> float:
        return self.center_x - self.width / 2

    @property
    def right(self) -> float:
        return self.center_x + self.width / 2

    @property
    def bottom(self) -> float:
        return self.top_y + self.height
