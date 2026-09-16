"""Planarity-aware post-processing for the readable orthogonal layout.

The workbook's ``order`` column is useful for birth order inside one sibling
family, but a numeric value on an unrelated cousin must not force two ancestry
branches to cross. The base layout remains responsible for component sizing,
generation placement and manual partner orientation. This pass only chooses a
safer left-to-right order for components that share a generation.
"""
from __future__ import annotations

from collections import defaultdict
from heapq import heappop, heappush


def install_planar_readable_layout() -> None:
    """Install planarity-aware layout and a bounded row-local route search."""

    from historical_bloodlines.infrastructure.graph import readable_renderer
    from historical_bloodlines.infrastructure.graph.connector_routing import (
        OrthogonalConnectorRouter,
        RoutingConflict,
    )

    base = readable_renderer._ReadableOrthogonalGenealogyLayout
    if getattr(base, "_planar_ancestry_ordering", False):
        return

    class _PlanarReadableOrthogonalGenealogyLayout(base):
        _planar_ancestry_ordering = True

        @staticmethod
        def _sibling_precedence(
            genealogy,
            families,
            component_by_person,
            level,
            levels,
        ):
            """Return hard precedence only for explicitly ordered siblings."""

            edges = set()
            for family in families:
                ordered = []
                seen = set()
                for child_id in family.child_ids:
                    component_id = component_by_person[child_id]
                    if component_id in seen or levels[component_id] != level:
                        continue
                    seen.add(component_id)
                    order = genealogy.persons[child_id].layout_hint.order
                    if order is not None:
                        ordered.append((order, component_id))
                ordered.sort()
                for (_, left_id), (_, right_id) in zip(ordered, ordered[1:]):
                    if left_id != right_id:
                        edges.add((left_id, right_id))
            return edges

        @staticmethod
        def _topological_row_order(row, desired, precedence, fallback):
            outgoing = defaultdict(set)
            indegree = {component_id: 0 for component_id in row}
            row_set = set(row)
            for left_id, right_id in precedence:
                if left_id not in row_set or right_id not in row_set:
                    continue
                if right_id in outgoing[left_id]:
                    continue
                outgoing[left_id].add(right_id)
                indegree[right_id] += 1

            queue = []
            serial = 0
            for component_id in row:
                if indegree[component_id] == 0:
                    heappush(
                        queue,
                        (
                            desired.get(component_id, fallback[component_id]),
                            fallback[component_id],
                            serial,
                            component_id,
                        ),
                    )
                    serial += 1

            result = []
            while queue:
                _, _, _, component_id = heappop(queue)
                result.append(component_id)
                for next_id in outgoing[component_id]:
                    indegree[next_id] -= 1
                    if indegree[next_id] == 0:
                        heappush(
                            queue,
                            (
                                desired.get(next_id, fallback[next_id]),
                                fallback[next_id],
                                serial,
                                next_id,
                            ),
                        )
                        serial += 1
            return result if len(result) == len(row) else list(row)

        def _place_components(
            self,
            genealogy,
            components,
            component_graph,
            component_by_person,
            families,
        ):
            centers, levels = super()._place_components(
                genealogy,
                components,
                component_graph,
                component_by_person,
                families,
            )

            rows = defaultdict(list)
            for component_id, level in levels.items():
                rows[level].append(component_id)
            for row in rows.values():
                row.sort(key=lambda component_id: centers[component_id])

            incoming = defaultdict(list)
            for family in families:
                parent_component = family.parent_component_id
                for child_id in family.child_ids:
                    child_component = component_by_person[child_id]
                    if child_component == parent_component:
                        continue
                    incoming[child_component].append(
                        (
                            parent_component,
                            family.source_offset,
                            components[child_component].person_offsets[child_id],
                        )
                    )

            first_level = min(rows, default=0)
            for _ in range(4):
                changed = False
                for level in sorted(rows):
                    if level == first_level:
                        continue
                    row = rows[level]
                    fallback = {
                        component_id: centers[component_id]
                        for component_id in row
                    }
                    desired = {}
                    for component_id in row:
                        values = [
                            centers[parent_component]
                            + source_offset
                            - child_offset
                            for parent_component, source_offset, child_offset
                            in incoming.get(component_id, ())
                        ]
                        desired[component_id] = (
                            sum(values) / len(values)
                            if values
                            else centers[component_id]
                        )

                    precedence = self._sibling_precedence(
                        genealogy,
                        families,
                        component_by_person,
                        level,
                        levels,
                    )
                    ordered = self._topological_row_order(
                        row,
                        desired,
                        precedence,
                        fallback,
                    )
                    if ordered != row:
                        changed = True
                    rows[level] = ordered
                    self._pack_layer(
                        ordered,
                        desired,
                        centers,
                        components,
                    )
                if not changed:
                    break

            for level, row in rows.items():
                for left_id, right_id in zip(row, row[1:]):
                    minimum = (
                        components[left_id].width / 2
                        + components[right_id].width / 2
                        + self.COMPONENT_GAP
                    )
                    if centers[right_id] - centers[left_id] < minimum - 1e-5:
                        raise ValueError(
                            f"Planar row packing overlapped generation {level + 1}"
                        )
            return centers, levels

    def _bounded_plan(self):
        """Solve one target row at a time after layout removes branch reversals."""

        self.search_count = 0
        routes = []
        by_target_row = defaultdict(list)
        for family in self.families:
            target_row = round(min(y for _, y in self.targets(family)), 5)
            by_target_row[target_row].append(family)

        last_blocked = None
        for target_row in sorted(by_target_row):
            group = tuple(
                sorted(by_target_row[target_row], key=self._family_priority)
            )
            states = 0

            def search(remaining, local):
                nonlocal states, last_blocked
                states += 1
                if states > 4000:
                    return None
                if not remaining:
                    return list(local)

                occupied = [*routes, *local]
                options = []
                for family in remaining:
                    candidates = self._route_candidates(family, occupied)
                    if not candidates:
                        last_blocked = family
                        return None
                    options.append(
                        (
                            len(candidates),
                            self._family_priority(family),
                            family,
                            candidates,
                        )
                    )

                for _, _, family, candidates in sorted(
                    options,
                    key=lambda item: (item[0], item[1]),
                ):
                    rest = tuple(item for item in remaining if item is not family)
                    for route in candidates[:8]:
                        result = search(rest, [*local, route])
                        if result is not None:
                            return result
                return None

            planned = search(group, [])
            if planned is None:
                family = last_blocked or group[0]
                raise RoutingConflict(
                    family,
                    "No downward, collision-free route satisfies the planar "
                    "generation layout after bounded row backtracking",
                )
            routes.extend(planned)

        issues = self.issues(routes)
        if issues:
            raise ValueError(f"Unsafe connector plan: {issues[0]!r}")
        return tuple(routes)

    readable_renderer._ReadableOrthogonalGenealogyLayout = (
        _PlanarReadableOrthogonalGenealogyLayout
    )
    OrthogonalConnectorRouter.plan = _bounded_plan
