from __future__ import annotations

from historical_bloodlines.domain import (
    FamilyChildRelation,
    Genealogy,
    MarriageRelation,
    Person,
    PersonLayoutHint,
    SourcePersonKey,
)
from historical_bloodlines.infrastructure.graph import GraphvizGenealogyRenderer


def _person(
    genealogy: Genealogy,
    row: int,
    name: str,
    generation: int,
    order: int | None = None,
) -> Person:
    person = Person.create(
        source_key=SourcePersonKey("Late Valois publisher regression", row),
        name=name,
        layout_hint=PersonLayoutHint(generation, order),
    )
    genealogy.add_person(person)
    return person


def test_full_late_valois_publisher_topology_is_routable(tmp_path) -> None:
    """Mirror v6 `Капетинги и Валуа ч.2` relationship topology."""

    genealogy = Genealogy()

    john_ii = _person(genealogy, 3, "John II the Good", 1, 20)
    bonne = _person(genealogy, 4, "Bonne of Luxembourg", 1, 10)

    charles_v = _person(genealogy, 5, "Charles V the Wise", 2, 10)
    louis_anjou = _person(genealogy, 6, "Louis of Anjou", 2, 30)
    john_berry = _person(genealogy, 7, "John of Berry", 2, 20)
    philip_bold = _person(genealogy, 8, "Philip II the Bold", 2, 40)
    margaret = _person(genealogy, 9, "Margaret of Flanders", 2, 50)

    charles_vi = _person(genealogy, 10, "Charles VI", 3, 10)
    louis_orleans = _person(genealogy, 11, "Louis of Orleans", 3, 30)
    isabeau = _person(genealogy, 12, "Isabeau of Bavaria", 3, 20)

    charles_vii = _person(genealogy, 13, "Charles VII", 4)
    marie_anjou = _person(genealogy, 14, "Marie of Anjou", 4)
    catherine = _person(genealogy, 15, "Catherine of Valois", 4)
    henry_v = _person(genealogy, 16, "Henry V", 4)

    henry_vi = _person(genealogy, 17, "Henry VI", 5)
    louis_xi = _person(genealogy, 18, "Louis XI", 5)
    charles_viii = _person(genealogy, 19, "Charles VIII", 6)
    anne_brittany = _person(genealogy, 20, "Anne of Brittany", 6)

    john_fearless = _person(genealogy, 21, "John the Fearless", 4)
    philip_good = _person(genealogy, 22, "Philip III the Good", 5)
    charles_bold = _person(genealogy, 23, "Charles the Bold", 6)
    mary_burgundy = _person(genealogy, 24, "Mary of Burgundy", 7)
    maximilian = _person(genealogy, 25, "Maximilian I", 7)

    for first, second in (
        (john_ii, bonne),
        (philip_bold, margaret),
        (charles_vi, isabeau),
        (charles_vii, marie_anjou),
        (catherine, henry_v),
        (charles_viii, anne_brittany),
        (mary_burgundy, maximilian),
    ):
        genealogy.marriages.add(MarriageRelation.create(first.id, second.id))

    def child(parent: Person, descendant: Person) -> None:
        genealogy.family_child_relations.add(
            FamilyChildRelation(frozenset((parent.id,)), descendant.id)
        )

    for descendant in (charles_v, louis_anjou, john_berry, philip_bold):
        child(john_ii, descendant)

    child(charles_v, charles_vi)
    child(charles_v, louis_orleans)

    for parent in (philip_bold, margaret):
        child(parent, john_fearless)

    child(charles_vi, charles_vii)
    child(charles_vi, catherine)

    for parent in (charles_vii, marie_anjou):
        child(parent, louis_xi)

    for parent in (catherine, henry_v):
        child(parent, henry_vi)

    child(louis_xi, charles_viii)
    child(john_fearless, philip_good)
    child(philip_good, charles_bold)
    child(charles_bold, mary_burgundy)

    renderer = GraphvizGenealogyRenderer()
    renderer.render(
        genealogy,
        tmp_path / "late-valois.svg",
        title="Поздние Валуа",
    )

    assert renderer.last_geometry is not None
    positions = renderer.last_geometry["positions"]
    assert positions[charles_v.id].center_x < positions[john_berry.id].center_x
    assert positions[john_berry.id].center_x < positions[louis_anjou.id].center_x
    assert positions[louis_anjou.id].center_x < positions[philip_bold.id].center_x
    assert renderer.last_geometry["issues"] == ()
