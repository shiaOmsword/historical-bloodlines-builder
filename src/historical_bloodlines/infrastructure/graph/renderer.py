from __future__ import annotations

import html
import math
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from uuid import UUID, uuid4

from graphviz import Graph

from historical_bloodlines.domain import Genealogy, Person
from historical_bloodlines.infrastructure.graph.labels import PersonLabelFormatter
from historical_bloodlines.infrastructure.graph.layout import (
    FixedGenealogyLayout,
    LayoutConfig,
)
from historical_bloodlines.infrastructure.graph.models import (
    FamilyView,
    PersonBox,
    PersonPosition,
)


@dataclass(frozen=True, slots=True)
class _FamilyBusGeometry:
    source_x: float
    child_xs: tuple[float, ...]
    left: float
    right: float
    base_y: float
    max_y: float


class GraphvizGenealogyRenderer:
    """Render a book-style genealogy using a deterministic fixed layout.

    Graphviz is used only as the vector output backend. All coordinates and all
    orthogonal line segments are calculated here. This prevents dot/neato from
    creating curls, loops, changing line thickness, or duplicating a person.
    """

    # Use Pango's generic family. Unlike a concrete Windows font name this
    # works with Graphviz's bundled font configuration and does not produce
    # a warning for every label.
    FONT_FAMILY = "Sans"
    FONT_SIZE = 13.0
    TITLE_FONT_SIZE = 19.0
    LINE_HEIGHT = 14.2
    TEXT_PADDING_X = 4.0
    TEXT_PADDING_Y = 1.5

    # Compact book-like spacing. The final PDF page is normalized to the
    # selected landscape paper size, so wasted space only shrinks the text.
    PERSON_GAP = 38.0
    COMPONENT_GAP = 26.0
    LAYER_GAP = 30.0
    PAGE_MARGIN_X = 22.0
    PAGE_MARGIN_Y = 16.0
    TITLE_AREA = 34.0
    LINE_WIDTH = 1.0
    MARRIAGE_LINE_GAP = 4.0
    MARRIAGE_SIGN_WIDTH = 12.0
    SINGLE_CHILD_SNAP_MAX = 18.0
    MIN_LANDSCAPE_RATIO = 1.4142
    MIN_PAGE_WIDTH = 760.0
    MAX_TEXT_LINE = 20
    MAX_NAME_LINE = 16
    MAX_HORIZONTAL_STRETCH = 1.35

    # Transit parent-child lines must not run through an unrelated label.  The
    # layout keeps person boxes apart, but a long vertical drop can still pass
    # through a box belonging to another branch (for example Edmund of York ->
    # Richard of Cambridge crossing Owen Tudor).  These clearances define a
    # protected rectangle around every label and a short approach lane above
    # the actual child.
    CONNECTOR_CLEARANCE_X = 8.0
    CONNECTOR_CLEARANCE_Y = 5.0
    CONNECTOR_APPROACH_GAP = 9.0

    # When one person has children from several partners, their horizontal
    # child buses can overlap exactly and look like one undifferentiated line.
    # Overlapping families are routed through separate nearby lanes.
    FAMILY_BUS_GAP = 8.0
    FAMILY_BUS_MIN_GAP = 2.5
    FAMILY_BUS_CHILD_CLEARANCE = 4.0

    def __init__(self) -> None:
        self._labels = PersonLabelFormatter(
            font_size=self.FONT_SIZE,
            line_height=self.LINE_HEIGHT,
            text_padding_x=self.TEXT_PADDING_X,
            text_padding_y=self.TEXT_PADDING_Y,
            max_text_line=self.MAX_TEXT_LINE,
            max_name_line=self.MAX_NAME_LINE,
        )
        self._layout = FixedGenealogyLayout(
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

    def render(
        self,
        genealogy: Genealogy,
        output_path: Path,
        *,
        title: str,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_format = output_path.suffix.lstrip(".").casefold()
        if output_format not in {"pdf", "svg", "png"}:
            raise ValueError("Output format must be pdf, svg or png")

        components, component_by_person = self._build_partner_components(genealogy)
        families = self._build_families(genealogy, component_by_person, components)
        component_graph = self._build_component_graph(components, families, component_by_person)

        component_centers, levels = self._place_components(
            genealogy,
            components,
            component_graph,
            component_by_person,
            families,
        )
        person_positions, page_width, page_height = self._place_people(
            components,
            component_centers,
            levels,
        )

        graph = Graph(name="genealogy", format=output_format, engine="neato")
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

        anchor_counter = 0
        anchors_by_position: dict[tuple[float, float], str] = {}

        def graph_y(canvas_y: float) -> float:
            return page_height - canvas_y

        def anchor(x: float, y: float) -> str:
            nonlocal anchor_counter
            key = (round(x, 3), round(y, 3))
            existing = anchors_by_position.get(key)
            if existing is not None:
                return existing

            anchor_counter += 1
            node_id = f"anchor_{anchor_counter}"
            anchors_by_position[key] = node_id
            graph.node(
                node_id,
                label="",
                shape="point",
                width="0.001",
                height="0.001",
                fixedsize="true",
                style="invis",
                pos=f"{key[0]:.3f},{graph_y(key[1]):.3f}!",
            )
            return node_id

        def segment(x1: float, y1: float, x2: float, y2: float) -> None:
            if math.isclose(x1, x2, abs_tol=0.05) and math.isclose(y1, y2, abs_tol=0.05):
                return
            if not (
                math.isclose(x1, x2, abs_tol=0.05)
                or math.isclose(y1, y2, abs_tol=0.05)
            ):
                raise ValueError("Relationship segment must be horizontal or vertical")

            graph.edge(anchor(x1, y1), anchor(x2, y2))

        def horizontal_bus(y: float, junction_xs: list[float]) -> None:
            # Split the bus at every vertical junction. All touching segments then
            # reuse the exact same anchor node, so no edge is extended through a
            # corner or T-junction and no anti-aliasing gap appears between them.
            for x1, y1, x2, y2 in self._horizontal_bus_segments(y, junction_xs):
                segment(x1, y1, x2, y2)

        # Invisible corner nodes force a predictable landscape bounding box.
        graph.node(
            "page_bottom_left",
            label="",
            shape="point",
            width="0.001",
            height="0.001",
            fixedsize="true",
            style="invis",
            pos=f"0,0!",
        )
        graph.node(
            "page_top_right",
            label="",
            shape="point",
            width="0.001",
            height="0.001",
            fixedsize="true",
            style="invis",
            pos=f"{page_width:.3f},{page_height:.3f}!",
        )

        graph.node(
            "title",
            label=f"<<B>{html.escape(title)}</B>>",
            pos=f"{page_width / 2:.3f},{graph_y(self.PAGE_MARGIN_Y + 8):.3f}!",
            fontsize=str(self.TITLE_FONT_SIZE),
            fontname=self.FONT_FAMILY,
        )

        for person in genealogy.persons.values():
            position = person_positions[person.id]
            graph.node(
                self._person_node_id(person.id),
                label=self._person_label(person),
                pos=(
                    f"{position.center_x:.3f},"
                    f"{graph_y(position.top_y + position.height / 2):.3f}!"
                ),
            )

        # Partnership lines. There are no visible marriage points. The line is
        # split at every family branch, so vertical descendants meet a real shared
        # anchor instead of visually piercing an uninterrupted horizontal edge.
        partnership_pairs = self._partnership_pairs(genealogy)
        marriage_connectors: dict[
            frozenset[UUID],
            tuple[float, float, float],
        ] = {}
        for pair in partnership_pairs:
            person_a_id, person_b_id = tuple(pair)
            pos_a = person_positions[person_a_id]
            pos_b = person_positions[person_b_id]
            if pos_a.center_x > pos_b.center_x:
                person_a_id, person_b_id = person_b_id, person_a_id
                pos_a, pos_b = pos_b, pos_a

            name_y_a = pos_a.top_y + self.LINE_HEIGHT * 0.58
            name_y_b = pos_b.top_y + self.LINE_HEIGHT * 0.58
            line_y = self._snap_coordinate((name_y_a + name_y_b) / 2)
            upper_line_y, lower_line_y = self._marriage_line_ys(line_y)
            gap_left_x = pos_a.right + 5.0
            gap_right_x = pos_b.left - 5.0
            if gap_right_x < gap_left_x:
                gap_left_x = pos_a.center_x
                gap_right_x = pos_b.center_x
            left_x, right_x = self._marriage_sign_xs(
                gap_left_x,
                gap_right_x,
            )

            junction_xs = [left_x, right_x]
            for family in families:
                if len(family.parent_ids) != 2 or frozenset(family.parent_ids) != pair:
                    continue
                source_x = (left_x + right_x) / 2
                if len(family.child_ids) == 1:
                    only_child_x = person_positions[family.child_ids[0]].center_x
                    if left_x - 0.5 <= only_child_x <= right_x + 0.5:
                        source_x = only_child_x
                junction_xs.append(source_x)

            # Two parallel strokes form the conventional genealogical "="
            # marriage sign. Descendant branches join the lower stroke.
            horizontal_bus(upper_line_y, [left_x, right_x])
            horizontal_bus(lower_line_y, junction_xs)
            marriage_connectors[pair] = (left_x, right_x, lower_line_y)

        # Parent-child connectors. Every connector is built from separate exact
        # horizontal/vertical segments, so Graphviz cannot curve or loop it.
        # Families from different marriages of the same person may have
        # overlapping horizontal spans. Put those buses on separate lanes so
        # two marriages never collapse into one continuous line.
        family_bus_ys = self._family_bus_ys(
            families,
            person_positions,
            marriage_connectors,
        )

        for family in families:
            children = sorted(
                family.child_ids,
                key=lambda child_id: (
                    person_positions[child_id].center_x,
                    genealogy.persons[child_id].source_key.row_number,
                ),
            )
            if not children:
                continue

            if len(family.parent_ids) == 2:
                pair = frozenset(family.parent_ids)
                connector = marriage_connectors.get(pair)
                if connector is None:
                    fallback_x, marriage_y = self._pair_fallback_midpoint(
                        family.parent_ids,
                        person_positions,
                    )
                    left_x = right_x = fallback_x
                else:
                    left_x, right_x, marriage_y = connector

                source_x = (left_x + right_x) / 2
                # For an only child, branch vertically from its x-coordinate
                # whenever that point lies on the marriage line. This removes
                # a purely cosmetic one-step elbow without moving any person.
                if len(children) == 1:
                    only_child_x = person_positions[children[0]].center_x
                    if left_x - 0.5 <= only_child_x <= right_x + 0.5:
                        source_x = only_child_x

                source_y = max(
                    person_positions[parent_id].bottom
                    for parent_id in family.parent_ids
                ) + 4.0
                segment(source_x, marriage_y, source_x, source_y)
            else:
                parent_position = person_positions[family.parent_ids[0]]
                source_x = parent_position.center_x
                source_y = parent_position.bottom + 4.0

            child_xs = [person_positions[child_id].center_x for child_id in children]
            child_tops = [person_positions[child_id].top_y for child_id in children]
            child_top = min(child_tops)
            bar_y = family_bus_ys[family]

            child_routes = [
                self._route_child_drop(
                    child_id=child_id,
                    bus_y=bar_y,
                    person_positions=person_positions,
                )
                for child_id in children
            ]

            if len(children) == 1:
                connection_x, routed_segments = child_routes[0]
                child_x = child_xs[0]
                if (
                    math.isclose(source_x, child_x, abs_tol=2.0)
                    and math.isclose(connection_x, child_x, abs_tol=0.05)
                ):
                    segment(source_x, source_y, child_x, child_top)
                else:
                    segment(source_x, source_y, source_x, bar_y)
                    horizontal_bus(bar_y, [source_x, connection_x])
                    for x1, y1, x2, y2 in routed_segments:
                        segment(x1, y1, x2, y2)
                continue

            segment(source_x, source_y, source_x, bar_y)
            horizontal_bus(
                bar_y,
                [source_x, *(connection_x for connection_x, _ in child_routes)],
            )
            for _, routed_segments in child_routes:
                for x1, y1, x2, y2 in routed_segments:
                    segment(x1, y1, x2, y2)

        # Graphviz for Windows still opens input files through APIs that may
        # reject non-ASCII filenames. Render under a private ASCII-only stem
        # and rename the finished artifact afterwards. The visible title and
        # the final user-facing filename remain unchanged.
        temporary_stem = f"bloodlines_render_{uuid4().hex}"
        rendered = Path(
            graph.render(
                filename=temporary_stem,
                directory=str(output_path.parent),
                cleanup=True,
                neato_no_op=2,
            )
        )
        rendered.replace(output_path)
        return output_path


    def _family_bus_ys(
        self,
        families: tuple[FamilyView, ...],
        person_positions: dict[UUID, PersonPosition],
        marriage_connectors: dict[frozenset[UUID], tuple[float, float, float]],
    ) -> dict[FamilyView, float]:
        """Return a collision-resistant horizontal bus Y for every family.

        A partner component can contain several marriages. If two child groups
        occupy overlapping X-ranges, using the same Y joins their buses into one
        apparent family line. We detect overlapping spans and assign nearby
        lanes in marriage order.

        The lane order follows the direction of the descendants. When children
        lie mostly to the left, left marriage sources stay higher; when they lie
        mostly to the right, right marriage sources stay higher. This prevents a
        later source stem from crossing an earlier family bus in the common
        nested-branch case.
        """

        geometry: dict[FamilyView, _FamilyBusGeometry] = {}
        by_component: dict[int, list[FamilyView]] = {}

        for family in families:
            children = tuple(family.child_ids)
            if not children:
                continue

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
                    source_x = (left_x + right_x) / 2
                    if len(children) == 1:
                        only_child_x = person_positions[children[0]].center_x
                        if left_x - 0.5 <= only_child_x <= right_x + 0.5:
                            source_x = only_child_x

                source_y = max(
                    person_positions[parent_id].bottom
                    for parent_id in family.parent_ids
                ) + 4.0
            else:
                parent_position = person_positions[family.parent_ids[0]]
                source_x = parent_position.center_x
                source_y = parent_position.bottom + 4.0

            child_xs = tuple(
                person_positions[child_id].center_x for child_id in children
            )
            child_top = min(
                person_positions[child_id].top_y for child_id in children
            )
            available = max(14.0, child_top - source_y)
            base_y = source_y + min(max(10.0, available * 0.34), 20.0)
            max_y = max(base_y, child_top - self.FAMILY_BUS_CHILD_CLEARANCE)

            geometry[family] = _FamilyBusGeometry(
                source_x=source_x,
                child_xs=child_xs,
                left=min(source_x, *child_xs),
                right=max(source_x, *child_xs),
                base_y=base_y,
                max_y=max_y,
            )
            by_component.setdefault(family.parent_component_id, []).append(family)

        result = {family: item.base_y for family, item in geometry.items()}

        for component_families in by_component.values():
            if len(component_families) < 2:
                continue

            # Build transitive clusters of horizontally overlapping family spans.
            ordered_by_left = sorted(
                component_families,
                key=lambda family: (
                    geometry[family].left,
                    geometry[family].right,
                ),
            )
            clusters: list[list[FamilyView]] = []
            current: list[FamilyView] = []
            current_right = -math.inf
            for family in ordered_by_left:
                item = geometry[family]
                if current and item.left > current_right + 0.5:
                    clusters.append(current)
                    current = []
                    current_right = -math.inf
                current.append(family)
                current_right = max(current_right, item.right)
            if current:
                clusters.append(current)

            for cluster in clusters:
                if len(cluster) < 2:
                    continue

                direction_score = sum(
                    (sum(geometry[family].child_xs) / len(geometry[family].child_xs))
                    - geometry[family].source_x
                    for family in cluster
                )
                # Descendants on the left: left source first (upper lane).
                # Descendants on the right: right source first (upper lane).
                lane_order = sorted(
                    cluster,
                    key=lambda family: geometry[family].source_x,
                    reverse=direction_score > 0,
                )

                assigned: list[float] | None = None
                gap = self.FAMILY_BUS_GAP
                while gap >= self.FAMILY_BUS_MIN_GAP - 0.01:
                    candidate: list[float] = []
                    previous_y = -math.inf
                    feasible = True
                    for family in lane_order:
                        item = geometry[family]
                        y = max(item.base_y, previous_y + gap)
                        if y > item.max_y + 0.05:
                            feasible = False
                            break
                        candidate.append(y)
                        previous_y = y
                    if feasible:
                        assigned = candidate
                        break
                    gap -= 0.5

                if assigned is None:
                    continue
                for family, y in zip(lane_order, assigned, strict=True):
                    result[family] = y

        return result

    @staticmethod
    def _horizontal_bus_segments(
        y: float,
        junction_xs: list[float],
    ) -> tuple[tuple[float, float, float, float], ...]:
        ordered_xs = sorted({round(x, 3) for x in junction_xs})
        return tuple(
            (left_x, y, right_x, y)
            for left_x, right_x in pairwise(ordered_xs)
        )

    def _route_child_drop(
        self,
        *,
        child_id: UUID,
        bus_y: float,
        person_positions: dict[UUID, PersonPosition],
    ) -> tuple[float, tuple[tuple[float, float, float, float], ...]]:
        """Return a collision-free drop from a family bus to one child.

        The first result is the x-coordinate at which the horizontal family
        bus must expose a junction.  Most children use their own centre x and
        therefore keep the old one-segment vertical drop.  When that vertical
        would cross an unrelated label, the route moves to the nearest free
        vertical corridor and approaches the child horizontally in the empty
        lane immediately above its box.
        """

        child_position = person_positions[child_id]
        child_x = child_position.center_x
        child_top = child_position.top_y
        ignored_ids = {child_id}

        if not self._vertical_segment_hits_person_box(
            child_x,
            bus_y,
            child_top,
            person_positions,
            ignored_ids=ignored_ids,
        ):
            return child_x, ((child_x, bus_y, child_x, child_top),)

        approach_y = max(bus_y, child_top - self.CONNECTOR_APPROACH_GAP)
        detour_x = self._nearest_free_vertical_corridor(
            preferred_x=child_x,
            y1=bus_y,
            y2=approach_y,
            person_positions=person_positions,
            ignored_ids=ignored_ids,
        )

        # The approach lane normally lies between generations and therefore is
        # clear.  Search upward in the unlikely case that another tall label
        # reaches into it.  The child itself is intentionally ignored because
        # the short final vertical segment must terminate at that box.
        approach_y = self._nearest_free_horizontal_lane(
            preferred_y=approach_y,
            x1=detour_x,
            x2=child_x,
            lower_bound=bus_y,
            person_positions=person_positions,
            ignored_ids=ignored_ids,
        )

        return detour_x, (
            (detour_x, bus_y, detour_x, approach_y),
            (detour_x, approach_y, child_x, approach_y),
            (child_x, approach_y, child_x, child_top),
        )

    def _nearest_free_vertical_corridor(
        self,
        *,
        preferred_x: float,
        y1: float,
        y2: float,
        person_positions: dict[UUID, PersonPosition],
        ignored_ids: set[UUID],
    ) -> float:
        candidates = {preferred_x}
        span_top, span_bottom = sorted((y1, y2))

        for person_id, position in person_positions.items():
            if person_id in ignored_ids:
                continue
            box_top = position.top_y - self.CONNECTOR_CLEARANCE_Y
            box_bottom = position.bottom + self.CONNECTOR_CLEARANCE_Y
            if span_bottom < box_top or span_top > box_bottom:
                continue
            candidates.add(position.left - self.CONNECTOR_CLEARANCE_X)
            candidates.add(position.right + self.CONNECTOR_CLEARANCE_X)

        ordered = sorted(
            candidates,
            key=lambda candidate: (
                abs(candidate - preferred_x),
                candidate > preferred_x,
                candidate,
            ),
        )
        for candidate in ordered:
            if not self._vertical_segment_hits_person_box(
                candidate,
                y1,
                y2,
                person_positions,
                ignored_ids=ignored_ids,
            ):
                return candidate

        # Every protected box contributes both outer edges, so a free corridor
        # should always exist.  This fallback keeps rendering deterministic if
        # future layout constraints produce a pathological wall of labels.
        return min(candidates) - self.CONNECTOR_CLEARANCE_X

    def _nearest_free_horizontal_lane(
        self,
        *,
        preferred_y: float,
        x1: float,
        x2: float,
        lower_bound: float,
        person_positions: dict[UUID, PersonPosition],
        ignored_ids: set[UUID],
    ) -> float:
        if not self._horizontal_segment_hits_person_box(
            x1,
            x2,
            preferred_y,
            person_positions,
            ignored_ids=ignored_ids,
        ):
            return preferred_y

        candidates = {preferred_y, lower_bound}
        segment_left, segment_right = sorted((x1, x2))
        for person_id, position in person_positions.items():
            if person_id in ignored_ids:
                continue
            box_left = position.left - self.CONNECTOR_CLEARANCE_X
            box_right = position.right + self.CONNECTOR_CLEARANCE_X
            if segment_right < box_left or segment_left > box_right:
                continue
            candidates.add(position.top_y - self.CONNECTOR_CLEARANCE_Y)
            candidates.add(position.bottom + self.CONNECTOR_CLEARANCE_Y)

        valid = [
            candidate
            for candidate in candidates
            if lower_bound <= candidate <= preferred_y
            and not self._horizontal_segment_hits_person_box(
                x1,
                x2,
                candidate,
                person_positions,
                ignored_ids=ignored_ids,
            )
        ]
        if valid:
            return min(valid, key=lambda candidate: abs(candidate - preferred_y))
        return lower_bound

    def _vertical_segment_hits_person_box(
        self,
        x: float,
        y1: float,
        y2: float,
        person_positions: dict[UUID, PersonPosition],
        *,
        ignored_ids: set[UUID],
    ) -> bool:
        segment_top, segment_bottom = sorted((y1, y2))
        for person_id, position in person_positions.items():
            if person_id in ignored_ids:
                continue
            left = position.left - self.CONNECTOR_CLEARANCE_X
            right = position.right + self.CONNECTOR_CLEARANCE_X
            top = position.top_y - self.CONNECTOR_CLEARANCE_Y
            bottom = position.bottom + self.CONNECTOR_CLEARANCE_Y
            if left < x < right and not (
                segment_bottom <= top or segment_top >= bottom
            ):
                return True
        return False

    def _horizontal_segment_hits_person_box(
        self,
        x1: float,
        x2: float,
        y: float,
        person_positions: dict[UUID, PersonPosition],
        *,
        ignored_ids: set[UUID],
    ) -> bool:
        segment_left, segment_right = sorted((x1, x2))
        for person_id, position in person_positions.items():
            if person_id in ignored_ids:
                continue
            left = position.left - self.CONNECTOR_CLEARANCE_X
            right = position.right + self.CONNECTOR_CLEARANCE_X
            top = position.top_y - self.CONNECTOR_CLEARANCE_Y
            bottom = position.bottom + self.CONNECTOR_CLEARANCE_Y
            if top < y < bottom and not (
                segment_right <= left or segment_left >= right
            ):
                return True
        return False

    def _build_partner_components(self, genealogy: Genealogy):
        return self._layout._build_partner_components(genealogy)

    def _build_families(
        self,
        genealogy: Genealogy,
        component_by_person,
        components,
    ):
        return self._layout._build_families(
            genealogy,
            component_by_person,
            components,
        )

    def _build_component_graph(
        self,
        components,
        families,
        component_by_person,
    ):
        return self._layout._build_component_graph(
            components,
            families,
            component_by_person,
        )

    def _place_components(
        self,
        genealogy,
        components,
        component_graph,
        component_by_person,
        families,
    ):
        return self._layout._place_components(
            genealogy,
            components,
            component_graph,
            component_by_person,
            families,
        )

    def _realign_single_child_components(
        self,
        genealogy,
        components,
        component_graph,
        component_by_person,
        families,
        levels,
        centers,
    ):
        return self._layout._realign_single_child_components(
            genealogy,
            components,
            component_graph,
            component_by_person,
            families,
            levels,
            centers,
        )

    def _place_tree_components(
        self,
        genealogy,
        components,
        component_graph,
        component_by_person,
        families,
    ):
        return self._layout._place_tree_components(
            genealogy,
            components,
            component_graph,
            component_by_person,
            families,
        )

    def _place_people(self, components, component_centers, levels):
        return self._layout._place_people(
            components,
            component_centers,
            levels,
        )

    def _person_box(self, person: Person) -> PersonBox:
        return self._labels.measure(person)

    def _person_label(self, person: Person) -> str:
        return self._labels.html_label(person)

    def _wrap(self, value: str) -> tuple[str, ...]:
        return self._labels.wrap(value)

    @classmethod
    def _marriage_line_ys(cls, center_y: float) -> tuple[float, float]:
        center_y = cls._snap_coordinate(center_y)
        half_gap = cls.MARRIAGE_LINE_GAP / 2
        return cls._snap_coordinate(center_y - half_gap), cls._snap_coordinate(center_y + half_gap)

    @classmethod
    def _marriage_sign_xs(
        cls,
        gap_left_x: float,
        gap_right_x: float,
    ) -> tuple[float, float]:
        """Return a compact, centered horizontal extent for the ``=`` sign."""

        left_boundary, right_boundary = sorted((gap_left_x, gap_right_x))
        center_x = cls._snap_coordinate((left_boundary + right_boundary) / 2)
        sign_width = min(cls.MARRIAGE_SIGN_WIDTH, right_boundary - left_boundary)
        half_width = sign_width / 2
        return cls._snap_coordinate(center_x - half_width), cls._snap_coordinate(center_x + half_width)

    @staticmethod
    def _snap_coordinate(value: float) -> float:
        """Snap line geometry to whole points for visually even strokes."""

        return round(value)

    @staticmethod
    def _partnership_pairs(genealogy: Genealogy) -> set[frozenset[UUID]]:
        pairs = {
            frozenset((marriage.spouse_a_id, marriage.spouse_b_id))
            for marriage in genealogy.marriages
        }
        pairs.update(
            relation.parent_ids
            for relation in genealogy.family_child_relations
            if len(relation.parent_ids) == 2
        )
        return pairs

    @staticmethod
    def _pair_fallback_midpoint(
        parent_ids: tuple[UUID, ...],
        positions: dict[UUID, PersonPosition],
    ) -> tuple[float, float]:
        parent_positions = [positions[parent_id] for parent_id in parent_ids]
        x = sum(position.center_x for position in parent_positions) / len(parent_positions)
        y = sum(position.top_y + 10.0 for position in parent_positions) / len(parent_positions)
        return x, y

    @staticmethod
    def _person_node_id(person_id: UUID) -> str:
        return f"person_{person_id.hex}"
