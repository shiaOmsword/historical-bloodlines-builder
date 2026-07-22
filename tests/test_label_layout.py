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
