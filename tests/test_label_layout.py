from historical_bloodlines.infrastructure.graph.labels import PersonLabelFormatter
from historical_bloodlines.infrastructure.graph.renderer import GraphvizGenealogyRenderer


def formatter() -> PersonLabelFormatter:
    return PersonLabelFormatter(
        font_size=13.0,
        line_height=14.2,
        text_padding_x=4.0,
        text_padding_y=1.5,
        max_text_line=20,
        max_name_line=16,
    )


def test_person_names_wrap_more_aggressively_than_titles() -> None:
    labels = formatter()

    assert labels.wrap_name("Елизавета Вудвилл") == (
        "Елизавета",
        "Вудвилл",
    )
    assert labels.wrap("прочие супруги не перечислены") == (
        "прочие супруги не",
        "перечислены",
    )


def test_trailing_life_note_stays_with_surname() -> None:
    labels = formatter()

    assert labels.wrap_name("Ричард, герцог Йоркский (ум. 1483)") == (
        "Ричард, герцог",
        "Йоркский (ум. 1483)",
    )


def test_renderer_keeps_extra_vertical_air_between_generations() -> None:
    assert GraphvizGenealogyRenderer.LAYER_GAP == 30.0


def test_child_drop_detours_around_unrelated_person_box() -> None:
    from uuid import uuid4

    from historical_bloodlines.infrastructure.graph.models import PersonPosition

    renderer = GraphvizGenealogyRenderer()
    obstacle_id = uuid4()
    child_id = uuid4()
    positions = {
        obstacle_id: PersonPosition(
            center_x=100.0,
            top_y=100.0,
            width=80.0,
            height=60.0,
        ),
        child_id: PersonPosition(
            center_x=100.0,
            top_y=300.0,
            width=80.0,
            height=40.0,
        ),
    }

    connection_x, segments = renderer._route_child_drop(
        child_id=child_id,
        bus_y=50.0,
        person_positions=positions,
    )

    assert connection_x == 52.0
    assert segments == (
        (52.0, 50.0, 52.0, 291.0),
        (52.0, 291.0, 100.0, 291.0),
        (100.0, 291.0, 100.0, 300.0),
    )


def test_child_drop_stays_straight_when_corridor_is_clear() -> None:
    from uuid import uuid4

    from historical_bloodlines.infrastructure.graph.models import PersonPosition

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

    connection_x, segments = renderer._route_child_drop(
        child_id=child_id,
        bus_y=50.0,
        person_positions=positions,
    )

    assert connection_x == 100.0
    assert segments == ((100.0, 50.0, 100.0, 300.0),)
