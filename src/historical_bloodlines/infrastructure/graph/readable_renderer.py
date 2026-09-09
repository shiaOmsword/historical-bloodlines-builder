from __future__ import annotations

import html
import math
from uuid import UUID

from historical_bloodlines.domain import Person
from historical_bloodlines.infrastructure.graph.labels import PersonLabelFormatter
from historical_bloodlines.infrastructure.graph.layout import (
    FixedGenealogyLayout,
    LayoutConfig,
)
from historical_bloodlines.infrastructure.graph.models import (
    FamilyView,
    PartnerComponent,
    PersonPosition,
)
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


class _ReadableFixedGenealogyLayout(FixedGenealogyLayout):
    """Manual-layout variant that avoids very large empty gaps inside a row.

    Explicit ``Порядок в поколении`` values are relative ordering constraints,
    not requests for arbitrary whitespace. During the iterative barycentric
    pass the desired centres of two neighbouring branches can nevertheless drift
    very far apart because each is pulled toward a different descendant chain.
    Capping only the *empty* gap keeps those rows compact without changing the
    requested left-to-right order or allowing boxes to overlap.
    """

    def __init__(
        self,
        config: LayoutConfig,
        labels: PersonLabelFormatter,
        *,
        max_component_gap: float,
    ) -> None:
        super().__init__(config, labels)
        self.MAX_COMPONENT_GAP = max(max_component_gap, self.COMPONENT_GAP)

    def _pack_layer(
        self,
        ordered_ids: list[int],
        desired: dict[int, float],
        centers: dict[int, float],
        components: dict[int, PartnerComponent],
    ) -> None:
        if not ordered_ids:
            return

        placed: dict[int, float] = {}
        previous_right: float | None = None
        for component_id in ordered_ids:
            width = components[component_id].width
            center = desired[component_id]
            if previous_right is not None:
                minimum_center = (
                    previous_right + self.COMPONENT_GAP + width / 2
                )
                maximum_center = (
                    previous_right + self.MAX_COMPONENT_GAP + width / 2
                )
                center = min(max(center, minimum_center), maximum_center)
            placed[component_id] = center
            previous_right = center + width / 2

        next_left: float | None = None
        for component_id in reversed(ordered_ids):
            width = components[component_id].width
            center = placed[component_id]
            if next_left is not None:
                maximum_center = next_left - self.COMPONENT_GAP - width / 2
                minimum_center = next_left - self.MAX_COMPONENT_GAP - width / 2
                center = max(min(center, maximum_center), minimum_center)
            placed[component_id] = center
            next_left = center - width / 2

        # Preserve the same translation strategy as the base layout. Only the
        # excessive internal whitespace is capped; the whole row is still moved
        # toward the median of its relationship constraints.
        shifts = [desired[item] - placed[item] for item in ordered_ids]
        shifts.sort()
        shift = shifts[len(shifts) // 2]
        for component_id in ordered_ids:
            centers[component_id] = placed[component_id] + shift


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
    MAX_COMPONENT_GAP = 46.0
    MAX_HORIZONTAL_STRETCH = 1.12

    # A one-child line does not need a visible dogleg merely because the child
    # label centre differs from the family source by a few points. If the source
    # still lands comfortably inside the label box, enter the top of that box at
    # the source X and keep the whole trunk vertical.
    SINGLE_CHILD_STRAIGHT_ENTRY_MAX = 12.0
    SINGLE_CHILD_ENTRY_MARGIN = 2.0

    def __init__(self) -> None:
        super().__init__()
        self._labels = _ReadablePersonLabelFormatter(
            font_size=self.FONT_SIZE,
            line_height=self.LINE_HEIGHT,
            text_padding_x=self.TEXT_PADDING_X,
            text_padding_y=self.TEXT_PADDING_Y,
            max_text_line=self.MAX_TEXT_LINE,
            max_name_line=self.MAX_NAME_LINE,
        )
        self._layout = _ReadableFixedGenealogyLayout(
            LayoutConfig(
                person_gap=self.PERSON_GAP,
                component_gap=self.COMPONENT_GAP,
                layer_gap=self.LAYER_GAP,
                page_margin_x=self.PAGE_MARGIN_X,
                page_margin_y=self.PAGE_MARGIN_Y,
                title_area=self.TITLE_AREA,
                single_child_snap_max=self.SINGLE_CHILD_SNAP_MAX,
                min_landscape_ratio=self.MIN_LANDSCAPE_RATIO,
                min_page_width=self.MIN_PAGE_WIDTH,
                max_horizontal_stretch=self.MAX_HORIZONTAL_STRETCH,
            ),
            self._labels,
            max_component_gap=self.MAX_COMPONENT_GAP,
        )
        self._single_child_source_x_by_child: dict[UUID, float] = {}

    def _family_bus_ys(
        self,
        families: tuple[FamilyView, ...],
        person_positions: dict[UUID, PersonPosition],
        marriage_connectors: dict[
            frozenset[UUID],
            tuple[float, float, float],
        ],
    ) -> dict[FamilyView, float]:
        result = super()._family_bus_ys(
            families,
            person_positions,
            marriage_connectors,
        )

        # Remember the exact X used by the source stem. _route_child_drop() is
        # called a little later and otherwise only knows the child centre. This
        # is the missing context that previously produced tiny horizontal bridge
        # segments in one-child families.
        source_x_by_child: dict[UUID, float] = {}
        for family in families:
            if len(family.child_ids) != 1:
                continue

            child_id = family.child_ids[0]
            if len(family.parent_ids) == 2:
                pair = frozenset(family.parent_ids)
                connector = marriage_connectors.get(pair)
                if connector is None:
                    source_x, _ = self._pair_fallback_midpoint(
                        family.parent_ids,
                        person_positions,
                    )
                else:
                    left_x, right_x, _ = connector
                    source_x = self._marriage_stem_x(left_x, right_x)
            else:
                source_x = person_positions[family.parent_ids[0]].center_x

            source_x_by_child[child_id] = source_x

        self._single_child_source_x_by_child = source_x_by_child
        return result

    def _route_child_drop(
        self,
        *,
        child_id: UUID,
        bus_y: float,
        person_positions: dict[UUID, PersonPosition],
    ) -> tuple[float, tuple[tuple[float, float, float, float], ...]]:
        """Prefer a single straight trunk for a visually near-aligned child.

        The previous readability patch removed collision-avoidance staircases,
        but the base renderer still inserted a short horizontal bus whenever a
        one-child source X and the child's centre X differed at all. That is the
        small 1-10 px "break" visible under several marriage signs and single
        parents in the review PDF.
        """

        child_position = person_positions[child_id]
        child_x = child_position.center_x
        child_top = child_position.top_y
        source_x = self._single_child_source_x_by_child.get(child_id)

        if source_x is not None:
            inside_box = (
                child_position.left + self.SINGLE_CHILD_ENTRY_MARGIN
                <= source_x
                <= child_position.right - self.SINGLE_CHILD_ENTRY_MARGIN
            )
            if (
                inside_box
                and abs(source_x - child_x)
                <= self.SINGLE_CHILD_STRAIGHT_ENTRY_MAX
            ):
                return source_x, (
                    (source_x, bus_y, source_x, child_top),
                )

        # For a genuinely displaced child keep the intentional orthogonal
        # connection. Labels remain opaque, so this straight drop can also pass
        # behind unrelated text without producing obstacle-avoidance staircases.
        return child_x, ((child_x, bus_y, child_x, child_top),)


__all__ = ["GraphvizGenealogyRenderer"]
