from __future__ import annotations

from pathlib import Path

import pytest

from historical_bloodlines.application.dto import RawGenealogyRowDTO
from historical_bloodlines.application.services import GenealogyAssembler, GenealogyRowParser
from historical_bloodlines.config.render import load_render_config
from historical_bloodlines.infrastructure.graph import GraphvizGenealogyRenderer
from historical_bloodlines.infrastructure.graph.connector_routing import Rect, Segment, intersection
from historical_bloodlines.infrastructure.graph.models import PersonPosition
from historical_bloodlines.infrastructure.graph.readable_renderer import (
    _component_marriage_centers,
    _nonadjacent_marriage_lanes,
    _nonadjacent_marriage_segments,
)


# Production input that used to fail at Henry VIII / Jane Seymour -> Edward VI.
# Keep the source rows and all three true parent pairs; no layout hints needed.
ROWS = [
    ("Генрих VII", None, 1485, 1509, "Генрих VIII; Маргарита Тюдор", "Елизавета Йоркская"),
    ("Елизавета Йоркская", None, None, None, "Генрих VIII", "Генрих VII"),
    ("Генрих VIII", None, 1509, 1547, "Мария I; Елизавета I; Эдуард VI", "Екатерина Арагонская; Анна Болейн; Джейн Сеймур"),
    ("Маргарита Тюдор", None, None, None, "Яков V", "Яков IV"),
    ("Яков IV", "Король Шотландский (1488-1513)", None, None, "Яков V", "Маргарита Тюдор"),
    ("Екатерина Арагонская", None, None, None, "Мария I", "Генрих VIII"),
    ("Анна Болейн", None, None, None, "Елизавета I", "Генрих VIII"),
    ("Джейн Сеймур", None, None, None, "Эдуард VI", "Генрих VIII"),
    ("Эдуард VI", None, 1547, 1553, None, None),
    ("Мария I", None, 1553, 1558, None, "Филипп II"),
    ("Филипп II", "король Испанский (1556-1598)", None, None, None, "Мария I"),
    ("Елизавета I", None, 1558, 1603, None, None),
    ("Яков V", "король Шотландский (1513-1542)", None, None, "Мария Стюарт", None),
    ("Мария Стюарт", "королева Шотландская (1542-1567)", None, None, "Яков VI (I)", None),
    ("Яков VI (I)", "Король Англии и Ирландии (1603-1625); король Шотландии (1567–1625)", None, None, None, None),
]


@pytest.mark.parametrize("profile", ["default", "plus2", "plus3", "publisher-review"])
def test_three_marriages_keep_true_parent_pairs_and_clear_connectors(tmp_path, profile):
    parser = GenealogyRowParser()
    rows = (
        RawGenealogyRowDTO(
            source_sheet="Лист1", row_number=index,
            person_name=name, title_raw=title,
            reign_start_raw=start, reign_end_raw=end,
            children_raw=children, spouses_raw=spouses,
        )
        for index, (name, title, start, end, children, spouses) in enumerate(ROWS, 1)
    )
    genealogy = GenealogyAssembler().assemble(parser.parse(row) for row in rows)
    assert len(genealogy.persons) == 15
    assert not genealogy.warnings
    renderer = GraphvizGenealogyRenderer(load_render_config(Path(f"config/render.{profile}.yaml")))
    renderer.render(genealogy, tmp_path / "tudors.svg", title="Тюдоры и Стюарты")
    geometry = renderer.last_geometry
    assert geometry is not None
    assert geometry["issues"] == ()

    parent_pairs = {
        genealogy.persons[child_id].name: frozenset(genealogy.persons[parent_id].name for parent_id in family.parent_ids)
        for family in geometry["families"]
        for child_id in family.child_ids
    }
    assert parent_pairs["Мария I"] == {"Генрих VIII", "Екатерина Арагонская"}
    assert parent_pairs["Елизавета I"] == {"Генрих VIII", "Анна Болейн"}
    assert parent_pairs["Эдуард VI"] == {"Генрих VIII", "Джейн Сеймур"}
    assert geometry["partnership_segments"]
    for bridge in geometry["partnership_segments"]:
        for position in geometry["positions"].values():
            assert not Rect(position.left - 3, position.top_y - 3,
                            position.right + 3, position.bottom + 3).hit(bridge)
    henry = next(person for person in genealogy.persons.values() if person.name == "Генрих VIII")
    henry_position = geometry["positions"][henry.id]
    assert any(
        bridge.start[0] == pytest.approx(henry_position.right + 5)
        for bridge in geometry["partnership_segments"]
    )
    jane = next(person for person in genealogy.persons.values() if person.name == "Джейн Сеймур")
    pair = frozenset((henry.id, jane.id))
    sign_left, sign_right, sign_lower = geometry["marriage_connectors"][pair]
    assert sign_lower < henry_position.top_y
    family_route = next(route for route in geometry["routes"]
                        if frozenset(route.family.parent_ids) == pair)
    assert family_route.source[1] == pytest.approx(sign_lower)
    child_id = next(iter(family_route.family.child_ids))
    assert (sign_left + sign_right) / 2 == pytest.approx(
        geometry["positions"][child_id].center_x
    )
    for other_pair, (left, right, lower) in geometry["marriage_connectors"].items():
        if other_pair == pair:
            continue
        for bridge in geometry["partnership_segments"]:
            for y in (lower, lower - renderer.MARRIAGE_LINE_GAP):
                assert intersection(bridge, Segment(left, y, right, y)) is None
    assert (tmp_path / "tudors.svg").stat().st_size > 100


def test_three_marriage_gap_assignment_survives_translation_and_reflection():
    anchors = {"wife1": (0.0, 100.0), "henry": (130.0, 100.0),
               "wife2": (260.0, 100.0), "wife3": (390.0, 100.0)}
    pairs = {frozenset(("henry", wife)) for wife in ("wife1", "wife2", "wife3")}
    original = _component_marriage_centers(anchors, pairs)
    assert len(set(original.values())) == 3
    for scale, shift in ((1, 981.123456789), (-1, 0)):
        moved = _component_marriage_centers(
            {key: (scale * x + shift, width) for key, (x, width) in anchors.items()}, pairs,
        )
        for pair in pairs:
            assert moved[pair] == pytest.approx(scale * original[pair] + shift)


def test_closed_partnership_cycle_fails_instead_of_sharing_marriage_sign():
    anchors = {"a": (0.0, 100.0), "b": (130.0, 100.0), "c": (260.0, 100.0)}
    pairs = {frozenset(pair) for pair in (("a", "b"), ("b", "c"), ("a", "c"))}
    with pytest.raises(ValueError, match="distinct, label-free gaps"):
        _component_marriage_centers(anchors, pairs)


def test_unrelated_partnership_bridges_still_fail_closed():
    anchors = {name: (index * 130.0, 100.0) for index, name in enumerate("abcd")}
    pairs = {frozenset(pair) for pair in (("a", "c"), ("b", "d"), ("c", "d"))}
    centers = _component_marriage_centers(anchors, pairs)
    positions = {key: PersonPosition(x, 50.0, width, 30.0)
                 for key, (x, width) in anchors.items()}
    lanes = _nonadjacent_marriage_lanes(positions, pairs)
    connectors = {pair: (center - 6, center + 6, lanes.get(pair, 57.5) + 4)
                  for pair, center in centers.items()}
    with pytest.raises(ValueError, match="intersect"):
        _nonadjacent_marriage_segments(
            positions, pairs, connectors, attachment_offset=9.5, line_gap=4,
        )


@pytest.mark.parametrize("direction", [1, -1])
def test_raised_marriage_bridge_reaches_both_true_spouses_and_its_sign(direction):
    positions = {name: PersonPosition(direction * index * 130.0, 50.0, 100.0, 30.0)
                 for index, name in enumerate(("wife1", "husband", "wife2", "wife3"))}
    pairs = {frozenset(("husband", wife)) for wife in ("wife1", "wife2", "wife3")}
    centers = _component_marriage_centers(
        {key: (position.center_x, position.width) for key, position in positions.items()}, pairs,
    )
    lanes = _nonadjacent_marriage_lanes(positions, pairs)
    remote_pair = frozenset(("husband", "wife3"))
    assert set(lanes) == {remote_pair}
    connectors = {pair: (center - 6, center + 6, lanes.get(pair, 57.5) + 4)
                  for pair, center in centers.items()}
    bridges = _nonadjacent_marriage_segments(
        positions, pairs, connectors, attachment_offset=9.5, line_gap=4,
    )
    left, right = sorted((positions[person_id] for person_id in remote_pair),
                         key=lambda position: position.center_x)
    endpoints = {point for bridge in bridges for point in (bridge.start, bridge.end)}
    sign_left, sign_right, sign_lower = connectors[remote_pair]
    assert (left.right + 5, left.top_y + 9.5) in endpoints
    assert (right.left - 5, right.top_y + 9.5) in endpoints
    assert (sign_left, sign_lower - 2) in endpoints
    assert (sign_right, sign_lower - 2) in endpoints
    for bridge in bridges:
        for y in (sign_lower, sign_lower - 4):
            assert intersection(bridge, Segment(sign_left, y, sign_right, y)) is None
