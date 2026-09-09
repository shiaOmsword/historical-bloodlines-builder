from __future__ import annotations

import html
import math
from uuid import UUID

from historical_bloodlines.domain import Person
from historical_bloodlines.infrastructure.graph.labels import PersonLabelFormatter
from historical_bloodlines.infrastructure.graph.models import PersonPosition
from historical_bloodlines.infrastructure.graph.renderer import (
    GraphvizGenealogyRenderer as _BaseGraphvizGenealogyRenderer,
)


class _ReadablePersonLabelFormatter(PersonLabelFormatter):
    """Render labels with stable line boxes and a print-friendly name weight.

    The regular renderer uses Graphviz ``BR`` elements and bold names. At the
    small effective point size of an A5 page, that combination can close the
    counters inside Cyrillic glyphs and Graphviz is free to choose its own line
    leading. Here every line gets a predictable row height and names use a
    medium face instead of full bold.

    The white table background is intentional. Relationship lines are emitted
    before nodes, so a long straight descendant line can pass *behind* an
    unrelated label without drawing through its text. That lets the renderer
    keep clean vertical trunks instead of the staircase-shaped detours that
    looked like broken lines in the publisher proofs.
    """

    NAME_FONT_FAMILY = "Roboto Medium"

    def html_label(self, person: Person) -> str:
        box = self.measure(person)
        row_height = max(1, int(math.ceil(self.line_height)))
        name_font = html.escape(self.NAME_FONT_FAMILY, quote=True)

        rows: list[str] = []
        for index, line in enumerate(box.lines):
            escaped = html.escape(line)
            if person.is_placeholder:
                escaped = f"<I>{escaped}</I>"
            elif index < box.name_line_count:
                escaped = f'<FONT FACE="{name_font}">{escaped}</FONT>'
            rows.append(
                '<TR><TD ALIGN="CENTER" VALIGN="MIDDLE" '
                f'HEIGHT="{row_height}">{escaped}</TD></TR>'
            )

        width = max(1, int(math.ceil(box.width)))
        height = max(1, int(math.ceil(box.height)))
        return (
            '<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" '
            'CELLPADDING="0" BGCOLOR="white" '
            f'WIDTH="{width}" HEIGHT="{height}">'
            f"{''.join(rows)}"
            "</TABLE>>"
        )


class GraphvizGenealogyRenderer(_BaseGraphvizGenealogyRenderer):
    """Publisher-oriented renderer tuned for compact, readable A5 tables."""

    # Roboto has a clearer small-size Cyrillic shape than the generic Sans
    # fallback while remaining neutral enough for book tables. Names are drawn
    # with Roboto Medium by _ReadablePersonLabelFormatter instead of full bold.
    FONT_FAMILY = "Roboto"
    FONT_SIZE = 13.2
    LINE_HEIGHT = 15.0
    TEXT_PADDING_Y = 2.0

    # The previous 760 pt minimum canvas was close to A4 landscape even though
    # the normal book output is A5 landscape (~595 pt wide). PdfBookComposer
    # therefore shrank even small genealogies before placing them on the page.
    # A smaller native canvas lets compact tables use the available A5 area and
    # materially increases their final effective text size.
    MIN_PAGE_WIDTH = 560.0
    PAGE_MARGIN_X = 18.0

    # Keep branches compact. In particular, do not stretch a short side branch
    # just to fill the landscape canvas; that was the source of several long
    # "shoulders" in the late Capetian table.
    PERSON_GAP = 34.0
    COMPONENT_GAP = 22.0
    MAX_HORIZONTAL_STRETCH = 1.12

    def __init__(self) -> None:
        super().__init__()
        # The layout created by the base constructor already uses the same
        # sizing constants. Only the HTML rendering strategy needs replacing.
        self._labels = _ReadablePersonLabelFormatter(
            font_size=self.FONT_SIZE,
            line_height=self.LINE_HEIGHT,
            text_padding_x=self.TEXT_PADDING_X,
            text_padding_y=self.TEXT_PADDING_Y,
            max_text_line=self.MAX_TEXT_LINE,
            max_name_line=self.MAX_NAME_LINE,
        )

    def _route_child_drop(
        self,
        *,
        child_id: UUID,
        bus_y: float,
        person_positions: dict[UUID, PersonPosition],
    ) -> tuple[float, tuple[tuple[float, float, float, float], ...]]:
        """Keep descendant trunks straight even when they cross another row.

        Person labels have an opaque white background and are rendered after
        edges, so unrelated labels safely mask the transit segment. This is
        visually cleaner than introducing a horizontal dogleg near the child.
        """

        child_position = person_positions[child_id]
        child_x = child_position.center_x
        child_top = child_position.top_y
        return child_x, ((child_x, bus_y, child_x, child_top),)


__all__ = ["GraphvizGenealogyRenderer"]
