"""Joint horizontal constraints for people and through-generation line corridors.

One-child alignments are solved before rendering, not approximated by moving
an endpoint inside a label. Explicit row order and non-overlap remain hard
constraints. Space is reserved for long links instead of hiding them under text.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math

import networkx as nx

from historical_bloodlines.infrastructure.graph.constraint_solver import constrained_positions
from historical_bloodlines.infrastructure.graph.layout import FixedGenealogyLayout
from historical_bloodlines.infrastructure.graph.models import PersonPosition


@dataclass(frozen=True)
class _Item:
    component: int
    left: float
    right: float


class _Potentials:
    def __init__(self, keys):
        self.parent = {key: key for key in keys}
        self.offset = {key: 0.0 for key in keys}

    def find(self, key):
        parent = self.parent[key]
        if parent != key:
            root, delta = self.find(parent)
            self.offset[key] += delta
            self.parent[key] = root
        return self.parent[key], self.offset[key]

    def join(self, a, b, delta):
        # x_b = x_a + delta
        ra, da = self.find(a)
        rb, db = self.find(b)
        if ra == rb:
            return abs(db - da - delta) < 1e-6
        self.parent[rb] = ra
        self.offset[rb] = da + delta - db
        return True


class OrthogonalGenealogyLayout(FixedGenealogyLayout):
    CORRIDOR_HALF_WIDTH = 9.0

    def _build_partner_components(self, genealogy):
        components, by_person = super()._build_partner_components(genealogy)
        child_groups = defaultdict(set)
        graph = nx.DiGraph()
        graph.add_nodes_from(components)
        for relation in genealogy.family_child_relations:
            child_groups[relation.parent_ids].add(relation.child_id)
            for parent in relation.parent_ids:
                a = by_person[parent]
                b = by_person[relation.child_id]
                if a != b:
                    graph.add_edge(a, b)
        if not nx.is_directed_acyclic_graph(graph):
            return components, by_person

        levels = {}
        for component_id in nx.topological_sort(graph):
            minimum = max(
                (levels[parent_id] + 1 for parent_id in graph.predecessors(component_id)),
                default=0,
            )
            levels[component_id] = max(
                minimum,
                components[component_id].generation_hint or 0,
            )

        incoming = defaultdict(list)
        for parents, children in child_groups.items():
            if len(children) != 1:
                continue
            child = next(iter(children))
            parent_component = by_person[next(iter(parents))]
            source_offset = self._family_source_offset(
                tuple(parents),
                components[parent_component],
            )
            incoming[child].append((parent_component, source_offset))

        # If two spouses each have a known single-parent ancestor in the same
        # generation, their gap must be wide enough for both ancestor labels to
        # stay on their child's exact vertical axis. Expand only the marriage
        # component; never compress text or fake a short dogleg.
        for component in components.values():
            people = component.person_ids
            if len(people) < 2:
                continue
            gaps = [self.PERSON_GAP] * (len(people) - 1)
            for i, left_person in enumerate(people):
                for j, right_person in enumerate(people[i + 1 :], i + 1):
                    for left_parent, left_source in incoming[left_person]:
                        for right_parent, right_source in incoming[right_person]:
                            if (
                                left_parent == right_parent
                                or levels[left_parent] != levels[right_parent]
                            ):
                                continue
                            required = (
                                (components[left_parent].width + components[right_parent].width)
                                / 2
                                + self.COMPONENT_GAP
                                + right_source
                                - left_source
                            )
                            current = (
                                component.person_boxes[left_person].width
                                + component.person_boxes[right_person].width
                            ) / 2
                            current += sum(
                                component.person_boxes[person_id].width
                                for person_id in people[i + 1 : j]
                            ) + sum(gaps[i:j])
                            if required > current:
                                gaps[j - 1] += required - current

            width = sum(box.width for box in component.person_boxes.values()) + sum(gaps)
            cursor = -width / 2
            for index, person_id in enumerate(people):
                box = component.person_boxes[person_id]
                component.person_offsets[person_id] = cursor + box.width / 2
                cursor += box.width + (gaps[index] if index < len(gaps) else 0)
            component.width = width

        return components, by_person

    def _place_components(
        self,
        genealogy,
        components,
        component_graph,
        component_by_person,
        families,
    ):
        # The base layout supplies the established partial/manual ordering. Its
        # coordinates are only reference values for the convex objective.
        original, levels = super()._place_components(
            genealogy,
            components,
            component_graph,
            component_by_person,
            families,
        )
        rows = defaultdict(list)
        for component_id, level in levels.items():
            rows[level].append(component_id)
        for ids in rows.values():
            ids.sort(key=lambda component_id: (
                original[component_id],
                components[component_id].min_source_row,
            ))

        # A childless automatically ordered side branch must not split the two
        # ancestors of a married pair. This fixes cases such as Baldwin between
        # Henry VII and Wenceslaus II while respecting explicit order hints.
        incoming = defaultdict(list)
        for family in families:
            if len(family.child_ids) == 1:
                child = family.child_ids[0]
                incoming[component_by_person[child]].append(
                    (child, family.parent_component_id)
                )
        for child_component, entries in incoming.items():
            entries.sort(
                key=lambda item: components[child_component].person_offsets[item[0]]
            )
            for (_, left_parent), (_, right_parent) in zip(entries, entries[1:]):
                if (
                    left_parent == right_parent
                    or levels[left_parent] != levels[right_parent]
                ):
                    continue
                ids = rows[levels[left_parent]]
                left_index = ids.index(left_parent)
                right_index = ids.index(right_parent)
                if left_index >= right_index:
                    continue
                middle = ids[left_index + 1 : right_index]
                if middle and all(
                    components[component_id].order_hint is None
                    and component_graph.out_degree(component_id) == 0
                    for component_id in middle
                ):
                    old_xs = sorted(original[component_id] for component_id in ids)
                    ids[:] = (
                        ids[:left_index]
                        + middle
                        + [left_parent, right_parent]
                        + ids[right_index + 1 :]
                    )
                    for component_id, x in zip(ids, old_xs):
                        original[component_id] = x

        inequalities = []
        for ids in rows.values():
            for left_id, right_id in zip(ids, ids[1:]):
                inequalities.append(
                    (
                        left_id,
                        right_id,
                        (components[left_id].width + components[right_id].width) / 2
                        + self.COMPONENT_GAP,
                    )
                )

        accepted = []
        candidates = []
        for family in families:
            if len(family.child_ids) != 1:
                continue
            child = family.child_ids[0]
            parent_component = family.parent_component_id
            child_component = component_by_person[child]
            if parent_component == child_component:
                continue
            delta = (
                family.source_offset
                - components[child_component].person_offsets[child]
            )
            priority = (
                component_graph.in_degree(parent_component) != 0,
                levels[child_component] - levels[parent_component],
                components[parent_component].min_source_row,
                components[child_component].min_source_row,
            )
            candidates.append((priority, (parent_component, child_component, delta)))

        # Accept as many exact one-child columns as the row order allows. When
        # an exact column would make the hard ordering infeasible, routing later
        # fails closed instead of drawing a misleading line through another tree.
        for _, alignment in sorted(candidates):
            if self._solve(components, inequalities, [*accepted, alignment]) is not None:
                accepted.append(alignment)

        solution = self._solve(components, inequalities, accepted)
        if solution is None:
            raise ValueError("Inconsistent horizontal layout constraints")
        centers, _, _, _ = solution
        centers = self._optimise(
            components,
            inequalities,
            accepted,
            families,
            component_by_person,
            original,
        )

        # A long descendant link receives an actual empty corridor through every
        # intervening generation. Candidate slots are scored by crossings first,
        # then overall width, then displacement from the natural child axis.
        transit_items = defaultdict(list)
        self.reserved_corridors = []
        long_links = []
        for family in families:
            for child in family.child_ids:
                parent_component = family.parent_component_id
                child_component = component_by_person[child]
                if levels[child_component] - levels[parent_component] > 1:
                    long_links.append(
                        (
                            -(levels[child_component] - levels[parent_component]),
                            components[child_component].min_source_row,
                            family,
                            child,
                        )
                    )

        for _, _, family, child in sorted(long_links, key=lambda item: item[:2]):
            child_component = component_by_person[child]
            offset = components[child_component].person_offsets[child]
            candidate_constraints = list(inequalities)
            additions = []
            feasible = True
            trial_centers = dict(centers)
            for level in range(
                levels[family.parent_component_id] + 1,
                levels[child_component],
            ):
                items = [
                    _Item(
                        component_id,
                        -components[component_id].width / 2,
                        components[component_id].width / 2,
                    )
                    for component_id in rows[level]
                ] + list(transit_items[level])
                items.sort(
                    key=lambda item: (
                        trial_centers[item.component]
                        + (item.left + item.right) / 2
                    )
                )
                preferred_x = trial_centers[child_component] + offset
                slots = []
                for slot in range(len(items) + 1):
                    low = (
                        trial_centers[items[slot - 1].component]
                        + items[slot - 1].right
                        + self.COMPONENT_GAP
                        if slot
                        else -math.inf
                    )
                    high = (
                        trial_centers[items[slot].component]
                        + items[slot].left
                        - self.COMPONENT_GAP
                        if slot < len(items)
                        else math.inf
                    )
                    distance = max(low - preferred_x, preferred_x - high, 0)
                    slots.append((distance, slot))

                options = []
                for _, slot in sorted(slots):
                    extra = []
                    if slot:
                        left_item = items[slot - 1]
                        extra.append(
                            (
                                left_item.component,
                                child_component,
                                left_item.right
                                + self.COMPONENT_GAP
                                + self.CORRIDOR_HALF_WIDTH
                                - offset,
                            )
                        )
                    if slot < len(items):
                        right_item = items[slot]
                        extra.append(
                            (
                                child_component,
                                right_item.component,
                                offset
                                + self.CORRIDOR_HALF_WIDTH
                                + self.COMPONENT_GAP
                                - right_item.left,
                            )
                        )
                    if self._solve(
                        components,
                        [*candidate_constraints, *extra],
                        accepted,
                    ) is None:
                        continue

                    candidate_centers = self._optimise(
                        components,
                        [*candidate_constraints, *extra],
                        accepted,
                        families,
                        component_by_person,
                        original,
                    )
                    x = candidate_centers[child_component] + offset
                    crossings = 0
                    for other in families:
                        if other == family:
                            continue
                        other_level = levels[other.parent_component_id]
                        if not (
                            levels[family.parent_component_id]
                            <= other_level
                            < levels[child_component]
                        ):
                            continue
                        other_xs = [
                            candidate_centers[other.parent_component_id]
                            + other.source_offset
                        ]
                        other_xs.extend(
                            candidate_centers[component_by_person[person_id]]
                            + components[component_by_person[person_id]].person_offsets[person_id]
                            for person_id in other.child_ids
                        )
                        if min(other_xs) + 1e-5 < x < max(other_xs) - 1e-5:
                            crossings += 1
                    content_width = (
                        max(
                            candidate_centers[component_id]
                            + components[component_id].width / 2
                            for component_id in components
                        )
                        - min(
                            candidate_centers[component_id]
                            - components[component_id].width / 2
                            for component_id in components
                        )
                    )
                    options.append(
                        (
                            (
                                crossings,
                                content_width,
                                abs(x - preferred_x),
                                slot,
                            ),
                            extra,
                            candidate_centers,
                        )
                    )

                if not options:
                    feasible = False
                    break
                _, extra, trial_centers = min(options, key=lambda item: item[0])
                candidate_constraints.extend(extra)
                additions.append(
                    (
                        level,
                        _Item(
                            child_component,
                            offset - self.CORRIDOR_HALF_WIDTH,
                            offset + self.CORRIDOR_HALF_WIDTH,
                        ),
                    )
                )

            if feasible:
                inequalities = candidate_constraints
                centers = trial_centers
                for level, item in additions:
                    transit_items[level].append(item)
                self.reserved_corridors.append(child)

        centers = self._optimise(
            components,
            inequalities,
            accepted,
            families,
            component_by_person,
            original,
        )
        self.accepted_alignments = tuple(accepted)
        self.deferred_alignments = tuple(
            item for _, item in sorted(candidates) if item not in accepted
        )
        self.horizontal_constraints = tuple(inequalities)
        self.component_centers = dict(centers)
        return centers, levels

    def _optimise(
        self,
        components,
        inequalities,
        alignments,
        families,
        by_person,
        original,
    ):
        solution = self._solve(components, inequalities, alignments)
        if solution is None:
            raise ValueError("Inconsistent horizontal constraints")
        _, groups, offsets, bounds = solution
        goals = []

        def goal(a, b, delta, weight):
            goals.append(
                (
                    groups[a],
                    groups[b],
                    delta + offsets[a] - offsets[b],
                    weight,
                )
            )

        # Family geometry remains the strong soft objective, while row gaps are
        # compactness hints rather than a hard upper bound.
        for family in families:
            parent_component = family.parent_component_id
            items = []
            seen = set()
            for person_id in sorted(
                family.child_ids,
                key=lambda person_id: original[by_person[person_id]],
            ):
                child_component = by_person[person_id]
                if child_component == parent_component or child_component in seen:
                    continue
                seen.add(child_component)
                items.append((person_id, child_component))
            if not items:
                continue

            cursor = 0.0
            slots = []
            anchors = []
            for person_id, child_component in items:
                center = cursor + components[child_component].width / 2
                slots.append(center)
                anchors.append(
                    center + components[child_component].person_offsets[person_id]
                )
                cursor += components[child_component].width + self.COMPONENT_GAP
            middle = (min(anchors) + max(anchors)) / 2
            for (person_id, child_component), slot in zip(items, slots):
                goal(
                    parent_component,
                    child_component,
                    family.source_offset + slot - middle,
                    1.0,
                )

        for left_id, right_id, distance in inequalities:
            goal(left_id, right_id, distance, 0.08)

        reference = {}
        for component_id in components:
            reference.setdefault(groups[component_id], []).append(
                original[component_id] - offsets[component_id]
            )
        reference = {
            group: sum(values) / len(values)
            for group, values in reference.items()
        }
        positions = constrained_positions(
            set(groups.values()),
            goals,
            bounds,
            reference,
        )
        return {
            component_id: positions[groups[component_id]] + offsets[component_id]
            for component_id in components
        }

    @staticmethod
    def _solve(components, inequalities, alignments):
        potentials = _Potentials(components)
        for left_id, right_id, delta in alignments:
            if not potentials.join(left_id, right_id, delta):
                return None

        groups = {}
        offsets = {}
        for component_id in components:
            groups[component_id], offsets[component_id] = potentials.find(component_id)

        edges = []
        for left_id, right_id, distance in inequalities:
            left_group = groups[left_id]
            right_group = groups[right_id]
            weight = distance + offsets[left_id] - offsets[right_id]
            if left_group == right_group:
                if weight > 1e-5:
                    return None
                continue
            edges.append((left_group, right_group, weight))

        distances = {group: 0.0 for group in set(groups.values())}
        for component_id, component in components.items():
            root = groups[component_id]
            distances[root] = max(
                distances[root],
                component.width / 2 - offsets[component_id],
            )

        for _ in range(len(distances)):
            changed = False
            for left_group, right_group, weight in edges:
                if distances[right_group] < distances[left_group] + weight - 1e-6:
                    distances[right_group] = distances[left_group] + weight
                    changed = True
            if not changed:
                return (
                    {
                        component_id: distances[groups[component_id]] + offsets[component_id]
                        for component_id in components
                    },
                    groups,
                    offsets,
                    edges,
                )
        return None

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
        # The joint solver already owns this constraint. The legacy thresholded
        # subtree translation can reintroduce collisions on other generations.
        return dict(centers)

    def _place_people(self, components, component_centers, levels):
        heights = defaultdict(float)
        for component_id, component in components.items():
            heights[levels[component_id]] = max(
                heights[levels[component_id]],
                component.height,
            )

        tops = {}
        y = self.PAGE_MARGIN_Y + self.TITLE_AREA
        for level in range(max(heights, default=0) + 1):
            tops[level] = y
            y += heights[level] + self.LAYER_GAP

        positions = {}
        for component_id, component in components.items():
            for person_id in component.person_ids:
                box = component.person_boxes[person_id]
                positions[person_id] = PersonPosition(
                    component_centers[component_id] + component.person_offsets[person_id],
                    tops[levels[component_id]],
                    box.width,
                    box.height,
                )
        if not positions:
            raise ValueError("Genealogy has no persons")

        left = min(position.left for position in positions.values())
        right = max(position.right for position in positions.values())
        height = y - self.LAYER_GAP + self.PAGE_MARGIN_Y
        width = max(
            right - left + 2 * self.PAGE_MARGIN_X,
            self.MIN_PAGE_WIDTH,
            height * self.MIN_LANDSCAPE_RATIO,
        )
        shift_x = (width - (right - left)) / 2 - left

        # Deliberately no per-person horizontal stretch. It changes marriage-gap
        # centres relative to fixed box widths and breaks solved alignments.
        return (
            {
                person_id: PersonPosition(
                    position.center_x + shift_x,
                    position.top_y,
                    position.width,
                    position.height,
                )
                for person_id, position in positions.items()
            },
            width,
            height,
        )
