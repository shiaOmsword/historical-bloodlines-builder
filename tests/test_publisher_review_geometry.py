from __future__ import annotations

import pytest

from historical_bloodlines.domain import (
    FamilyChildRelation,
    Genealogy,
    MarriageRelation,
    Person,
    PersonLayoutHint,
    SourcePersonKey,
)
from historical_bloodlines.infrastructure.graph import GraphvizGenealogyRenderer
from historical_bloodlines.infrastructure.graph.models import PersonPosition


def _person(
    genealogy: Genealogy,
    row: int,
    name: str,
    generation: int,
    order: int | None = None,
) -> Person:
    person = Person.create(
        source_key=SourcePersonKey("Publisher regression", row),
        name=name,
        layout_hint=PersonLayoutHint(generation, order),
    )
    genealogy.add_person(person)
    return person


def test_asymmetric_spouse_labels_keep_marriage_sign_visually_centered() -> None:
    renderer = GraphvizGenealogyRenderer()
    left = PersonPosition(center_x=100.0, top_y=0.0, width=140.0, height=30.0)
    right = PersonPosition(center_x=260.0, top_y=0.0, width=40.0, height=30.0)

    sign_left, sign_right = renderer._readable_marriage_sign_xs(left, right)

    # 180 is the preferred anchor midpoint; 181 is the nearest centre that
    # keeps the full 12 pt sign outside the wider label's 5 pt clearance.
    assert (sign_left + sign_right) / 2 == pytest.approx(181.0)
    assert sign_left >= left.right + 5.0 - 1e-6
    assert sign_right <= right.left - 5.0 + 1e-6


def test_single_parent_stays_on_axis_of_child_inside_marriage_component() -> None:
    genealogy = Genealogy()
    parent = _person(genealogy, 1, "Parent", 1)
    child = _person(genealogy, 2, "Child", 2)
    spouse = _person(genealogy, 3, "Spouse with a longer name", 2)
    genealogy.marriages.add(MarriageRelation.create(child.id, spouse.id))
    genealogy.family_child_relations.add(
        FamilyChildRelation(frozenset((parent.id,)), child.id)
    )

    renderer = GraphvizGenealogyRenderer()
    layout = renderer._layout
    components, by_person = layout._build_partner_components(genealogy)
    families = layout._build_families(genealogy, by_person, components)
    graph = layout._build_component_graph(components, families, by_person)
    centers, levels = layout._place_components(
        genealogy,
        components,
        graph,
        by_person,
        families,
    )
    positions, _, _ = layout._place_people(components, centers, levels)

    assert positions[parent.id].center_x == pytest.approx(
        positions[child.id].center_x,
        abs=1e-6,
    )


def test_two_parent_descendant_uses_same_axis_as_readable_marriage_sign(
    tmp_path,
) -> None:
    genealogy = Genealogy()
    first = _person(
        genealogy,
        1,
        "Parent with a substantially wider label",
        1,
    )
    second = _person(genealogy, 2, "B", 1)
    child = _person(genealogy, 3, "Only child", 2)
    genealogy.marriages.add(MarriageRelation.create(first.id, second.id))
    genealogy.family_child_relations.add(
        FamilyChildRelation(frozenset((first.id, second.id)), child.id)
    )

    renderer = GraphvizGenealogyRenderer()
    renderer.render(genealogy, tmp_path / "marriage-axis.svg", title="Marriage axis")

    assert renderer.last_geometry is not None
    route = renderer.last_geometry["routes"][0]
    assert route.source[0] == pytest.approx(route.targets[0][0], abs=1e-6)
    assert len(route.segments) == 1
    assert renderer.last_geometry["issues"] == ()


def test_luxembourg_two_spouses_and_descendant_branch_is_routable(
    tmp_path,
) -> None:
    """Mirror the publisher workbook around Sigismund's two marriages.

    Only the historically requested Wenceslaus-before-Sigismund order is manual.
    The partner component must orient itself so that Maria stays on the side of
    her own father, while Barbara remains adjacent to Sigismund for Elizabeth's
    descendant branch. That keeps both ancestry trees planar without inventing
    extra spreadsheet order hints for spouses.
    """

    genealogy = Genealogy()
    charles = _person(genealogy, 1, "Charles IV", 4)
    louis = _person(genealogy, 2, "Louis I of Anjou", 4)
    wenceslaus = _person(genealogy, 3, "Wenceslaus IV", 5, 10)
    sigismund = _person(genealogy, 4, "Sigismund", 5, 20)
    maria = _person(genealogy, 5, "Maria of Anjou", 5)
    barbara = _person(genealogy, 6, "Barbara of Cilli", 5)
    albert = _person(genealogy, 7, "Albert V of Habsburg", 6)
    elizabeth = _person(genealogy, 8, "Elizabeth", 6)
    ladislaus = _person(genealogy, 9, "Ladislaus Posthumous", 7)

    genealogy.marriages.add(MarriageRelation.create(sigismund.id, maria.id))
    genealogy.marriages.add(MarriageRelation.create(sigismund.id, barbara.id))
    genealogy.marriages.add(MarriageRelation.create(albert.id, elizabeth.id))

    genealogy.family_child_relations.add(
        FamilyChildRelation(frozenset((charles.id,)), wenceslaus.id)
    )
    genealogy.family_child_relations.add(
        FamilyChildRelation(frozenset((charles.id,)), sigismund.id)
    )
    genealogy.family_child_relations.add(
        FamilyChildRelation(frozenset((louis.id,)), maria.id)
    )
    # The workbook describes Elizabeth from both spouse rows. _build_families
    # must normalize these into the Sigismund/Barbara two-parent family.
    genealogy.family_child_relations.add(
        FamilyChildRelation(frozenset((sigismund.id,)), elizabeth.id)
    )
    genealogy.family_child_relations.add(
        FamilyChildRelation(frozenset((barbara.id,)), elizabeth.id)
    )
    genealogy.family_child_relations.add(
        FamilyChildRelation(frozenset((albert.id,)), ladislaus.id)
    )
    genealogy.family_child_relations.add(
        FamilyChildRelation(frozenset((elizabeth.id,)), ladislaus.id)
    )

    renderer = GraphvizGenealogyRenderer()
    renderer.render(genealogy, tmp_path / "luxembourg.svg", title="Luxembourg")

    assert renderer.last_geometry is not None
    positions = renderer.last_geometry["positions"]
    assert positions[wenceslaus.id].center_x < positions[sigismund.id].center_x
    assert positions[barbara.id].center_x < positions[sigismund.id].center_x
    assert positions[sigismund.id].center_x < positions[maria.id].center_x
    assert renderer.last_geometry["issues"] == ()
