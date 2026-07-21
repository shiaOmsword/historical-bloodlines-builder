from __future__ import annotations

import re
from dataclasses import dataclass, field
from uuid import UUID, uuid5

# Stable identities make generated SVG/PDF structure reproducible for the same
# workbook. SourcePersonKey remains the human-readable source identity.
PERSON_ID_NAMESPACE = UUID("0a8bce4f-23b7-4b48-a479-c3d15f2822db")


@dataclass(frozen=True, slots=True)
class SourcePersonKey:
    sheet_name: str
    row_number: int

    def __post_init__(self) -> None:
        if not self.sheet_name.strip():
            raise ValueError("Sheet name cannot be empty")
        if self.row_number < 1:
            raise ValueError("Row number must be positive")

    def stable_id(self) -> UUID:
        identity = f"{self.sheet_name.strip()}:{self.row_number}"
        return uuid5(PERSON_ID_NAMESPACE, identity)


@dataclass(frozen=True, slots=True)
class ReignPeriod:
    start_year: int
    end_year: int

    def __post_init__(self) -> None:
        if self.start_year > self.end_year:
            raise ValueError("Reign start year cannot be later than end year")


@dataclass(frozen=True, slots=True)
class ReferenceWarning:
    source_key: SourcePersonKey
    relation: str
    reference: str
    reason: str = "placeholder_created"

    def __str__(self) -> str:
        return (
            f"{self.source_key.sheet_name}:{self.source_key.row_number}: "
            f"created placeholder for {self.relation} reference "
            f"{self.reference!r}"
        )


@dataclass(slots=True)
class Person:
    id: UUID
    source_key: SourcePersonKey
    name: str
    dynasty: str | None = None
    titles: tuple[str, ...] = ()
    reign_periods: tuple[ReignPeriod, ...] = ()
    is_placeholder: bool = False

    @classmethod
    def create(
        cls,
        *,
        source_key: SourcePersonKey,
        name: str,
        dynasty: str | None = None,
        titles: tuple[str, ...] = (),
        reign_periods: tuple[ReignPeriod, ...] = (),
        is_placeholder: bool = False,
    ) -> Person:
        normalized_name = " ".join(name.split())
        if not normalized_name:
            raise ValueError("Person name cannot be empty")
        return cls(
            id=source_key.stable_id(),
            source_key=source_key,
            name=normalized_name,
            dynasty=dynasty.strip() if dynasty else None,
            titles=titles,
            reign_periods=reign_periods,
            is_placeholder=is_placeholder,
        )


@dataclass(frozen=True, slots=True)
class ParentChildRelation:
    parent_id: UUID
    child_id: UUID

    def __post_init__(self) -> None:
        if self.parent_id == self.child_id:
            raise ValueError("A person cannot be their own parent")


@dataclass(frozen=True, slots=True)
class FamilyChildRelation:
    parent_ids: frozenset[UUID]
    child_id: UUID

    def __post_init__(self) -> None:
        if not self.parent_ids:
            raise ValueError("Family must have at least one parent")
        if self.child_id in self.parent_ids:
            raise ValueError("A child cannot be their own parent")


@dataclass(frozen=True, slots=True)
class MarriageRelation:
    spouse_a_id: UUID
    spouse_b_id: UUID
    # Order is source metadata, not part of relation identity. Reciprocal
    # declarations therefore deduplicate to one marriage relation.
    order_for_a: int | None = field(default=None, compare=False, hash=False)
    order_for_b: int | None = field(default=None, compare=False, hash=False)

    def __post_init__(self) -> None:
        if self.spouse_a_id == self.spouse_b_id:
            raise ValueError("A person cannot marry themselves")

    @classmethod
    def create(
        cls,
        spouse_a_id: UUID,
        spouse_b_id: UUID,
        *,
        order_for_a: int | None = None,
        order_for_b: int | None = None,
    ) -> MarriageRelation:
        first, second = sorted((spouse_a_id, spouse_b_id), key=str)
        if first == spouse_a_id:
            return cls(first, second, order_for_a, order_for_b)
        return cls(first, second, order_for_b, order_for_a)


@dataclass(slots=True)
class Genealogy:
    persons: dict[UUID, Person] = field(default_factory=dict)
    parent_child_relations: set[ParentChildRelation] = field(default_factory=set)
    family_child_relations: set[FamilyChildRelation] = field(default_factory=set)
    marriages: set[MarriageRelation] = field(default_factory=set)
    warnings: list[ReferenceWarning] = field(default_factory=list)
    _ids_by_normalized_name: dict[str, list[UUID]] = field(default_factory=dict)

    @staticmethod
    def normalize_name(value: str) -> str:
        value = value.casefold().replace("ё", "е")
        value = re.sub(r"[«»\"'.,;:]+", " ", value)
        return " ".join(value.split())

    @staticmethod
    def base_name(value: str) -> str:
        without_qualifier = re.sub(r"\s*\([^()]*\)\s*$", "", value)
        without_nickname = re.sub(r'\s*[«\"]([^»\"]*)[»\"]\s*', " ", without_qualifier)
        return Genealogy.normalize_name(without_nickname)

    def add_person(self, person: Person) -> None:
        if person.id in self.persons:
            raise ValueError(
                "Duplicate person source key: "
                f"{person.source_key.sheet_name!r}, row {person.source_key.row_number}"
            )
        self.persons[person.id] = person
        for key in {self.normalize_name(person.name), self.base_name(person.name)}:
            self._ids_by_normalized_name.setdefault(key, []).append(person.id)

    def find_by_name(self, name: str, dynasty: str | None = None) -> list[Person]:
        ids = self._ids_by_normalized_name.get(self.normalize_name(name), [])
        persons = [self.persons[person_id] for person_id in dict.fromkeys(ids)]
        if dynasty is None:
            return persons
        dynasty_key = dynasty.casefold().strip()
        return [
            person
            for person in persons
            if (person.dynasty or "").casefold().strip() == dynasty_key
        ]
