from historical_bloodlines.infrastructure.graph import GraphvizGenealogyRenderer
from historical_bloodlines.infrastructure.graph.labels import (
    PersonLabelFormatter,
    normalize_display_text,
)
from historical_bloodlines.domain import Person, ReignPeriod, SourcePersonKey


def test_display_text_uses_short_en_dash_for_all_dash_variants() -> None:
    assert normalize_display_text("1154-1189") == "1154–1189"
    assert normalize_display_text("1154—1189") == "1154–1189"
    assert normalize_display_text("1154–1189") == "1154–1189"


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


def test_renderer_keeps_approved_readability_typography() -> None:
    assert GraphvizGenealogyRenderer.LAYER_GAP == 30.0
    assert GraphvizGenealogyRenderer.LINE_HEIGHT == 15.0
    assert GraphvizGenealogyRenderer.MIN_PAGE_WIDTH == 560.0
    # The joint layout no longer stretches already-solved person centres.
    assert GraphvizGenealogyRenderer.MAX_HORIZONTAL_STRETCH == 1.0


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
        "Оттон I,",
        "(936–973, император",
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
        "Оттон I,",
        "(936–973, император",
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
        "Людовик,",
        "(король 1226–1270)",
    )


def test_textual_title_adds_comma_even_when_excel_name_has_none() -> None:
    labels = formatter()
    person = Person.create(
        source_key=SourcePersonKey("Dynasty", 4),
        name="Оттон I",
        titles=("Король Восточных Франков (936-973)",),
    )

    assert labels.measure(person).lines == (
        "Оттон I,",
        "король Восточных",
        "Франков (936–973)",
    )


def test_date_only_title_does_not_add_comma() -> None:
    labels = formatter()
    person = Person.create(
        source_key=SourcePersonKey("Dynasty", 5),
        name="Рюрик,",
        titles=("862-879",),
    )

    assert labels.measure(person).lines == ("Рюрик", "862–879")


def test_life_date_note_does_not_add_comma() -> None:
    labels = formatter()
    person = Person.create(
        source_key=SourcePersonKey("Dynasty", 6),
        name="Эдуард Чёрный принц,",
        titles=("ум. в 960",),
    )

    assert labels.measure(person).lines == (
        "Эдуард Чёрный",
        "принц",
        "ум. в 960",
    )


def test_existing_terminal_comma_is_removed_when_title_is_absent() -> None:
    labels = formatter()
    person = Person.create(
        source_key=SourcePersonKey("Dynasty", 7),
        name="Матильда,",
    )

    assert labels.measure(person).lines == ("Матильда",)


def test_marriage_connector_is_drawn_as_compact_equals_sign() -> None:
    renderer = GraphvizGenealogyRenderer()

    # These helpers remain part of the base renderer contract even though the
    # final readable renderer now plans relationship geometry in one pass.
    assert renderer._marriage_line_ys(100.0) == (98.0, 102.0)
    assert renderer._marriage_sign_xs(100.0, 160.0) == (124.0, 136.0)
    assert renderer._marriage_sign_xs(100.0, 108.0) == (100.0, 108.0)
