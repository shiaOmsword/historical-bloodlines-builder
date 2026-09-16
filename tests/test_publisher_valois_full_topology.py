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
        source_key=SourcePersonKey("Full Valois publisher regression", row),
        name=name,
        layout_hint=PersonLayoutHint(generation, order),
    )
    genealogy.add_person(person)
    return person


def _layout_diagnostic(renderer, genealogy: Genealogy) -> str:
    layout = renderer._layout
    components, component_by_person = layout._build_partner_components(genealogy)
    families = layout._build_families(genealogy, component_by_person, components)
    component_graph = layout._build_component_graph(
        components,
        families,
        component_by_person,
    )
    centers, levels = layout._place_components(
        genealogy,
        components,
        component_graph,
        component_by_person,
        families,
    )
    positions, _, _ = layout._place_people(components, centers, levels)

    rows = []
    for person_id, position in sorted(
        positions.items(),
        key=lambda item: (item[1].top_y, item[1].center_x),
    ):
        rows.append(
            (
                genealogy.persons[person_id].name,
                round(position.center_x, 1),
                round(position.top_y, 1),
                round(position.width, 1),
                round(position.height, 1),
                levels[component_by_person[person_id]] + 1,
            )
        )

    family_rows = []
    for family in sorted(
        families,
        key=lambda item: (
            min(positions[child_id].top_y for child_id in item.child_ids),
            centers[item.parent_component_id] + item.source_offset,
        ),
    ):
        family_rows.append(
            (
                tuple(genealogy.persons[item].name for item in family.parent_ids),
                tuple(genealogy.persons[item].name for item in family.child_ids),
                round(centers[family.parent_component_id] + family.source_offset, 1),
                tuple(round(positions[item].center_x, 1) for item in family.child_ids),
            )
        )

    reserved = tuple(
        genealogy.persons[person_id].name
        for person_id in getattr(layout, "reserved_corridors", ())
    )
    return f"positions={rows!r}\nfamilies={family_rows!r}\nreserved={reserved!r}"


def test_full_valois_publisher_topology_is_routable(tmp_path) -> None:
    """Mirror the publisher topology without artificial cousin-order locks.

    The requested Capetian sibling order remains hard in generations 1-3. The
    cross-branch marriages in generations 4-5 are automatic because their old
    numbers were layout scaffolding, not sibling birth-order requirements.
    """

    genealogy = Genealogy()

    philip_iii = _person(genealogy, 3, "Philip III", 1, 20)
    isabella_aragon = _person(genealogy, 4, "Isabella of Aragon", 1, 10)
    maria_brabant = _person(genealogy, 5, "Maria of Brabant", 1, 30)

    louis_evreux = _person(genealogy, 6, "Louis of Evreux", 2, 40)
    charles_bad = _person(genealogy, 7, "Charles II the Bad", 5)
    philip_iv = _person(genealogy, 8, "Philip IV", 2, 10)
    charles_valois = _person(genealogy, 9, "Charles of Valois", 2, 30)
    joan_navarre = _person(genealogy, 10, "Joan I of Navarre", 2, 20)

    louis_x = _person(genealogy, 11, "Louis X", 3, 30)
    philip_evreux = _person(genealogy, 12, "Philip III of Evreux", 4)
    joan_ii = _person(genealogy, 13, "Joan II of Navarre", 4)
    john_i = _person(genealogy, 14, "John I", 4)
    philip_v = _person(genealogy, 15, "Philip V", 3, 40)
    charles_iv = _person(genealogy, 16, "Charles IV", 3, 50)
    isabella_france = _person(genealogy, 17, "Isabella of France", 3, 60)
    edward_ii = _person(genealogy, 18, "Edward II", 3, 70)
    edward_iii = _person(genealogy, 19, "Edward III", 4)
    philip_vi = _person(genealogy, 20, "Philip VI of Valois", 3)
    john_ii = _person(genealogy, 21, "John II", 4)
    john_bohemia = _person(genealogy, 22, "John of Bohemia", 3)
    bonne = _person(genealogy, 23, "Bonne of Luxembourg", 4)

    for first, second in (
        (philip_iii, isabella_aragon),
        (philip_iii, maria_brabant),
        (philip_iv, joan_navarre),
        (philip_evreux, joan_ii),
        (isabella_france, edward_ii),
        (john_ii, bonne),
    ):
        genealogy.marriages.add(MarriageRelation.create(first.id, second.id))

    def child(parent: Person, descendant: Person) -> None:
        genealogy.family_child_relations.add(
            FamilyChildRelation(frozenset((parent.id,)), descendant.id)
        )

    for parent in (philip_iii, isabella_aragon):
        child(parent, philip_iv)
        child(parent, charles_valois)
    for parent in (philip_iii, maria_brabant):
        child(parent, louis_evreux)

    child(louis_evreux, philip_evreux)

    for descendant in (louis_x, philip_v, charles_iv, isabella_france):
        for parent in (philip_iv, joan_navarre):
            child(parent, descendant)

    child(louis_x, john_i)
    child(louis_x, joan_ii)

    for parent in (philip_evreux, joan_ii):
        child(parent, charles_bad)

    for parent in (isabella_france, edward_ii):
        child(parent, edward_iii)

    child(charles_valois, philip_vi)
    child(philip_vi, john_ii)
    child(john_bohemia, bonne)

    renderer = GraphvizGenealogyRenderer()
    try:
        renderer.render(
            genealogy,
            tmp_path / "full-valois.svg",
            title="Поздние Капетинги и ранние Валуа",
        )
    except ValueError as exc:
        raise AssertionError(f"{exc}\n{_layout_diagnostic(renderer, genealogy)}") from exc

    assert renderer.last_geometry is not None
    positions = renderer.last_geometry["positions"]
    assert positions[philip_iv.id].center_x < positions[charles_valois.id].center_x
    assert positions[louis_x.id].center_x < positions[philip_vi.id].center_x
    assert renderer.last_geometry["issues"] == ()
