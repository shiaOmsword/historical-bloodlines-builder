from __future__ import annotations

from dataclasses import replace
import html
import math
from pathlib import Path

from graphviz import Graph

from historical_bloodlines.config.render import RenderConfig

from historical_bloodlines.domain import Genealogy, Person
from historical_bloodlines.infrastructure.graph.connector_routing import (
    OrthogonalConnectorRouter,
    RoutingConflict,
    Segment,
    intersection,
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


MARRIAGE_TEXT_CLEARANCE = 5.0
MARRIAGE_SIGN_WIDTH = 12.0


def _marriage_source_center(
    left_center: float,
    left_width: float,
    right_center: float,
    right_width: float,
) -> float:
    """Return the visual/source centre shared by layout and rendered ``=``.

    Prefer the midpoint between spouse anchors. When unequal label widths put
    that midpoint too close to either label, clamp just enough to keep a full
    marriage sign inside the readable text gap. Sharing this calculation with
    family layout prevents the sign correction from recreating a tiny dogleg in
    descendant connectors.
    """

    if left_center > right_center:
        left_center, right_center = right_center, left_center
        left_width, right_width = right_width, left_width

    gap_left = left_center + left_width / 2 + MARRIAGE_TEXT_CLEARANCE
    gap_right = right_center - right_width / 2 - MARRIAGE_TEXT_CLEARANCE
    available_width = max(0.0, gap_right - gap_left)
    sign_width = min(MARRIAGE_SIGN_WIDTH, available_width)
    if sign_width <= 0.05:
        return (left_center + left_width / 2 + right_center - right_width / 2) / 2

    preferred = (left_center + right_center) / 2
    minimum = gap_left + sign_width / 2
    maximum = gap_right - sign_width / 2
    return min(max(preferred, minimum), maximum)


def _component_marriage_centers(anchors, pairs):
    """Assign each partnership a distinct clear gap in its partner component.

    With three spouses a pair's midpoint can fall inside another spouse's
    label. Prefer the established midpoint, but match non-adjacent marriages
    to available gaps rather than starting a descendant line inside text.
    Layout and drawing must use this same assignment.
    """
    people = sorted(anchors, key=lambda person_id: anchors[person_id][0])
    indices = {person_id: index for index, person_id in enumerate(people)}
    pairs = sorted(
        (pair for pair in pairs if pair.issubset(anchors)),
        key=lambda pair: tuple(sorted(indices[person_id] for person_id in pair)),
    )
    if not pairs:
        return {}

    gaps = []
    for left_id, right_id in zip(people, people[1:]):
        left_x, left_width = anchors[left_id]
        right_x, right_width = anchors[right_id]
        gaps.append((
            left_x + left_width / 2 + MARRIAGE_TEXT_CLEARANCE + MARRIAGE_SIGN_WIDTH / 2,
            right_x - right_width / 2 - MARRIAGE_TEXT_CLEARANCE - MARRIAGE_SIGN_WIDTH / 2,
        ))

    candidates = {}
    for pair in pairs:
        left_id, right_id = sorted(pair, key=indices.get)
        preferred = _marriage_source_center(*anchors[left_id], *anchors[right_id])
        options = []
        for index in range(indices[left_id], indices[right_id]):
            minimum, maximum = gaps[index]
            if minimum <= maximum:
                center = min(max(preferred, minimum), maximum)
                # Translation must not change ties between equally good gaps.
                options.append((round(abs(center - preferred), 8), index, center))
        candidates[pair] = sorted(options)

    # Adjacent marriages have only one gap; reserve those first. Partner
    # components are small, and pruning keeps the matching deterministic.
    ordered = sorted(pairs, key=lambda pair: (len(candidates[pair]), pairs.index(pair)))
    best = None
    best_centers = None

    def visit(index, used, centers, cost):
        nonlocal best, best_centers
        if best is not None and cost > best[0]:
            return
        if index == len(ordered):
            score = cost, tuple(centers[pair] for pair in pairs)
            if best is None or score < best:
                best, best_centers = score, dict(centers)
            return
        pair = ordered[index]
        for distance, gap, center in candidates[pair]:
            if gap in used:
                continue
            centers[pair] = center
            visit(index + 1, used | {gap}, centers, cost + distance)
            del centers[pair]

    visit(0, set(), {}, 0.0)
    if best_centers is None:
        raise ValueError("No distinct, label-free gaps for the partnership signs")
    return best_centers


def _nonadjacent_marriage_lanes(positions, pairs):
    """Reserve an overhead lane for each non-adjacent partnership and its sign."""
    result = {}
    lanes = {}
    for pair in sorted(pairs, key=lambda item: (
        abs(positions[tuple(item)[0]].center_x - positions[tuple(item)[1]].center_x),
        tuple(sorted(str(person_id) for person_id in item)),
    )):
        left_id, right_id = sorted(pair, key=lambda person_id: positions[person_id].center_x)
        left, right = positions[left_id], positions[right_id]
        intervening = [
            position for person_id, position in positions.items()
            if person_id not in pair
            and math.isclose(position.top_y, left.top_y, abs_tol=1e-6)
            and left.center_x < position.center_x < right.center_x
        ]
        if not intervening:
            continue

        lane = lanes.get(left.top_y, 0)
        lanes[left.top_y] = lane + 1
        result[pair] = left.top_y - 10.0 - lane * 8.0
    return result


def _nonadjacent_marriage_segments(
    positions, pairs, connectors, *, attachment_offset, line_gap,
):
    """Join true spouses to their raised sign without joining adjacent signs."""
    result = []
    owned_segments = []
    for pair in _nonadjacent_marriage_lanes(positions, pairs):
        left_id, right_id = sorted(pair, key=lambda person_id: positions[person_id].center_x)
        left, right = positions[left_id], positions[right_id]
        sign_left, sign_right, lower_y = connectors[pair]
        # Enter between the two bars so the bridge does not swallow the '='.
        junction_y = lower_y - line_gap / 2
        for source_x, sign_x, position in (
            (left.right + MARRIAGE_TEXT_CLEARANCE, sign_left, left),
            (right.left - MARRIAGE_TEXT_CLEARANCE, sign_right, right),
        ):
            points = (
                (source_x, position.top_y + attachment_offset),
                (source_x, junction_y),
                (sign_x, junction_y),
            )
            segments = tuple(
                Segment(*first, *second)
                for first, second in zip(points, points[1:])
                if first != second
            )
            for segment in segments:
                for other_pair, other_segment in owned_segments:
                    if pair.isdisjoint(other_pair) and intersection(segment, other_segment):
                        raise ValueError("Unrelated partnership bridges would intersect")
                for other_pair, (other_left, other_right, other_lower) in connectors.items():
                    if not pair.isdisjoint(other_pair):
                        continue
                    if any(intersection(segment, Segment(other_left, y, other_right, y))
                           for y in (other_lower, other_lower - line_gap)):
                        raise ValueError("A partnership bridge would intersect an unrelated marriage")
                owned_segments.append((pair, segment))
            result.extend(segments)
    return tuple(result)


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


class _ReadableOrthogonalGenealogyLayout(OrthogonalGenealogyLayout):
    """Use readable marriage centres and planar two-person orientation."""

    def _build_partner_components(self, genealogy):
        self._marriage_pairs = self._partnership_pairs(genealogy)
        return super()._build_partner_components(genealogy)

    def _order_partner_component(self, genealogy, person_ids):
        ordered = super()._order_partner_component(genealogy, person_ids)
        if len(ordered) != 2:
            return ordered

        # An explicit person order remains authoritative. Otherwise orient the
        # spouses toward their parent branches, even without workbook hints.
        if any(
            genealogy.persons[person_id].layout_hint.order is not None
            for person_id in ordered
        ):
            return ordered

        anchors = {}
        for person_id in ordered:
            person = genealogy.persons[person_id]
            parent_orders = []
            generation_gaps = []
            parent_rows = []
            for relation in genealogy.family_child_relations:
                if relation.child_id != person_id:
                    continue
                for parent_id in relation.parent_ids:
                    if parent_id in person_ids:
                        continue
                    parent = genealogy.persons[parent_id]
                    if parent.layout_hint.order is not None:
                        parent_orders.append(parent.layout_hint.order)
                    if (
                        person.layout_hint.generation is not None
                        and parent.layout_hint.generation is not None
                    ):
                        generation_gaps.append(
                            person.layout_hint.generation
                            - parent.layout_hint.generation
                        )
                    parent_rows.append(parent.source_key.row_number)
            if parent_rows:
                anchors[person_id] = (
                    max(generation_gaps, default=1),
                    sum(parent_orders) / len(parent_orders)
                    if parent_orders else min(parent_rows),
                    min(parent_rows),
                    bool(parent_orders),
                )

        if len(anchors) != 2:
            return ordered
        # Manual priorities and source row numbers use different scales. Keep
        # the established orientation if only one parent branch is numbered.
        if len({anchor[3] for anchor in anchors.values()}) != 1:
            return ordered
        if (
            all(anchor[3] for anchor in anchors.values())
            and max(anchor[0] for anchor in anchors.values()) <= 1
        ):
            return ordered

        first_order = anchors[ordered[0]][1]
        second_order = anchors[ordered[1]][1]
        if math.isclose(first_order, second_order, abs_tol=1e-9):
            return ordered

        # With no parent order hints, their source rows are the base layout's
        # branch tie-breaker. Spouse source order can reverse those branches and
        # trap an incoming route behind the other spouse's sibling bus.
        original_index = {person_id: index for index, person_id in enumerate(ordered)}
        return tuple(
            sorted(
                ordered,
                key=lambda person_id: (
                    anchors[person_id][1],
                    anchors[person_id][2],
                    original_index[person_id],
                ),
            )
        )

    def _family_source_offset(self, parent_ids, component) -> float:
        if len(parent_ids) == 1:
            return component.person_offsets[parent_ids[0]]

        centers = _component_marriage_centers(
            {person_id: (component.person_offsets[person_id], box.width)
             for person_id, box in component.person_boxes.items()},
            self._marriage_pairs,
        )
        return centers[frozenset(parent_ids)]


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

    def __init__(self, config: RenderConfig | None = None) -> None:
        self.config = config or RenderConfig()
        typography = self.config.typography
        layout = self.config.layout
        # Instance attributes only: independent jobs never modify global style.
        self.FONT_SIZE = typography.font_size_pt
        self.LINE_HEIGHT = typography.resolved_line_height_pt
        self.TITLE_FONT_SIZE = typography.title_font_size_pt
        self.NOTE_FONT_SIZE = typography.note_font_size_pt
        self.NOTE_LINE_HEIGHT = typography.note_line_height_pt
        self.PERSON_GAP = layout.person_gap_pt
        self.COMPONENT_GAP = layout.component_gap_pt
        self.LAYER_GAP = layout.layer_gap_pt
        self.PAGE_MARGIN_X = layout.page_margin_x_pt
        self.PAGE_MARGIN_Y = layout.page_margin_y_pt
        self.MIN_PAGE_WIDTH = layout.min_page_width_pt
        self.MAX_TEXT_LINE = layout.max_text_line
        self.MAX_NAME_LINE = layout.max_name_line
        self._labels = _ReadablePersonLabelFormatter(
            font_size=self.FONT_SIZE,
            line_height=self.LINE_HEIGHT,
            text_padding_x=self.TEXT_PADDING_X,
            text_padding_y=self.TEXT_PADDING_Y,
            max_text_line=self.MAX_TEXT_LINE,
            max_name_line=self.MAX_NAME_LINE,
        )
        self._layout = _ReadableOrthogonalGenealogyLayout(
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

    def _readable_marriage_sign_xs(
        self,
        left_position,
        right_position,
    ) -> tuple[float, float]:
        """Place ``=`` on the same source centre used by family layout."""

        if left_position.center_x > right_position.center_x:
            left_position, right_position = right_position, left_position
        gap_left = left_position.right + MARRIAGE_TEXT_CLEARANCE
        gap_right = right_position.left - MARRIAGE_TEXT_CLEARANCE
        available_width = max(0.0, gap_right - gap_left)
        sign_width = min(self.MARRIAGE_SIGN_WIDTH, available_width)
        center_x = _marriage_source_center(
            left_position.center_x,
            left_position.width,
            right_position.center_x,
            right_position.width,
        )
        return center_x - sign_width / 2, center_x + sign_width / 2

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
        nonadjacent_by_level = {}
        for component in components.values():
            indices = {person_id: index for index, person_id in enumerate(component.person_ids)}
            count = sum(
                abs(indices[tuple(pair)[0]] - indices[tuple(pair)[1]]) > 1
                for pair in self._layout._partnership_pairs(genealogy)
                if pair.issubset(indices)
            )
            level = levels[component.id]
            nonadjacent_by_level[level] = nonadjacent_by_level.get(level, 0) + count
        bridge_room = max(nonadjacent_by_level.values(), default=0) * 8.0
        self._layout.LAYER_GAP = max(self.LAYER_GAP, bridge_room + 18.0)
        self._layout.TITLE_AREA = self.TITLE_AREA + nonadjacent_by_level.get(0, 0) * 8.0
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
        marriage_centers = {}
        for component in components.values():
            marriage_centers.update(_component_marriage_centers(
                {person_id: (person_positions[person_id].center_x,
                             person_positions[person_id].width)
                 for person_id in component.person_ids},
                partnership_pairs,
            ))
        bridge_lanes = _nonadjacent_marriage_lanes(person_positions, partnership_pairs)
        for pair in partnership_pairs:
            person_a_id, person_b_id = sorted(
                pair,
                key=lambda person_id: person_positions[person_id].center_x,
            )
            pos_a = person_positions[person_a_id]
            pos_b = person_positions[person_b_id]

            name_y_a = pos_a.top_y + self.TEXT_PADDING_Y + self.LINE_HEIGHT / 2
            name_y_b = pos_b.top_y + self.TEXT_PADDING_Y + self.LINE_HEIGHT / 2
            center_y = (name_y_a + name_y_b) / 2
            upper_y = center_y - self.MARRIAGE_LINE_GAP / 2
            upper_y = bridge_lanes.get(pair, upper_y)
            lower_y = upper_y + self.MARRIAGE_LINE_GAP

            center_x = marriage_centers[pair]
            left_x = center_x - self.MARRIAGE_SIGN_WIDTH / 2
            right_x = center_x + self.MARRIAGE_SIGN_WIDTH / 2
            sign_width = right_x - left_x

            marriage_connectors[pair] = (left_x, right_x, lower_y)
            if sign_width > 0.05:
                marriage_segments.extend(
                    (
                        Segment(left_x, upper_y, right_x, upper_y),
                        Segment(left_x, lower_y, right_x, lower_y),
                    )
                )

        partnership_segments = _nonadjacent_marriage_segments(
            person_positions, partnership_pairs, marriage_connectors,
            attachment_offset=self.TEXT_PADDING_Y + self.LINE_HEIGHT / 2,
            line_gap=self.MARRIAGE_LINE_GAP,
        )
        marriage_segments.extend(partnership_segments)
        router = OrthogonalConnectorRouter(
            person_positions,
            families,
            marriage_connectors,
            reserved_corridors=getattr(self._layout, "reserved_corridors", ()),
            partnership_segments=partnership_segments,
        )
        if any(box.hit(segment) for box in router.boxes for segment in marriage_segments):
            raise ValueError("A partnership connector overlaps a person label")
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
            "partnership_segments": tuple(
                Segment(segment.x1 + shift_x, segment.y1,
                        segment.x2 + shift_x, segment.y2)
                for segment in partnership_segments
            ),
            "marriage_connectors": {
                pair: (left + shift_x, right + shift_x, lower_y)
                for pair, (left, right, lower_y) in marriage_connectors.items()
            },
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
