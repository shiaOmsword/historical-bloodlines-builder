from __future__ import annotations

import html
import math
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
    PersonBox,
    PersonPosition,
)


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
    SINGLE_CHILD_SNAP_MAX = 18.0
    MIN_LANDSCAPE_RATIO = 1.4142
    MIN_PAGE_WIDTH = 760.0
    MAX_TEXT_LINE = 20
    MAX_NAME_LINE = 16
    MAX_HORIZONTAL_STRETCH = 1.35

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
            line_y = (name_y_a + name_y_b) / 2
            left_x = pos_a.right + 5.0
            right_x = pos_b.left - 5.0
            if right_x < left_x:
                left_x = pos_a.center_x
                right_x = pos_b.center_x

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

            horizontal_bus(line_y, junction_xs)
            marriage_connectors[pair] = (left_x, right_x, line_y)

        # Parent-child connectors. Every connector is built from separate exact
        # horizontal/vertical segments, so Graphviz cannot curve or loop it.
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
            available = max(14.0, child_top - source_y)
            bar_y = source_y + min(max(10.0, available * 0.34), 20.0)

            if len(children) == 1:
                child_x = child_xs[0]
                if math.isclose(source_x, child_x, abs_tol=2.0):
                    segment(source_x, source_y, child_x, child_top)
                else:
                    segment(source_x, source_y, source_x, bar_y)
                    segment(source_x, bar_y, child_x, bar_y)
                    segment(child_x, bar_y, child_x, child_top)
                continue

            segment(source_x, source_y, source_x, bar_y)
            horizontal_bus(bar_y, [source_x, *child_xs])
            for child_x, top_y in zip(child_xs, child_tops):
                segment(child_x, bar_y, child_x, top_y)

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
