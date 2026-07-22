from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from itertools import permutations
from uuid import UUID

import networkx as nx

from historical_bloodlines.domain import Genealogy, Person
from historical_bloodlines.infrastructure.graph.labels import PersonLabelFormatter
from historical_bloodlines.infrastructure.graph.models import (
    FamilyView,
    PartnerComponent,
    PersonBox,
    PersonPosition,
)


@dataclass(frozen=True, slots=True)
class LayoutConfig:
    person_gap: float
    component_gap: float
    layer_gap: float
    page_margin_x: float
    page_margin_y: float
    title_area: float
    single_child_snap_max: float
    min_landscape_ratio: float
    min_page_width: float
    max_horizontal_stretch: float


class FixedGenealogyLayout:
    """Build the deterministic render projection and absolute coordinates."""

    def __init__(
        self,
        config: LayoutConfig,
        labels: PersonLabelFormatter,
    ) -> None:
        self.PERSON_GAP = config.person_gap
        self.COMPONENT_GAP = config.component_gap
        self.LAYER_GAP = config.layer_gap
        self.PAGE_MARGIN_X = config.page_margin_x
        self.PAGE_MARGIN_Y = config.page_margin_y
        self.TITLE_AREA = config.title_area
        self.SINGLE_CHILD_SNAP_MAX = config.single_child_snap_max
        self.MIN_LANDSCAPE_RATIO = config.min_landscape_ratio
        self.MIN_PAGE_WIDTH = config.min_page_width
        self.MAX_HORIZONTAL_STRETCH = config.max_horizontal_stretch
        self._labels = labels

    def _build_partner_components(
        self,
        genealogy: Genealogy,
    ) -> tuple[dict[int, PartnerComponent], dict[UUID, int]]:
        partnership_graph = nx.Graph()
        partnership_graph.add_nodes_from(genealogy.persons)
        partnership_graph.add_edges_from(
            tuple(pair) for pair in self._partnership_pairs(genealogy)
        )

        components: dict[int, PartnerComponent] = {}
        component_by_person: dict[UUID, int] = {}

        connected_components = sorted(
            nx.connected_components(partnership_graph),
            key=lambda ids: min(
                genealogy.persons[person_id].source_key.row_number
                for person_id in ids
            ),
        )
        for component_id, person_ids_set in enumerate(connected_components):
            ordered_ids = self._order_partner_component(genealogy, person_ids_set)
            explicit_generations = {
                genealogy.persons[person_id].layout_hint.generation
                for person_id in ordered_ids
                if genealogy.persons[person_id].layout_hint.generation is not None
            }
            if len(explicit_generations) > 1:
                people = ", ".join(
                    genealogy.persons[person_id].name for person_id in ordered_ids
                )
                values = ", ".join(str(item) for item in sorted(explicit_generations))
                raise ValueError(
                    "People in one partnership component must have the same "
                    f"generation: {people} (got {values})"
                )

            explicit_orders = [
                genealogy.persons[person_id].layout_hint.order
                for person_id in ordered_ids
                if genealogy.persons[person_id].layout_hint.order is not None
            ]
            boxes = {
                person_id: self._person_box(genealogy.persons[person_id])
                for person_id in ordered_ids
            }
            total_width = sum(box.width for box in boxes.values())
            if len(ordered_ids) > 1:
                total_width += self.PERSON_GAP * (len(ordered_ids) - 1)

            left = -total_width / 2
            offsets: dict[UUID, float] = {}
            cursor = left
            for person_id in ordered_ids:
                box = boxes[person_id]
                offsets[person_id] = cursor + box.width / 2
                cursor += box.width + self.PERSON_GAP

            component = PartnerComponent(
                id=component_id,
                person_ids=ordered_ids,
                person_boxes=boxes,
                person_offsets=offsets,
                width=total_width,
                height=max(box.height for box in boxes.values()),
                min_source_row=min(
                    genealogy.persons[person_id].source_key.row_number
                    for person_id in ordered_ids
                ),
                generation_hint=(
                    next(iter(explicit_generations)) - 1
                    if explicit_generations
                    else None
                ),
                order_hint=min(explicit_orders) if explicit_orders else None,
            )
            components[component_id] = component
            for person_id in ordered_ids:
                component_by_person[person_id] = component_id

        return components, component_by_person

    def _build_families(
        self,
        genealogy: Genealogy,
        component_by_person: dict[UUID, int],
        components: dict[int, PartnerComponent],
    ) -> tuple[FamilyView, ...]:
        # Normalize duplicated single-parent records into one two-parent family
        # when both parents are known partners and point to the same child.
        # Historical source tables often describe the same child once from the
        # mother's row and once from the father's row. Rendering those as two
        # independent families creates doubled or L-shaped connectors.
        parent_sets_by_child: dict[UUID, list[frozenset[UUID]]] = defaultdict(list)
        for relation in genealogy.family_child_relations:
            parent_sets_by_child[relation.child_id].append(relation.parent_ids)

        partnership_pairs = self._partnership_pairs(genealogy)
        children_by_parents: dict[frozenset[UUID], list[UUID]] = defaultdict(list)
        for child_id, raw_parent_sets in parent_sets_by_child.items():
            parent_sets = list(dict.fromkeys(raw_parent_sets))
            singles = {next(iter(item)) for item in parent_sets if len(item) == 1}
            consumed: set[UUID] = set()

            for pair in partnership_pairs:
                if len(pair) != 2 or not pair.issubset(singles):
                    continue
                children_by_parents[pair].append(child_id)
                consumed.update(pair)

            for parent_ids in parent_sets:
                if len(parent_ids) == 1 and next(iter(parent_ids)) in consumed:
                    continue
                if len(parent_ids) == 2 and any(
                    parent_ids == pair and pair.issubset(singles)
                    for pair in partnership_pairs
                ):
                    # The explicit pair and the two single-parent rows describe
                    # the same family; keep only one normalized relation.
                    if child_id not in children_by_parents[parent_ids]:
                        children_by_parents[parent_ids].append(child_id)
                    continue
                children_by_parents[parent_ids].append(child_id)

        families: list[FamilyView] = []
        for parent_ids, child_ids in children_by_parents.items():
            ordered_parents = tuple(
                sorted(
                    parent_ids,
                    key=lambda person_id: genealogy.persons[person_id].source_key.row_number,
                )
            )
            parent_component_id = component_by_person[ordered_parents[0]]
            component = components[parent_component_id]
            source_offset = self._family_source_offset(
                ordered_parents,
                component,
            )
            families.append(
                FamilyView(
                    parent_ids=ordered_parents,
                    child_ids=tuple(dict.fromkeys(child_ids)),
                    parent_component_id=parent_component_id,
                    source_offset=source_offset,
                )
            )

        return tuple(
            sorted(
                families,
                key=lambda family: (
                    components[family.parent_component_id].min_source_row,
                    family.source_offset,
                    min(
                        genealogy.persons[child_id].source_key.row_number
                        for child_id in family.child_ids
                    ),
                ),
            )
        )

    @staticmethod
    def _build_component_graph(
        components: dict[int, PartnerComponent],
        families: tuple[FamilyView, ...],
        component_by_person: dict[UUID, int],
    ) -> nx.DiGraph:
        graph = nx.DiGraph()
        graph.add_nodes_from(components)
        for family in families:
            for child_id in family.child_ids:
                child_component_id = component_by_person[child_id]
                if child_component_id != family.parent_component_id:
                    graph.add_edge(family.parent_component_id, child_component_id)
        if not nx.is_directed_acyclic_graph(graph):
            cycle = nx.find_cycle(graph)
            raise ValueError(f"Component genealogy contains a cycle: {cycle!r}")
        return graph

    @staticmethod
    def _family_source_offset(
        parent_ids: tuple[UUID, ...],
        component: PartnerComponent,
    ) -> float:
        if len(parent_ids) == 1:
            return component.person_offsets[parent_ids[0]]

        ordered = sorted(parent_ids, key=lambda person_id: component.person_offsets[person_id])
        left_id, right_id = ordered[0], ordered[-1]
        left_edge = (
            component.person_offsets[left_id]
            + component.person_boxes[left_id].width / 2
        )
        right_edge = (
            component.person_offsets[right_id]
            - component.person_boxes[right_id].width / 2
        )
        return (left_edge + right_edge) / 2

    def _place_components(
        self,
        genealogy: Genealogy,
        components: dict[int, PartnerComponent],
        component_graph: nx.DiGraph,
        component_by_person: dict[UUID, int],
        families: tuple[FamilyView, ...],
    ) -> tuple[dict[int, float], dict[int, int]]:
        levels: dict[int, int] = {}
        for component_id in nx.topological_sort(component_graph):
            predecessors = tuple(component_graph.predecessors(component_id))
            minimum_level = (
                max(levels[parent_id] for parent_id in predecessors) + 1
                if predecessors
                else 0
            )
            manual_level = components[component_id].generation_hint
            if manual_level is not None and manual_level < minimum_level:
                people = ", ".join(
                    genealogy.persons[person_id].name
                    for person_id in components[component_id].person_ids
                )
                raise ValueError(
                    f"Generation {manual_level + 1} for {people} is too early; "
                    f"minimum allowed generation is {minimum_level + 1}"
                )
            levels[component_id] = (
                manual_level if manual_level is not None else minimum_level
            )
        for component_id in components:
            levels.setdefault(component_id, 0)

        manual_layout_requested = any(
            component.generation_hint is not None or component.order_hint is not None
            for component in components.values()
        )

        if (
            not manual_layout_requested
            and max((degree for _, degree in component_graph.in_degree()), default=0) <= 1
        ):
            tree_centers = self._place_tree_components(
                genealogy,
                components,
                component_graph,
                component_by_person,
                families,
            )
            tree_centers = self._realign_single_child_components(
                genealogy,
                components,
                component_graph,
                component_by_person,
                families,
                levels,
                tree_centers,
            )
            return tree_centers, levels

        by_level: dict[int, list[int]] = defaultdict(list)
        for component_id, level in levels.items():
            by_level[level].append(component_id)
        for component_ids in by_level.values():
            component_ids.sort(key=lambda item: components[item].min_source_row)
            self._apply_manual_component_order(component_ids, components)

        self._validate_manual_orders(by_level, components, genealogy)

        max_level = max(by_level, default=0)

        # Order every generation by the position of its immediate ancestors.
        # Children of the same family retain workbook order, while unrelated
        # branches stay close to the parent they continue from.
        order_index = {
            component_id: index
            for level in range(max_level + 1)
            for index, component_id in enumerate(by_level[level])
        }
        for level in range(1, max_level + 1):
            by_level[level].sort(
                key=lambda component_id: (
                    self._neighbor_barycenter(
                        component_graph.predecessors(component_id),
                        order_index,
                    ),
                    components[component_id].min_source_row,
                )
            )
            self._apply_manual_component_order(by_level[level], components)
            for index, component_id in enumerate(by_level[level]):
                order_index[component_id] = index

        centers: dict[int, float] = {}
        for level in range(max_level + 1):
            cursor = 0.0
            for component_id in by_level[level]:
                width = components[component_id].width
                centers[component_id] = cursor + width / 2
                cursor += width + self.COMPONENT_GAP
            if by_level[level]:
                layer_width = cursor - self.COMPONENT_GAP
                for component_id in by_level[level]:
                    centers[component_id] -= layer_width / 2

        constraints_forward: dict[int, list[tuple[int, float]]] = defaultdict(list)
        constraints_backward: dict[int, list[tuple[int, float]]] = defaultdict(list)

        # Align a child group around the actual family source (the centre of
        # the marriage gap, or the centre of a single parent). This is more
        # stable than averaging independent parent-child edges. In particular,
        # an only child is placed directly below the source, which removes the
        # small staircase-shaped connectors visible in earlier builds.
        for family in families:
            parent_component_id = family.parent_component_id
            ordered_children = sorted(
                family.child_ids,
                key=lambda child_id: (
                    levels.get(component_by_person[child_id], 0),
                    order_index.get(component_by_person[child_id], math.inf),
                    genealogy.persons[child_id].source_key.row_number,
                ),
            )
            child_items: list[tuple[UUID, int, float]] = []
            seen_components: set[int] = set()
            for child_id in ordered_children:
                child_component_id = component_by_person[child_id]
                if (
                    child_component_id == parent_component_id
                    or child_component_id in seen_components
                ):
                    continue
                seen_components.add(child_component_id)
                child_items.append(
                    (
                        child_id,
                        child_component_id,
                        components[child_component_id].width,
                    )
                )

            if not child_items:
                continue

            group_width = sum(item[2] for item in child_items)
            group_width += self.COMPONENT_GAP * max(0, len(child_items) - 1)
            cursor = -group_width / 2
            for child_id, child_component_id, child_width in child_items:
                slot_offset = cursor + child_width / 2
                child_person_offset = components[child_component_id].person_offsets[child_id]
                delta = family.source_offset + slot_offset - child_person_offset
                constraints_forward[child_component_id].append(
                    (parent_component_id, delta)
                )
                constraints_backward[parent_component_id].append(
                    (child_component_id, -delta)
                )
                cursor += child_width + self.COMPONENT_GAP

        for _ in range(12):
            for level in range(1, max_level + 1):
                desired: dict[int, float] = {}
                for component_id in by_level[level]:
                    values = [
                        centers[parent_id] + delta
                        for parent_id, delta in constraints_forward.get(component_id, [])
                    ]
                    desired[component_id] = (
                        sum(values) / len(values) if values else centers[component_id]
                    )
                self._pack_layer(
                    by_level[level],
                    desired,
                    centers,
                    components,
                )

            for level in range(max_level - 1, -1, -1):
                desired = {}
                for component_id in by_level[level]:
                    values = [
                        centers[child_id] + delta
                        for child_id, delta in constraints_backward.get(component_id, [])
                    ]
                    desired[component_id] = (
                        sum(values) / len(values) if values else centers[component_id]
                    )
                self._pack_layer(
                    by_level[level],
                    desired,
                    centers,
                    components,
                )

        centers = self._realign_single_child_components(
            genealogy,
            components,
            component_graph,
            component_by_person,
            families,
            levels,
            centers,
        )
        return centers, levels

    def _realign_single_child_components(
        self,
        genealogy: Genealogy,
        components: dict[int, PartnerComponent],
        component_graph: nx.DiGraph,
        component_by_person: dict[UUID, int],
        families: tuple[FamilyView, ...],
        levels: dict[int, int],
        centers: dict[int, float],
    ) -> dict[int, float]:
        adjusted = dict(centers)

        for family in families:
            ordered_children = [
                child_id
                for child_id in sorted(
                    family.child_ids,
                    key=lambda child_id: (
                        genealogy.persons[child_id].layout_hint.order is None,
                        genealogy.persons[child_id].layout_hint.order or math.inf,
                        genealogy.persons[child_id].source_key.row_number,
                    ),
                )
                if component_by_person[child_id] != family.parent_component_id
            ]
            if not ordered_children:
                continue

            unique_child_components: list[tuple[int, UUID]] = []
            seen_components: set[int] = set()
            for child_id in ordered_children:
                child_component_id = component_by_person[child_id]
                if child_component_id in seen_components:
                    continue
                seen_components.add(child_component_id)
                unique_child_components.append((child_component_id, child_id))

            if len(unique_child_components) != 1:
                continue

            child_component_id, anchor_child_id = unique_child_components[0]
            if component_graph.in_degree(child_component_id) != 1:
                continue

            desired_center = (
                adjusted[family.parent_component_id]
                + family.source_offset
                - components[child_component_id].person_offsets[anchor_child_id]
            )
            current_center = adjusted[child_component_id]
            delta = desired_center - current_center
            if math.isclose(delta, 0.0, abs_tol=0.8):
                continue
            if abs(delta) > self.SINGLE_CHILD_SNAP_MAX:
                continue

            child_width = components[child_component_id].width
            level = levels.get(child_component_id, 0)
            min_delta = -math.inf
            max_delta = math.inf
            for other_component_id, other_center in adjusted.items():
                if other_component_id == child_component_id:
                    continue
                if levels.get(other_component_id, 0) != level:
                    continue
                if other_component_id in nx.descendants(component_graph, child_component_id):
                    continue
                other_width = components[other_component_id].width
                minimum_gap = (child_width + other_width) / 2 + self.COMPONENT_GAP
                offset = other_center - current_center
                if offset < 0:
                    min_delta = max(min_delta, offset + minimum_gap)
                else:
                    max_delta = min(max_delta, offset - minimum_gap)

            clamped_delta = min(max(delta, min_delta), max_delta)
            if math.isclose(clamped_delta, 0.0, abs_tol=0.8):
                continue

            subtree = nx.descendants(component_graph, child_component_id) | {child_component_id}
            for component_id in subtree:
                adjusted[component_id] += clamped_delta

        return adjusted

    def _place_tree_components(
        self,
        genealogy: Genealogy,
        components: dict[int, PartnerComponent],
        component_graph: nx.DiGraph,
        component_by_person: dict[UUID, int],
        families: tuple[FamilyView, ...],
    ) -> dict[int, float]:
        """Compact rooted-tree layout using depth contours.

        Sibling subtrees are separated only on generations where both actually
        contain people. A short side branch therefore does not reserve empty
        width all the way to the bottom of the page. This is the key difference
        from a simple subtree-width layout and keeps large trees such as the
        Carolingians readable on A4.
        """

        families_by_parent: dict[int, list[FamilyView]] = defaultdict(list)
        incoming_anchor: dict[int, float] = {}

        for family in families:
            families_by_parent[family.parent_component_id].append(family)
            for child_id in family.child_ids:
                child_component_id = component_by_person[child_id]
                if child_component_id == family.parent_component_id:
                    continue
                incoming_anchor.setdefault(
                    child_component_id,
                    components[child_component_id].person_offsets[child_id],
                )

        for family_list in families_by_parent.values():
            family_list.sort(
                key=lambda family: (
                    family.source_offset,
                    min(
                        genealogy.persons[child_id].source_key.row_number
                        for child_id in family.child_ids
                    ),
                )
            )

        # A layout is (component anchor positions, horizontal contours by depth).
        # All coordinates are relative to the incoming person's anchor.
        cache: dict[
            int,
            tuple[dict[int, float], dict[int, tuple[float, float]]],
        ] = {}

        @staticmethod
        def shift_layout(
            positions: dict[int, float],
            contours: dict[int, tuple[float, float]],
            dx: float,
            depth_offset: int = 0,
        ) -> tuple[dict[int, float], dict[int, tuple[float, float]]]:
            return (
                {component_id: x + dx for component_id, x in positions.items()},
                {
                    depth + depth_offset: (left + dx, right + dx)
                    for depth, (left, right) in contours.items()
                },
            )

        @staticmethod
        def required_shift(
            occupied: dict[int, tuple[float, float]],
            incoming: dict[int, tuple[float, float]],
            gap: float,
        ) -> float:
            shift = 0.0
            for depth in occupied.keys() & incoming.keys():
                shift = max(
                    shift,
                    occupied[depth][1] + gap - incoming[depth][0],
                )
            return max(0.0, shift)

        @staticmethod
        def merge_contours(
            target: dict[int, tuple[float, float]],
            incoming: dict[int, tuple[float, float]],
        ) -> None:
            for depth, (left, right) in incoming.items():
                if depth in target:
                    old_left, old_right = target[depth]
                    target[depth] = (min(old_left, left), max(old_right, right))
                else:
                    target[depth] = (left, right)

        def build(component_id: int) -> tuple[dict[int, float], dict[int, tuple[float, float]]]:
            if component_id in cache:
                positions, contours = cache[component_id]
                return dict(positions), dict(contours)

            component = components[component_id]
            anchor_offset = incoming_anchor.get(component_id, 0.0)
            component_left = min(
                component.person_offsets[person_id]
                - anchor_offset
                - component.person_boxes[person_id].width / 2
                for person_id in component.person_ids
            )
            component_right = max(
                component.person_offsets[person_id]
                - anchor_offset
                + component.person_boxes[person_id].width / 2
                for person_id in component.person_ids
            )

            positions: dict[int, float] = {component_id: 0.0}
            contours: dict[int, tuple[float, float]] = {
                0: (component_left, component_right)
            }

            family_groups: list[
                tuple[float, dict[int, float], dict[int, tuple[float, float]]]
            ] = []
            for family in families_by_parent.get(component_id, []):
                seen: set[int] = set()
                child_layouts: list[
                    tuple[
                        int,
                        dict[int, float],
                        dict[int, tuple[float, float]],
                    ]
                ] = []
                for child_id in sorted(
                    family.child_ids,
                    key=lambda item: genealogy.persons[item].source_key.row_number,
                ):
                    child_component_id = component_by_person[child_id]
                    if child_component_id == component_id or child_component_id in seen:
                        continue
                    seen.add(child_component_id)
                    child_positions, child_contours = build(child_component_id)
                    child_layouts.append(
                        (child_component_id, child_positions, child_contours)
                    )

                if not child_layouts:
                    continue

                group_positions: dict[int, float] = {}
                group_contours: dict[int, tuple[float, float]] = {}
                child_anchor_positions: list[float] = []
                for child_component_id, child_positions, child_contours in child_layouts:
                    dx = (
                        0.0
                        if not group_contours
                        else required_shift(
                            group_contours,
                            child_contours,
                            self.COMPONENT_GAP,
                        )
                    )
                    shifted_positions, shifted_contours = shift_layout(
                        child_positions,
                        child_contours,
                        dx,
                    )
                    group_positions.update(shifted_positions)
                    merge_contours(group_contours, shifted_contours)
                    child_anchor_positions.append(
                        shifted_positions[child_component_id]
                    )

                desired_center = family.source_offset - anchor_offset
                anchor_span_center = (
                    min(child_anchor_positions) + max(child_anchor_positions)
                ) / 2
                group_shift = desired_center - anchor_span_center
                group_positions, group_contours = shift_layout(
                    group_positions,
                    group_contours,
                    group_shift,
                )
                family_groups.append(
                    (desired_center, group_positions, group_contours)
                )

            # Different marriages of the same person may create separate child
            # groups. Pack those groups by their full depth contours while
            # keeping their preferred order around each marriage source.
            family_groups.sort(key=lambda item: item[0])
            placed_family_contours: dict[int, tuple[float, float]] = {}
            for _desired, group_positions, group_contours in family_groups:
                dx = required_shift(
                    placed_family_contours,
                    group_contours,
                    self.COMPONENT_GAP,
                )
                shifted_positions, shifted_contours = shift_layout(
                    group_positions,
                    group_contours,
                    dx,
                    depth_offset=1,
                )
                positions.update(shifted_positions)
                merge_contours(contours, shifted_contours)
                merge_contours(placed_family_contours, group_contours if dx == 0 else {
                    depth: (left + dx, right + dx)
                    for depth, (left, right) in group_contours.items()
                })

            cache[component_id] = (dict(positions), dict(contours))
            return positions, contours

        roots = sorted(
            (
                component_id
                for component_id in components
                if component_graph.in_degree(component_id) == 0
            ),
            key=lambda component_id: components[component_id].min_source_row,
        )

        global_positions: dict[int, float] = {}
        global_contours: dict[int, tuple[float, float]] = {}
        for root_id in roots:
            root_positions, root_contours = build(root_id)
            dx = (
                0.0
                if not global_contours
                else required_shift(
                    global_contours,
                    root_contours,
                    self.COMPONENT_GAP * 2,
                )
            )
            shifted_positions, shifted_contours = shift_layout(
                root_positions,
                root_contours,
                dx,
            )
            global_positions.update(shifted_positions)
            merge_contours(global_contours, shifted_contours)

        for component_id in components:
            if component_id not in global_positions:
                root_positions, root_contours = build(component_id)
                dx = required_shift(
                    global_contours,
                    root_contours,
                    self.COMPONENT_GAP * 2,
                )
                shifted_positions, shifted_contours = shift_layout(
                    root_positions,
                    root_contours,
                    dx,
                )
                global_positions.update(shifted_positions)
                merge_contours(global_contours, shifted_contours)

        return {
            component_id: anchor_x - incoming_anchor.get(component_id, 0.0)
            for component_id, anchor_x in global_positions.items()
        }

    @staticmethod
    def _neighbor_barycenter(neighbors, order_index: dict[int, int]) -> float:
        values = [order_index[item] for item in neighbors if item in order_index]
        return sum(values) / len(values) if values else math.inf

    @staticmethod
    def _apply_manual_component_order(
        ordered_ids: list[int],
        components: dict[int, PartnerComponent],
    ) -> None:
        """Apply manual order as a partial constraint.

        Unnumbered components keep their automatic positions. Numbered
        components are reordered only among the slots already occupied by
        numbered components. Therefore one or two optional hints do not drag all
        automatic branches to an arbitrary side, while a fully numbered layer
        receives an exact left-to-right order.
        """

        manual_slots = [
            index
            for index, component_id in enumerate(ordered_ids)
            if components[component_id].order_hint is not None
        ]
        manual_ids = sorted(
            (ordered_ids[index] for index in manual_slots),
            key=lambda component_id: (
                components[component_id].order_hint,
                components[component_id].min_source_row,
            ),
        )
        for index, component_id in zip(manual_slots, manual_ids):
            ordered_ids[index] = component_id

    @staticmethod
    def _validate_manual_orders(
        by_level: dict[int, list[int]],
        components: dict[int, PartnerComponent],
        genealogy: Genealogy,
    ) -> None:
        for level, component_ids in by_level.items():
            by_order: dict[int, list[int]] = defaultdict(list)
            for component_id in component_ids:
                order = components[component_id].order_hint
                if order is not None:
                    by_order[order].append(component_id)

            duplicates = {
                order: ids for order, ids in by_order.items() if len(ids) > 1
            }
            if not duplicates:
                continue

            details: list[str] = []
            for order, ids in sorted(duplicates.items()):
                names = [
                    "/".join(
                        genealogy.persons[person_id].name
                        for person_id in components[component_id].person_ids
                    )
                    for component_id in ids
                ]
                details.append(f"{order}: {', '.join(names)}")
            raise ValueError(
                f"Duplicate order values in generation {level + 1}: "
                + "; ".join(details)
            )

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
                center = max(
                    center,
                    previous_right + self.COMPONENT_GAP + width / 2,
                )
            placed[component_id] = center
            previous_right = center + width / 2

        next_left: float | None = None
        for component_id in reversed(ordered_ids):
            width = components[component_id].width
            center = placed[component_id]
            if next_left is not None:
                center = min(
                    center,
                    next_left - self.COMPONENT_GAP - width / 2,
                )
            placed[component_id] = center
            next_left = center - width / 2

        shifts = [desired[item] - placed[item] for item in ordered_ids]
        shifts.sort()
        shift = shifts[len(shifts) // 2]
        for component_id in ordered_ids:
            centers[component_id] = placed[component_id] + shift

    def _place_people(
        self,
        components: dict[int, PartnerComponent],
        component_centers: dict[int, float],
        levels: dict[int, int],
    ) -> tuple[dict[UUID, PersonPosition], float, float]:
        level_heights: dict[int, float] = defaultdict(float)
        for component_id, component in components.items():
            level_heights[levels.get(component_id, 0)] = max(
                level_heights[levels.get(component_id, 0)],
                component.height,
            )

        level_top: dict[int, float] = {}
        current_y = self.PAGE_MARGIN_Y + self.TITLE_AREA
        for level in range(max(level_heights, default=0) + 1):
            level_top[level] = current_y
            current_y += level_heights[level] + self.LAYER_GAP

        positions: dict[UUID, PersonPosition] = {}
        min_x = math.inf
        max_x = -math.inf
        for component_id, component in components.items():
            center_x = component_centers[component_id]
            level = levels.get(component_id, 0)
            for person_id in component.person_ids:
                box = component.person_boxes[person_id]
                # Top-align a generation. Names then share a baseline and
                # marriage lines do not rise or fall through neighbouring text.
                top_y = level_top[level]
                person_center = center_x + component.person_offsets[person_id]
                positions[person_id] = PersonPosition(
                    center_x=person_center,
                    top_y=top_y,
                    width=box.width,
                    height=box.height,
                )
                min_x = min(min_x, person_center - box.width / 2)
                max_x = max(max_x, person_center + box.width / 2)

        if not positions:
            raise ValueError("Genealogy has no persons")

        content_width = max_x - min_x
        page_height = current_y - self.LAYER_GAP + self.PAGE_MARGIN_Y

        # When the tree is much taller than it is wide, spread existing
        # branches horizontally before creating the page. Text boxes keep their
        # size; only the whitespace between branches grows. This uses an A4
        # landscape page far more effectively without turning a single lineage
        # into an artificial zig-zag.
        desired_content_width = max(
            content_width,
            page_height * self.MIN_LANDSCAPE_RATIO - self.PAGE_MARGIN_X * 2,
        )
        if content_width > 0:
            horizontal_stretch = min(
                self.MAX_HORIZONTAL_STRETCH,
                desired_content_width / content_width,
            )
        else:
            horizontal_stretch = 1.0

        content_center = (min_x + max_x) / 2
        if horizontal_stretch > 1.001:
            positions = {
                person_id: PersonPosition(
                    center_x=(
                        (position.center_x - content_center)
                        * horizontal_stretch
                        + content_center
                    ),
                    top_y=position.top_y,
                    width=position.width,
                    height=position.height,
                )
                for person_id, position in positions.items()
            }
            min_x = min(position.left for position in positions.values())
            max_x = max(position.right for position in positions.values())
            content_width = max_x - min_x

        page_width = max(
            content_width + self.PAGE_MARGIN_X * 2,
            self.MIN_PAGE_WIDTH,
            page_height * self.MIN_LANDSCAPE_RATIO,
        )
        shift_x = (page_width - content_width) / 2 - min_x
        shifted = {
            person_id: PersonPosition(
                center_x=position.center_x + shift_x,
                top_y=position.top_y,
                width=position.width,
                height=position.height,
            )
            for person_id, position in positions.items()
        }
        return shifted, page_width, page_height

    def _order_partner_component(
        self,
        genealogy: Genealogy,
        person_ids: set[UUID],
    ) -> tuple[UUID, ...]:
        source_order = tuple(
            sorted(
                person_ids,
                key=lambda person_id: (
                    genealogy.persons[person_id].source_key.row_number
                ),
            )
        )
        manually_ordered = list(source_order)
        manual_slots = [
            index
            for index, person_id in enumerate(manually_ordered)
            if genealogy.persons[person_id].layout_hint.order is not None
        ]
        manual_ids = sorted(
            (manually_ordered[index] for index in manual_slots),
            key=lambda person_id: (
                genealogy.persons[person_id].layout_hint.order,
                genealogy.persons[person_id].source_key.row_number,
            ),
        )
        for index, person_id in zip(manual_slots, manual_ids):
            manually_ordered[index] = person_id
        source_order = tuple(manually_ordered)

        if len(source_order) <= 2 or len(source_order) > 7:
            return source_order

        edges = {
            frozenset((marriage.spouse_a_id, marriage.spouse_b_id))
            for marriage in genealogy.marriages
            if marriage.spouse_a_id in person_ids and marriage.spouse_b_id in person_ids
        }
        source_index = {person_id: index for index, person_id in enumerate(source_order)}

        manual_people = [
            person_id
            for person_id in source_order
            if genealogy.persons[person_id].layout_hint.order is not None
        ]
        manual_pairs = [
            (left_id, right_id)
            for left_index, left_id in enumerate(manual_people)
            for right_id in manual_people[left_index + 1 :]
            if genealogy.persons[left_id].layout_hint.order
            < genealogy.persons[right_id].layout_hint.order
        ]

        def score(order: tuple[UUID, ...]) -> tuple[int, int, int, tuple[int, ...]]:
            index = {person_id: position for position, person_id in enumerate(order)}
            manual_violations = sum(
                index[left_id] > index[right_id]
                for left_id, right_id in manual_pairs
            )
            marriage_span = 0
            for pair in edges:
                a, b = tuple(pair)
                marriage_span += abs(index[a] - index[b])
            displacement = sum(
                abs(index[person_id] - source_index[person_id])
                for person_id in order
            )
            lexical = tuple(source_index[person_id] for person_id in order)
            return manual_violations, marriage_span, displacement, lexical

        return min(permutations(source_order), key=score)

    def _person_box(self, person: Person) -> PersonBox:
        return self._labels.measure(person)


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
