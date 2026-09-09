from __future__ import annotations

from uuid import uuid4
import xml.etree.ElementTree as ET

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
from historical_bloodlines.infrastructure.graph.connector_routing import (
    OrthogonalConnectorRouter,
    Segment,
    intersection,
)
from historical_bloodlines.infrastructure.graph.constraint_solver import (
    constrained_positions,
)
from historical_bloodlines.infrastructure.graph.models import (
    FamilyView,
    PersonPosition,
)


def _person(
    genealogy: Genealogy,
    row: int,
    name: str,
    generation: int,
    order: int | None = None,
    titles: tuple[str, ...] = (),
) -> Person:
    person = Person.create(
        source_key=SourcePersonKey("Regression", row),
        name=name,
        titles=titles,
        layout_hint=PersonLayoutHint(generation, order),
    )
    genealogy.add_person(person)
    return person


def _family(
    genealogy: Genealogy,
    parents: tuple[Person, ...],
    children: tuple[Person, ...],
) -> None:
    for child in children:
        genealogy.family_child_relations.add(
            FamilyChildRelation(
                frozenset(parent.id for parent in parents),
                child.id,
            )
        )


def _marry(genealogy: Genealogy, first: Person, second: Person) -> None:
    genealogy.marriages.add(MarriageRelation.create(first.id, second.id))


def _prepare(genealogy: Genealogy):
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
    return renderer, components, by_person, families, positions


def test_solver_moves_linked_columns_without_violating_spacing() -> None:
    positions = constrained_positions(
        [0, 1, 2],
        [(0, 1, 0.0, 1.0), (1, 2, 0.0, 1.0)],
        [(0, 1, 70.0), (1, 2, 90.0)],
        {},
    )

    assert positions[1] - positions[0] >= 70.0 - 1e-5
    assert positions[2] - positions[1] >= 90.0 - 1e-5


def test_wider_known_parents_expand_marriage_gap_not_letters() -> None:
    genealogy = Genealogy()
    parent_a = _person(
        genealogy,
        1,
        "A long parent title",
        1,
        10,
        titles=("a broad ancestral label",),
    )
    parent_b = _person(
        genealogy,
        2,
        "B long parent title",
        1,
        20,
        titles=("another broad label",),
    )
    spouse_a = _person(genealogy, 3, "C", 2, 10)
    spouse_b = _person(genealogy, 4, "D", 2, 20)
    _marry(genealogy, spouse_a, spouse_b)
    _family(genealogy, (parent_a,), (spouse_a,))
    _family(genealogy, (parent_b,), (spouse_b,))

    renderer, _, _, _, positions = _prepare(genealogy)

    assert positions[parent_a.id].center_x == pytest.approx(
        positions[spouse_a.id].center_x
    )
    assert positions[parent_b.id].center_x == pytest.approx(
        positions[spouse_b.id].center_x
    )
    assert (
        positions[parent_a.id].right + renderer.COMPONENT_GAP
        <= positions[parent_b.id].left + 1e-5
    )
    assert len(renderer._layout.deferred_alignments) == 0


def test_consecutive_single_children_share_exact_axis_after_page_placement() -> None:
    genealogy = Genealogy()
    parent = _person(genealogy, 1, "Parent with a wider label", 1)
    child = _person(genealogy, 2, "Child", 2)
    grandchild = _person(genealogy, 3, "Grandchild", 3)
    _family(genealogy, (parent,), (child,))
    _family(genealogy, (child,), (grandchild,))

    _, _, _, _, positions = _prepare(genealogy)

    assert positions[parent.id].center_x == pytest.approx(
        positions[child.id].center_x,
        abs=1e-6,
    )
    assert positions[child.id].center_x == pytest.approx(
        positions[grandchild.id].center_x,
        abs=1e-6,
    )


def test_long_ancestry_link_reserves_empty_column_not_text_mask() -> None:
    genealogy = Genealogy()
    ancestor = _person(genealogy, 1, "Ancestor", 1, 20)
    other = _person(genealogy, 2, "Other ancestor", 1, 10)
    intervening = _person(genealogy, 3, "Intervening person", 2, 10)
    target = _person(genealogy, 4, "Target", 3, 20)
    _family(genealogy, (ancestor,), (target,))
    _family(genealogy, (other,), (intervening,))

    renderer, _, _, families, positions = _prepare(genealogy)
    router = OrthogonalConnectorRouter(positions, families, {})
    routes = router.plan()

    assert router.issues(routes) == []
    assert target.id in renderer._layout.reserved_corridors
    assert "BGCOLOR" not in renderer._labels.html_label(intervening)


def _crossed_generations(*, swapped: bool = False) -> Genealogy:
    genealogy = Genealogy()
    first_father = _person(
        genealogy,
        1,
        "First father",
        1,
        20 if swapped else 10,
    )
    second_father = _person(
        genealogy,
        2,
        "Second father",
        1,
        10 if swapped else 20,
    )
    first_child = _person(genealogy, 3, "First child", 2, 20)
    second_child = _person(genealogy, 4, "Second child", 2, 10)
    _family(genealogy, (first_father,), (first_child,))
    _family(genealogy, (second_father,), (second_child,))
    return genealogy


def test_incompatible_manual_order_is_rejected_instead_of_false_link(
    tmp_path,
) -> None:
    genealogy = _crossed_generations()

    with pytest.raises(ValueError, match="generation/order"):
        GraphvizGenealogyRenderer().render(
            genealogy,
            tmp_path / "bad.svg",
            title="Conflicting order",
        )

    assert not (tmp_path / "bad.svg").exists()


def test_order_only_fix_preserves_all_family_relations(tmp_path) -> None:
    genealogy = _crossed_generations(swapped=True)
    relations_before = set(genealogy.family_child_relations)
    renderer = GraphvizGenealogyRenderer()

    renderer.render(
        genealogy,
        tmp_path / "good.svg",
        title="Valid order",
    )

    assert genealogy.family_child_relations == relations_before
    assert renderer.last_geometry is not None
    assert renderer.last_geometry["issues"] == ()
    assert all(
        len(route.segments) == 1
        for route in renderer.last_geometry["routes"]
    )


def test_obstacle_route_does_not_cross_unrelated_label() -> None:
    parent_id = uuid4()
    obstacle_id = uuid4()
    child_id = uuid4()
    positions = {
        parent_id: PersonPosition(100.0, 0.0, 40.0, 30.0),
        obstacle_id: PersonPosition(100.0, 100.0, 80.0, 50.0),
        child_id: PersonPosition(100.0, 250.0, 50.0, 30.0),
    }
    family = FamilyView(
        parent_ids=(parent_id,),
        child_ids=(child_id,),
        parent_component_id=0,
        source_offset=0.0,
    )
    router = OrthogonalConnectorRouter(positions, (family,), {})

    routes = router.plan()

    assert routes[0].strategy == "obstacle_route"
    assert len(routes[0].segments) > 1
    assert router.issues(routes) == []


@pytest.mark.parametrize(
    ("first", "second", "kind"),
    [
        (Segment(0, 10, 20, 10), Segment(10, 0, 10, 20), "cross"),
        (Segment(0, 10, 20, 10), Segment(10, 10, 10, 20), "touch"),
        (Segment(0, 10, 20, 10), Segment(5, 10, 25, 10), "overlap"),
    ],
)
def test_foreign_intersections_detect_cross_t_junction_and_overlap(
    first: Segment,
    second: Segment,
    kind: str,
) -> None:
    assert intersection(first, second)[0] == kind


def test_segment_requires_orthogonal_geometry() -> None:
    with pytest.raises(ValueError, match="Non-orthogonal"):
        Segment(0, 0, 10, 10)


def test_svg_is_deterministic_and_has_no_masked_person_nodes(tmp_path) -> None:
    genealogy = _crossed_generations(swapped=True)
    renderer = GraphvizGenealogyRenderer()
    first = tmp_path / "a.svg"
    second = tmp_path / "b.svg"

    renderer.render(genealogy, first, title="Regression")
    renderer.render(genealogy, second, title="Regression")

    assert first.read_bytes() == second.read_bytes()
    root = ET.parse(first).getroot()
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    nodes = [
        item
        for item in root.findall(".//svg:g", namespace)
        if item.get("class") == "node"
    ]
    person_nodes = [
        node
        for node in nodes
        if node.find("svg:title", namespace).text.startswith("person_")
    ]
    assert len(person_nodes) == len(genealogy.persons)
    assert all(
        not node.findall("svg:polygon", namespace)
        for node in person_nodes
    )


def test_publisher_eps_remains_vector_export(tmp_path) -> None:
    genealogy = _crossed_generations(swapped=True)
    target = tmp_path / "proof.eps"

    GraphvizGenealogyRenderer().render(
        genealogy,
        target,
        title="EPS regression",
    )

    data = target.read_text(errors="replace")
    assert data.startswith("%!PS-Adobe")
    assert "%%BoundingBox:" in data
    body = data.split("%%EndProlog", 1)[1]
    assert "cairo_image" not in body
    assert "/ImageType" not in body


def test_approved_typography_is_not_changed() -> None:
    renderer = GraphvizGenealogyRenderer()

    assert (
        renderer.FONT_FAMILY,
        renderer.FONT_SIZE,
        renderer.LINE_HEIGHT,
    ) == ("Roboto", 13.2, 15.0)
    assert renderer._labels.NAME_FONT_FAMILY == "Roboto Medium"
