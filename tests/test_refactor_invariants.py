from pathlib import Path

import pytest

from historical_bloodlines.application.dto import ParsedGenealogyRowDTO
from historical_bloodlines.application.services.assembler import GenealogyAssembler
from historical_bloodlines.domain import (
    Genealogy,
    MarriageRelation,
    ParentChildRelation,
    Person,
    SourcePersonKey,
)
from historical_bloodlines.infrastructure.graph import NetworkXGenealogyValidator


def parsed_row(sheet: str, row_number: int, name: str) -> ParsedGenealogyRowDTO:
    return ParsedGenealogyRowDTO(
        source_key=SourcePersonKey(sheet, row_number),
        name=name,
        dynasty=sheet,
        titles=(),
        reign_periods=(),
        children=(),
        spouses=(),
    )


def test_person_identity_is_deterministic() -> None:
    source_key = SourcePersonKey("Dynasty", 7)

    first = Person.create(source_key=source_key, name="Person")
    second = Person.create(source_key=source_key, name="Renamed person")

    assert first.id == second.id


def test_assembler_rejects_duplicate_source_keys() -> None:
    rows = (
        parsed_row("Dynasty", 1, "First"),
        parsed_row("Dynasty", 1, "Second"),
    )

    with pytest.raises(ValueError, match="Duplicate source key"):
        GenealogyAssembler().assemble(rows)


def test_reciprocal_marriage_declarations_deduplicate() -> None:
    first = Person.create(
        source_key=SourcePersonKey("Dynasty", 1),
        name="First",
    )
    second = Person.create(
        source_key=SourcePersonKey("Dynasty", 2),
        name="Second",
    )

    relations = {
        MarriageRelation.create(first.id, second.id, order_for_a=1),
        MarriageRelation.create(second.id, first.id, order_for_a=2),
    }

    assert len(relations) == 1


def test_validator_reports_readable_parent_cycle() -> None:
    genealogy = Genealogy()
    first = Person.create(
        source_key=SourcePersonKey("Dynasty", 1),
        name="First",
    )
    second = Person.create(
        source_key=SourcePersonKey("Dynasty", 2),
        name="Second",
    )
    genealogy.add_person(first)
    genealogy.add_person(second)
    genealogy.parent_child_relations.update(
        {
            ParentChildRelation(first.id, second.id),
            ParentChildRelation(second.id, first.id),
        }
    )

    with pytest.raises(ValueError, match="First"):
        NetworkXGenealogyValidator().validate(genealogy)


def test_repository_contains_example_workbook() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    assert (repository_root / "examples" / "input.example.xlsx").exists()
