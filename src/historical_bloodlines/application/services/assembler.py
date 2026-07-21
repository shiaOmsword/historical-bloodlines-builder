from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from uuid import UUID

from historical_bloodlines.application.dto import ParsedGenealogyRowDTO, PersonReferenceDTO
from historical_bloodlines.domain import (
    FamilyChildRelation,
    Genealogy,
    MarriageRelation,
    ParentChildRelation,
    Person,
    ReferenceWarning,
    SourcePersonKey,
)


class PersonReferenceResolver:
    def resolve(
        self,
        genealogy: Genealogy,
        reference: PersonReferenceDTO,
        *,
        dynasty: str,
        source_row: int,
        relation: str,
        source_person_id: UUID | None = None,
    ) -> Person | None:
        reference_key = genealogy.base_name(reference.name)
        excluded_ids: set[UUID] = set()
        if relation == "child" and source_person_id is not None:
            # A spouse with the same name as a later child is a common pattern
            # in dynastic tables. Partnerships are resolved before children, so
            # exclude current spouses from child candidates instead of linking
            # a person to their own partner as a descendant.
            for marriage in genealogy.marriages:
                if marriage.spouse_a_id == source_person_id:
                    excluded_ids.add(marriage.spouse_b_id)
                elif marriage.spouse_b_id == source_person_id:
                    excluded_ids.add(marriage.spouse_a_id)

        candidates = [
            person
            for person in genealogy.persons.values()
            if person.id != source_person_id
            and person.id not in excluded_ids
            and (person.dynasty or "").casefold() == dynasty.casefold()
            and self._name_matches(genealogy.base_name(person.name), reference_key)
        ]
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        qualifier = genealogy.normalize_name(reference.qualifier or "")
        raw_reference = genealogy.normalize_name(reference.raw_value or reference.name)

        def score(person: Person) -> tuple[int, int, int, int, int]:
            searchable = genealogy.normalize_name(
                " ".join((person.name, *person.titles))
            )
            qualifier_score = 0
            if qualifier:
                qualifier_tokens = set(qualifier.split())
                qualifier_score = sum(token in searchable for token in qualifier_tokens)

            raw_score = sum(token in searchable for token in raw_reference.split())
            exact_score = int(
                genealogy.normalize_name(person.name)
                == genealogy.normalize_name(reference.name)
            )
            row = person.source_key.row_number
            direction_score = int(relation == "child" and row > source_row)
            distance_score = -abs(row - source_row)
            return qualifier_score, exact_score, raw_score, direction_score, distance_score

        ranked = sorted(candidates, key=score, reverse=True)
        best_score = score(ranked[0])
        tied = [candidate for candidate in ranked if score(candidate) == best_score]
        if len(tied) == 1:
            return tied[0]

        # Stable fallback: workbook row order is the final disambiguator.
        return min(
            tied,
            key=lambda person: abs(person.source_key.row_number - source_row),
        )

    @staticmethod
    def _name_matches(candidate: str, reference: str) -> bool:
        if candidate == reference:
            return True
        candidate_tokens = candidate.split()
        reference_tokens = reference.split()
        if not candidate_tokens or not reference_tokens:
            return False
        shorter, longer = sorted((candidate_tokens, reference_tokens), key=len)
        return longer[: len(shorter)] == shorter


class GenealogyAssembler:
    def __init__(self, resolver: PersonReferenceResolver | None = None) -> None:
        self._resolver = resolver or PersonReferenceResolver()

    def assemble(self, rows: Iterable[ParsedGenealogyRowDTO]) -> Genealogy:
        parsed_rows = tuple(rows)
        genealogy = Genealogy()
        source_to_person: dict[SourcePersonKey, Person] = {}
        placeholder_index = 0
        placeholder_by_name: dict[tuple[str, str], Person] = {}

        for row in parsed_rows:
            if row.source_key in source_to_person:
                raise ValueError(
                    "Duplicate source key: "
                    f"{row.source_key.sheet_name!r}, row {row.source_key.row_number}"
                )
            person = Person.create(
                source_key=row.source_key,
                name=row.name,
                dynasty=row.dynasty,
                titles=row.titles,
                reign_periods=row.reign_periods,
            )
            genealogy.add_person(person)
            source_to_person[row.source_key] = person

        def placeholder(
            reference: PersonReferenceDTO,
            dynasty: str,
            *,
            source_key: SourcePersonKey,
            relation: str,
        ) -> Person:
            nonlocal placeholder_index
            display_name = reference.raw_value or reference.name
            key = (dynasty.casefold(), genealogy.normalize_name(display_name))
            if key in placeholder_by_name:
                return placeholder_by_name[key]

            existing = genealogy.find_by_name(display_name, dynasty=dynasty)
            if len(existing) == 1:
                return existing[0]

            placeholder_index += 1
            person = Person.create(
                source_key=SourcePersonKey(dynasty, 100000 + placeholder_index),
                name=display_name,
                dynasty=dynasty,
                is_placeholder=True,
            )
            genealogy.add_person(person)
            placeholder_by_name[key] = person
            genealogy.warnings.append(
                ReferenceWarning(
                    source_key=source_key,
                    relation=relation,
                    reference=display_name,
                )
            )
            return person

        # First resolve all partnerships. Children are intentionally not attached
        # to a spouse merely because that spouse is listed on the same row.
        # Co-parenthood is inferred only when both people independently declare
        # the same child. This avoids false family lines for second marriages.
        for row in parsed_rows:
            person = source_to_person[row.source_key]
            for spouse_ref in row.spouses:
                spouse = self._resolver.resolve(
                    genealogy,
                    spouse_ref,
                    dynasty=row.dynasty,
                    source_row=row.source_key.row_number,
                    relation="spouse",
                    source_person_id=person.id,
                )
                if spouse is None:
                    spouse = placeholder(
                        spouse_ref,
                        row.dynasty,
                        source_key=row.source_key,
                        relation="spouse",
                    )
                genealogy.marriages.add(
                    MarriageRelation.create(
                        person.id,
                        spouse.id,
                        order_for_a=spouse_ref.order,
                    )
                )

        declarations_by_child: dict[UUID, set[UUID]] = defaultdict(set)
        for row in parsed_rows:
            parent = source_to_person[row.source_key]
            for child_ref in row.children:
                child = self._resolver.resolve(
                    genealogy,
                    child_ref,
                    dynasty=row.dynasty,
                    source_row=row.source_key.row_number,
                    relation="child",
                    source_person_id=parent.id,
                )
                if child is None:
                    child = placeholder(
                        child_ref,
                        row.dynasty,
                        source_key=row.source_key,
                        relation="child",
                    )
                genealogy.parent_child_relations.add(
                    ParentChildRelation(parent_id=parent.id, child_id=child.id)
                )
                declarations_by_child[child.id].add(parent.id)

        married_pairs = {
            frozenset((marriage.spouse_a_id, marriage.spouse_b_id))
            for marriage in genealogy.marriages
        }
        for child_id, declaring_parents in declarations_by_child.items():
            parent_ids = sorted(
                declaring_parents,
                key=lambda person_id: genealogy.persons[person_id].source_key.row_number,
            )
            consumed: set[UUID] = set()

            # Prefer explicit married co-parents that both declare this child.
            for index, parent_a_id in enumerate(parent_ids):
                if parent_a_id in consumed:
                    continue
                for parent_b_id in parent_ids[index + 1 :]:
                    pair = frozenset((parent_a_id, parent_b_id))
                    if parent_b_id not in consumed and pair in married_pairs:
                        genealogy.family_child_relations.add(
                            FamilyChildRelation(parent_ids=pair, child_id=child_id)
                        )
                        consumed.update(pair)
                        break

            remaining = [
                parent_id for parent_id in parent_ids if parent_id not in consumed
            ]
            if len(remaining) == 2:
                # Two independent declarations are sufficient evidence of a
                # shared family even if the marriage column is empty.
                genealogy.family_child_relations.add(
                    FamilyChildRelation(
                        parent_ids=frozenset(remaining),
                        child_id=child_id,
                    )
                )
            else:
                for parent_id in remaining:
                    genealogy.family_child_relations.add(
                        FamilyChildRelation(
                            parent_ids=frozenset((parent_id,)),
                            child_id=child_id,
                        )
                    )

        return genealogy
