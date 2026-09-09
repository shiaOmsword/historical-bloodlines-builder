from __future__ import annotations

from dataclasses import replace
import html
import math
from pathlib import Path

from graphviz import Graph

from historical_bloodlines.domain import Genealogy, Person
from historical_bloodlines.infrastructure.graph.connector_routing import (
    OrthogonalConnectorRouter,
    RoutingConflict,
    Segment,
)
from historical_bloodlines.infrastructure.graph.labels import (
    PersonLabelFormatter,
    normalize_display_text,
)
from historical_bloodlines.infrastructure.graph.layout import LayoutConfig
from historical_bloodlines.infrastructure.graph.orthogonal_layout import (
    OrthogonalGenealogyLayout,
)
from historical_bloodlines.infrastructure.graph.renderer import (
    GraphvizGenealogyRenderer as _BaseGraphvizGenealogyRenderer,
)


class _ReadablePersonLabelFormatter(PersonLabelFormatter):
    """Keep the approved typeface and leading without hiding connectors."""

    NAME_FONT_FAMILY = "Roboto Medium"

    def html_label(self, person: Person) -> str:
        box = self.measure(person)
        rows: list[str] = []
        name_font = html.escape(self.NAME_FONT_FAMILY, quote=True)
        row_height = max(1, int(math.ceil(self.line_height)))

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
        # Deliberately no BGCOLOR. A label may not conceal an invalid line.
        return (
            '<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" '
            f'CELLPADDING="0" WIDTH="{width}" HEIGHT="{height}">'
            f"{''.join(rows)}</TABLE>>"
        )


class GraphvizGenealogyRenderer(_BaseGraphvizGenealogyRenderer):
    """Readable genealogy renderer with validated orthogonal connectors.

    Horizontal positions are solved jointly across generations. Relationship
    routes are then validated against labels and other family routes before any
    Graphviz artifact is written. If the workbook's explicit generation/order
    constraints make a clean route impossible, rendering fails closed instead
    of publishing an ambiguous crossing.
    """

    FONT_FAMILY = "Roboto"
    FONT_SIZE = 13.2
    LINE_HEIGHT = 15.0
    TEXT_PADDING_Y = 2.0

    MIN_PAGE_WIDTH = 560.0
    PAGE_MARGIN_X = 18.0
    PERSON_GAP = 34.0
    COMPONENT_GAP = 22.0

    # Never stretch solved person centres after the constraint pass. Stretching
    # coordinates while keeping label widths fixed shifts marriage centres away
    # from their exact descendant axes and recreates tiny G-shaped doglegs.
    MAX_HORIZONTAL_STRETCH = 1.0

    def __init__(self) -> None:
        self._labels = _ReadablePersonLabelFormatter(
            font_size=self.FONT_SIZE,
            line_height=self.LINE_HEIGHT,
            text_padding_x=self.TEXT_PADDING_X,
            text_padding_y=self.TEXT_PADDING_Y,
            max_text_line=self.MAX_TEXT_LINE,
            max_name_line=self.MAX_NAME_LINE,
        )
        self._layout = OrthogonalGenealogyLayout(
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
        )
        self.last_geometry: dict[str, object] | None = None

    def render(
        self,
        genealogy: Genealogy,
        output_path: Path,
        *,
        title: str,
    ) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_format = output_path.suffix.lstrip(".").casefold()
        if output_format not in {"pdf", "svg", "png", "eps"}:
            raise ValueError("Output format must be pdf, svg, png or eps")

        components, component_by_person = self._layout._build_partner_components(
            genealogy
        )
        families = self._layout._build_families(
            genealogy,
            component_by_person,
            components,
        )
        component_graph = self._layout._build_component_graph(
            components,
            families,
            component_by_person,
        )
        component_centers, levels = self._layout._place_components(
            genealogy,
            components,
            component_graph,
            component_by_person,
            families,
        )
        person_positions, page_width, page_height = self._layout._place_people(
            components,
            component_centers,
            levels,
        )

        marriage_connectors: dict[
            frozenset,
            tuple[float, float, float],
        ] = {}
        marriage_segments: list[Segment] = []
        partnership_pairs = sorted(
            self._layout._partnership_pairs(genealogy),
            key=lambda pair: tuple(sorted(str(person_id) for person_id in pair)),
        )
        for pair in partnership_pairs:
            person_a_id, person_b_id = sorted(
                pair,
                key=lambda person_id: person_positions[person_id].center_x,
            )
            pos_a = person_positions[person_a_id]
            pos_b = person_positions[person_b_id]

            gap_center_x = (pos_a.right + pos_b.left) / 2
            name_y_a = pos_a.top_y + self.TEXT_PADDING_Y + self.LINE_HEIGHT / 2
            name_y_b = pos_b.top_y + self.TEXT_PADDING_Y + self.LINE_HEIGHT / 2
            center_y = (name_y_a + name_y_b) / 2
            upper_y = center_y - self.MARRIAGE_LINE_GAP / 2
            lower_y = center_y + self.MARRIAGE_LINE_GAP / 2

            available_width = max(0.0, pos_b.left - pos_a.right - 10.0)
            sign_width = min(self.MARRIAGE_SIGN_WIDTH, available_width)
            left_x = gap_center_x - sign_width / 2
            right_x = gap_center_x + sign_width / 2

            marriage_connectors[pair] = (left_x, right_x, lower_y)
            if sign_width > 0.05:
                marriage_segments.extend(
                    (
                        Segment(left_x, upper_y, right_x, upper_y),
                        Segment(left_x, lower_y, right_x, lower_y),
                    )
                )

        router = OrthogonalConnectorRouter(
            person_positions,
            families,
            marriage_connectors,
        )
        try:
            routes = router.plan()
        except RoutingConflict as exc:
            parents = " / ".join(
                genealogy.persons[person_id].name
                for person_id in exc.family.parent_ids
            )
            children = ", ".join(
                genealogy.persons[person_id].name
                for person_id in exc.family.child_ids
            )
            raise ValueError(
                f"{title}: {parents} -> {children}: {exc}. "
                "Review manual generation/order; no misleading crossing was rendered."
            ) from exc

        line_segments = [
            *marriage_segments,
            *(segment for route in routes for segment in route.segments),
        ]
        min_x = min(
            [position.left for position in person_positions.values()]
            + [min(segment.x1, segment.x2) for segment in line_segments]
        )
        max_x = max(
            [position.right for position in person_positions.values()]
            + [max(segment.x1, segment.x2) for segment in line_segments]
        )
        page_width = max(
            page_width,
            max_x - min_x + self.PAGE_MARGIN_X * 2,
        )
        shift_x = (page_width - (max_x - min_x)) / 2 - min_x

        footnote_lines = self._footnote_lines(genealogy, page_width)
        footnote_center_y: float | None = None
        if footnote_lines:
            footnote_height = max(
                self.NOTE_LINE_HEIGHT,
                len(footnote_lines) * self.NOTE_LINE_HEIGHT,
            )
            footnote_top = page_height - self.PAGE_MARGIN_Y + self.NOTE_TOP_GAP
            footnote_center_y = footnote_top + footnote_height / 2
            page_height = footnote_top + footnote_height + self.NOTE_BOTTOM_GAP
            extra_width = max(
                0.0,
                page_height * self.MIN_LANDSCAPE_RATIO - page_width,
            )
            page_width += extra_width
            shift_x += extra_width / 2

        person_positions = {
            person_id: replace(
                position,
                center_x=position.center_x + shift_x,
            )
            for person_id, position in person_positions.items()
        }
        line_segments = [
            Segment(
                segment.x1 + shift_x,
                segment.y1,
                segment.x2 + shift_x,
                segment.y2,
            )
            for segment in line_segments
        ]

        # A translation changes neither crossings nor box hits; expose the
        # unambiguous pre-translation route diagnostics for regression tests.
        route_issues = tuple(router.issues(routes))
        self.last_geometry = {
            "positions": person_positions,
            "routes": routes,
            "families": families,
            "width": page_width,
            "height": page_height,
            "segments": tuple(line_segments),
            "router_searches": router.search_count,
            "accepted_alignments": len(self._layout.accepted_alignments),
            "deferred_alignments": len(self._layout.deferred_alignments),
            "reserved_corridors": len(self._layout.reserved_corridors),
            "issues": route_issues,
        }
        if route_issues:
            raise ValueError(f"Unsafe connector geometry: {route_issues[0]!r}")

        graph_output_format = "svg" if output_format == "eps" else output_format
        graph_output_renderer = "cairo" if output_format == "eps" else None
        graph = Graph(
            name="genealogy",
            format=graph_output_format,
            engine="neato",
            renderer=graph_output_renderer,
        )
        graph.attr(
            layout="neato",
            overlap="true",
            splines="false",
            outputorder="edgesfirst",
            bgcolor="white",
            pad="0.12",
            margin="0",
            notranslate="true",
        )
        graph.attr(
            "node",
            shape="plain",
            fontname=self.FONT_FAMILY,
            fontsize=str(self.FONT_SIZE),
            margin="0",
            pin="true",
        )
        graph.attr(
            "edge",
            color="#222222",
            penwidth=str(self.LINE_WIDTH),
            dir="none",
            tailclip="false",
            headclip="false",
        )

        anchors: dict[tuple[float, float], str] = {}

        def graph_y(canvas_y: float) -> float:
            return page_height - canvas_y

        def anchor(x: float, y: float) -> str:
            key = round(x, 6), round(y, 6)
            existing = anchors.get(key)
            if existing is not None:
                return existing
            node_id = f"anchor_{len(anchors) + 1}"
            anchors[key] = node_id
            graph.node(
                node_id,
                label="",
                shape="point",
                width="0.001",
                height="0.001",
                fixedsize="true",
                style="invis",
                pos=f"{key[0]:.6f},{graph_y(key[1]):.6f}!",
            )
            return node_id

        graph.node(
            "page_bottom_left",
            label="",
            shape="point",
            width="0.001",
            height="0.001",
            fixedsize="true",
            style="invis",
            pos="0,0!",
        )
        graph.node(
            "page_top_right",
            label="",
            shape="point",
            width="0.001",
            height="0.001",
            fixedsize="true",
            style="invis",
            pos=f"{page_width:.6f},{page_height:.6f}!",
        )

        # Split only at genuine endpoints/T-junctions. Do not independently
        # round parent and child centres; doing so was another source of tiny
        # visible offsets in earlier builds.
        for segment in self._split_junctions(tuple(line_segments)):
            graph.edge(
                anchor(segment.x1, segment.y1),
                anchor(segment.x2, segment.y2),
            )

        graph.node(
            "title",
            label=f"<<B>{html.escape(normalize_display_text(title))}</B>>",
            pos=(
                f"{page_width / 2:.6f},"
                f"{graph_y(self.PAGE_MARGIN_Y + 8):.6f}!"
            ),
            fontsize=str(self.TITLE_FONT_SIZE),
            fontname=self.FONT_FAMILY,
        )

        for person in genealogy.persons.values():
            position = person_positions[person.id]
            graph.node(
                self._person_node_id(person.id),
                label=self._labels.html_label(person),
                pos=(
                    f"{position.center_x:.6f},"
                    f"{graph_y(position.top_y + position.height / 2):.6f}!"
                ),
            )

        if footnote_center_y is not None:
            footnote_rows = "".join(
                (
                    '<TR><TD ALIGN="LEFT">'
                    f'<FONT POINT-SIZE="{self.NOTE_FONT_SIZE:g}">'
                    f"{html.escape(line)}</FONT></TD></TR>"
                )
                for line in footnote_lines
            )
            graph.node(
                "footnotes",
                label=(
                    '<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" '
                    f'CELLPADDING="0">{footnote_rows}</TABLE>>'
                ),
                pos=(
                    f"{page_width / 2:.6f},"
                    f"{graph_y(footnote_center_y):.6f}!"
                ),
                shape="plain",
                fontname=self.FONT_FAMILY,
                fontsize=str(self.NOTE_FONT_SIZE),
                margin="0",
            )

        if output_format == "eps":
            return self._render_publisher_safe_eps(graph, output_path)

        rendered = self._render_graph_artifact(
            graph,
            output_directory=output_path.parent,
        )
        rendered.replace(output_path)
        return output_path

    @staticmethod
    def _split_junctions(
        lines: tuple[Segment, ...],
    ) -> tuple[Segment, ...]:
        endpoints = {
            point
            for segment in lines
            for point in (segment.start, segment.end)
        }
        result: list[Segment] = []
        for segment in lines:
            left, top, right, bottom = segment.bounds
            if segment.vertical:
                values = sorted(
                    {
                        segment.y1,
                        segment.y2,
                        *(
                            y
                            for x, y in endpoints
                            if abs(x - segment.x1) < 1e-5
                            and top < y < bottom
                        ),
                    }
                )
                result.extend(
                    Segment(segment.x1, start, segment.x1, end)
                    for start, end in zip(values, values[1:])
                    if end - start > 1e-5
                )
            else:
                values = sorted(
                    {
                        segment.x1,
                        segment.x2,
                        *(
                            x
                            for x, y in endpoints
                            if abs(y - segment.y1) < 1e-5
                            and left < x < right
                        ),
                    }
                )
                result.extend(
                    Segment(start, segment.y1, end, segment.y1)
                    for start, end in zip(values, values[1:])
                    if end - start > 1e-5
                )
        return tuple(result)


__all__ = ["GraphvizGenealogyRenderer"]
