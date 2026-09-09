from __future__ import annotations

from uuid import uuid4

from historical_bloodlines.infrastructure.graph import GraphvizGenealogyRenderer
from historical_bloodlines.infrastructure.graph.models import (
    PartnerComponent,
    PersonPosition,
)


def _component(component_id: int, width: float = 40.0) -> PartnerComponent:
    return PartnerComponent(
        id=component_id,
        person_ids=(),
        person_boxes={},
        person_offsets={},
        width=width,
        height=20.0,
        min_source_row=component_id,
    )


def test_readable_layout_caps_excessive_empty_gap_between_manual_components() -> None:
    renderer = GraphvizGenealogyRenderer()
    components = {
        1: _component(1),
        2: _component(2),
    }
    centers = {1: 0.0, 2: 0.0}
    desired = {1: 0.0, 2: 300.0}

    renderer._layout._pack_layer(
        [1, 2],
        desired,
        centers,
        components,
    )

    first_right = centers[1] + components[1].width / 2
    second_left = centers[2] - components[2].width / 2
    assert second_left - first_right == renderer.MAX_COMPONENT_GAP


def test_near_aligned_single_child_uses_parent_source_x_without_dogleg() -> None:
    renderer = GraphvizGenealogyRenderer()
    child_id = uuid4()
    positions = {
        child_id: PersonPosition(
            center_x=100.0,
            top_y=300.0,
            width=80.0,
            height=40.0,
        ),
    }
    renderer._single_child_source_x_by_child = {child_id: 106.0}

    connection_x, segments = renderer._route_child_drop(
        child_id=child_id,
        bus_y=80.0,
        person_positions=positions,
    )

    assert connection_x == 106.0
    assert segments == ((106.0, 80.0, 106.0, 300.0),)


def test_genuinely_displaced_single_child_keeps_orthogonal_fallback() -> None:
    renderer = GraphvizGenealogyRenderer()
    child_id = uuid4()
    positions = {
        child_id: PersonPosition(
            center_x=100.0,
            top_y=300.0,
            width=80.0,
            height=40.0,
        ),
    }
    renderer._single_child_source_x_by_child = {child_id: 130.0}

    connection_x, segments = renderer._route_child_drop(
        child_id=child_id,
        bus_y=80.0,
        person_positions=positions,
    )

    assert connection_x == 100.0
    assert segments == ((100.0, 80.0, 100.0, 300.0),)
