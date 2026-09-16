"""Planarity-aware post-processing for the readable orthogonal layout.

Explicit ``order`` values remain hard left-to-right constraints.  Components
without an order hint may move between those anchors so sibling buses and the
parents of a marriage component stay contiguous whenever the topology permits.
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
        def _manual_precedence(row, components):
            """Preserve the workbook's global order hints exactly."""

            manual = sorted(
                (
                    (components[component_id].order_hint, component_id)
                    for component_id in row
                    if components[component_id].order_hint is not None
                ),
                key=lambda item: item[0],
            )
            return {
                (left_id, right_id)
                for (_, left_id), (_, right_id) in zip(manual, manual[1:])
            }

        @staticmethod
        def _topology_blocks(
            row,
            families,
            component_by_person,
            level,
            levels,
        ):
            """Return components that must stay contiguous for a planar tree.

            Two structures form a block:
            * children sharing one multi-child family bus;
            * same-level parent components whose children are spouses inside one
              partner component.  The latter is what keeps two ancestry branches
              adjacent before they join in a marriage component.
            """

            parent = {component_id: component_id for component_id in row}
            row_set = set(row)

            def find(component_id):
                root = component_id
                while parent[root] != root:
                    root = parent[root]
                while parent[component_id] != component_id:
                    next_id = parent[component_id]
                    parent[component_id] = root
                    component_id = next_id
                return root

            def join(left_id, right_id):
                left_root = find(left_id)
                right_root = find(right_id)
                if left_root != right_root:
                    parent[right_root] = left_root

            # A sibling bus cannot contain an unrelated cousin between children.
            for family in families:
                children = []
                seen = set()
                for child_id in family.child_ids:
                    component_id = component_by_person[child_id]
                    if (
                        component_id in row_set
                        and levels[component_id] == level
                        and component_id not in seen
                    ):
                        seen.add(component_id)
                        children.append(component_id)
                if len(children) >= 2:
                    anchor = children[0]
                    for component_id in children[1:]:
                        join(anchor, component_id)

            # If two people in one marriage component have independent parents
            # on this row, those parent branches must also remain adjacent.
            parents_by_child_component = defaultdict(set)
            for family in families:
                parent_component = family.parent_component_id
                if parent_component not in row_set:
                    continue
                for child_id in family.child_ids:
                    child_component = component_by_person[child_id]
                    if child_component != parent_component:
                        parents_by_child_component[child_component].add(parent_component)
            for parent_components in parents_by_child_component.values():
                items = list(parent_components)
                if len(items) >= 2:
                    anchor = items[0]
                    for component_id in items[1:]:
                        join(anchor, component_id)

            grouped = defaultdict(list)
            for component_id in row:
                grouped[find(component_id)].append(component_id)
            return list(grouped.values())

        @staticmethod
        def _topological_order(items, desired, precedence, fallback):
            outgoing = defaultdict(set)
            indegree = {item: 0 for item in items}
            item_set = set(items)
            for left_id, right_id in precedence:
                if left_id not in item_set or right_id not in item_set:
                    continue
                if right_id in outgoing[left_id]:
                    continue
                outgoing[left_id].add(right_id)
                indegree[right_id] += 1

            queue = []
            serial = 0
            for item in items:
                if indegree[item] == 0:
                    heappush(
                        queue,
                        (
                            desired.get(item, fallback[item]),
                            fallback[item],
                            serial,
                            item,
                        ),
                    )
                    serial += 1

            result = []
            while queue:
                _, _, _, item = heappop(queue)
                result.append(item)
                for next_id in outgoing[item]:
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
            return result if len(result) == len(items) else None

        def _order_blocks(
            self,
            blocks,
            desired,
            fallback,
            precedence,
        ):
            """Order whole topology blocks while respecting global hints."""

            block_index = {
                component_id: index
                for index, block in enumerate(blocks)
                for component_id in block
            }
            block_precedence = set()
            for left_id, right_id in precedence:
                left_block = block_index[left_id]
                right_block = block_index[right_id]
                if left_block != right_block:
                    block_precedence.add((left_block, right_block))

            block_desired = {
                index: sum(desired[item] for item in block) / len(block)
                for index, block in enumerate(blocks)
            }
            block_fallback = {
                index: sum(fallback[item] for item in block) / len(block)
                for index, block in enumerate(blocks)
            }
            ordered_block_ids = self._topological_order(
                list(range(len(blocks))),
                block_desired,
                block_precedence,
                block_fallback,
            )
            if ordered_block_ids is None:
                return None

            result = []
            for block_id in ordered_block_ids:
                block = blocks[block_id]
                internal = self._topological_order(
                    block,
                    desired,
                    precedence,
                    fallback,
                )
                if internal is None:
                    return None
                result.extend(internal)
            return result

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
            outgoing = defaultdict(list)
            for family in families:
                parent_component = family.parent_component_id
                for child_id in family.child_ids:
                    child_component = component_by_person[child_id]
                    if child_component == parent_component:
                        continue
                    child_offset = components[child_component].person_offsets[child_id]
                    incoming[child_component].append(
                        (parent_component, family.source_offset, child_offset)
                    )
                    outgoing[parent_component].append(
                        (child_component, family.source_offset, child_offset)
                    )

            # Alternate downward/upward information through the layered graph.
            # Manual order stays hard; only unnumbered components move between
            # those anchors. This gives automatic bridge branches enough context
            # to sit beside the ancestry they later marry into.
            for _ in range(6):
                changed = False
                for level in sorted(rows):
                    row = rows[level]
                    fallback = {
                        component_id: centers[component_id]
                        for component_id in row
                    }
                    desired = {}
                    for component_id in row:
                        values = []
                        values.extend(
                            centers[parent_component]
                            + source_offset
                            - child_offset
                            for parent_component, source_offset, child_offset
                            in incoming.get(component_id, ())
                        )
                        values.extend(
                            centers[child_component]
                            + child_offset
                            - source_offset
                            for child_component, source_offset, child_offset
                            in outgoing.get(component_id, ())
                        )
                        desired[component_id] = (
                            sum(values) / len(values)
                            if values
                            else centers[component_id]
                        )

                    precedence = self._manual_precedence(row, components)
                    blocks = self._topology_blocks(
                        row,
                        families,
                        component_by_person,
                        level,
                        levels,
                    )
                    ordered = self._order_blocks(
                        blocks,
                        desired,
                        fallback,
                        precedence,
                    )
                    if ordered is None:
                        # Contiguous topology blocks and explicit manual order are
                        # contradictory. Keep the manual base layout so the router
                        # can fail closed with the established generation/order
                        # diagnostic rather than silently violating the workbook.
                        continue
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
                manual = [
                    (components[item].order_hint, item)
                    for item in row
                    if components[item].order_hint is not None
                ]
                if [item for _, item in manual] != [
                    item for _, item in sorted(manual)
                ]:
                    raise ValueError(
                        f"Planar layout violated manual order in generation {level + 1}"
                    )
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
