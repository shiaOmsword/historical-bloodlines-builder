from historical_bloodlines.infrastructure.graph.labels import PersonLabelFormatter
from historical_bloodlines.infrastructure.graph.renderer import GraphvizGenealogyRenderer
from historical_bloodlines.domain import Person, ReignPeriod, SourcePersonKey


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


def test_titles_and_reign_dates_use_one_consistent_parenthetical_format() -> None:
    labels = formatter()
    person = Person.create(
        source_key=SourcePersonKey("Dynasty", 1),
        name="Оттон I",
        titles=("Король", "Император"),
        reign_periods=(ReignPeriod(936, 973), ReignPeriod(962)),
    )

    box = labels.measure(person)

    assert person.titles == ("король", "император")
    assert box.lines == (
        "Оттон I",
        "(936-973, император",
        "с 962)",
    )


def test_complete_reign_range_precedes_open_ended_qualification() -> None:
    labels = formatter()
    person = Person.create(
        source_key=SourcePersonKey("Dynasty", 2),
        name="Оттон I",
        titles=("Император", "Король"),
        reign_periods=(ReignPeriod(962), ReignPeriod(936, 973)),
    )

    assert labels.measure(person).lines == (
        "Оттон I",
        "(936-973, император",
        "с 962)",
    )


def test_single_complete_reign_keeps_its_title() -> None:
    labels = formatter()
    person = Person.create(
        source_key=SourcePersonKey("Dynasty", 3),
        name="Людовик",
        titles=("Король",),
        reign_periods=(ReignPeriod(1226, 1270),),
    )

    assert labels.measure(person).lines == (
        "Людовик",
        "(король 1226-1270)",
    )


def test_marriage_connector_is_drawn_as_compact_equals_sign() -> None:
    renderer = GraphvizGenealogyRenderer()

    assert renderer._marriage_line_ys(100.0) == (98.0, 102.0)
    assert renderer._marriage_sign_xs(100.0, 160.0) == (124.0, 136.0)
    assert renderer._marriage_sign_xs(100.0, 108.0) == (100.0, 108.0)


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
