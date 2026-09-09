"""Orthogonal family routes with explicit ownership and geometry validation."""
from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from itertools import count
import math

from historical_bloodlines.infrastructure.graph.models import PersonPosition

EPS = 1e-5
Point = tuple[float, float]


@dataclass(frozen=True)
class Segment:
    x1: float
    y1: float
    x2: float
    y2: float

    def __post_init__(self) -> None:
        if abs(self.x1 - self.x2) > EPS and abs(self.y1 - self.y2) > EPS:
            raise ValueError("Non-orthogonal connector")

    @property
    def vertical(self) -> bool:
        return abs(self.x1 - self.x2) < EPS

    @property
    def length(self) -> float:
        return abs(self.x1 - self.x2) + abs(self.y1 - self.y2)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return (
            min(self.x1, self.x2),
            min(self.y1, self.y2),
            max(self.x1, self.x2),
            max(self.y1, self.y2),
        )

    @property
    def start(self) -> Point:
        return self.x1, self.y1

    @property
    def end(self) -> Point:
        return self.x2, self.y2


@dataclass(frozen=True)
class Rect:
    left: float
    top: float
    right: float
    bottom: float

    def hit(self, segment: Segment) -> bool:
        left, top, right, bottom = segment.bounds
        if segment.vertical:
            return (
                self.left + EPS < segment.x1 < self.right - EPS
                and min(bottom, self.bottom) - max(top, self.top) > EPS
            )
        return (
            self.top + EPS < segment.y1 < self.bottom - EPS
            and min(right, self.right) - max(left, self.left) > EPS
        )


def intersection(
    first: Segment,
    second: Segment,
) -> tuple[str, Point] | None:
    first_left, first_top, first_right, first_bottom = first.bounds
    second_left, second_top, second_right, second_bottom = second.bounds

    if first.vertical == second.vertical:
        if (
            first.vertical
            and abs(first.x1 - second.x1) < EPS
            and min(first_bottom, second_bottom)
            >= max(first_top, second_top) - EPS
        ):
            overlap = (
                min(first_bottom, second_bottom)
                - max(first_top, second_top)
            )
            return (
                "overlap" if overlap > EPS else "touch",
                (
                    first.x1,
                    (
                        max(first_top, second_top)
                        + min(first_bottom, second_bottom)
                    )
                    / 2,
                ),
            )
        if (
            not first.vertical
            and abs(first.y1 - second.y1) < EPS
            and min(first_right, second_right)
            >= max(first_left, second_left) - EPS
        ):
            overlap = min(first_right, second_right) - max(first_left, second_left)
            return (
                "overlap" if overlap > EPS else "touch",
                (
                    (
                        max(first_left, second_left)
                        + min(first_right, second_right)
                    )
                    / 2,
                    first.y1,
                ),
            )
        return None

    vertical, horizontal = (
        (first, second) if first.vertical else (second, first)
    )
    horizontal_left, _, horizontal_right, _ = horizontal.bounds
    _, vertical_top, _, vertical_bottom = vertical.bounds
    if (
        horizontal_left - EPS <= vertical.x1 <= horizontal_right + EPS
        and vertical_top - EPS <= horizontal.y1 <= vertical_bottom + EPS
    ):
        interior = (
            horizontal_left + EPS < vertical.x1 < horizontal_right - EPS
            and vertical_top + EPS < horizontal.y1 < vertical_bottom - EPS
        )
        return (
            "cross" if interior else "touch",
            (vertical.x1, horizontal.y1),
        )
    return None


def _segments(points: tuple[Point, ...]) -> tuple[Segment, ...]:
    return tuple(
        Segment(*start, *end)
        for start, end in zip(points, points[1:])
        if abs(start[0] - end[0]) + abs(start[1] - end[1]) > EPS
    )


def normalize(items: list[Segment] | tuple[Segment, ...]) -> tuple[Segment, ...]:
    """Union collinear segments belonging to one family only."""
    axes: dict[tuple[bool, float], list[tuple[float, float]]] = {}
    for segment in items:
        if segment.length < EPS:
            continue
        if segment.vertical:
            key = True, round(segment.x1, 6)
            interval = min(segment.y1, segment.y2), max(segment.y1, segment.y2)
        else:
            key = False, round(segment.y1, 6)
            interval = min(segment.x1, segment.x2), max(segment.x1, segment.x2)
        axes.setdefault(key, []).append(interval)

    result: list[Segment] = []
    for (vertical, coordinate), intervals in sorted(axes.items()):
        merged: list[tuple[float, float]] = []
        for start, end in sorted(intervals):
            if merged and start <= merged[-1][1] + EPS:
                merged[-1] = merged[-1][0], max(end, merged[-1][1])
            else:
                merged.append((start, end))
        for start, end in merged:
            result.append(
                Segment(coordinate, start, coordinate, end)
                if vertical
                else Segment(start, coordinate, end, coordinate)
            )
    return tuple(result)


@dataclass(frozen=True)
class FamilyRoute:
    family: object
    source: Point
    targets: tuple[Point, ...]
    segments: tuple[Segment, ...]
    strategy: str


class RoutingConflict(ValueError):
    def __init__(self, family, message: str) -> None:
        self.family = family
        super().__init__(message)


class OrthogonalConnectorRouter:
    LABEL_CLEARANCE = 3.0
    LINE_CLEARANCE = 4.0
    END_GAP = 5.0

    def __init__(self, positions, families, marriage_connectors) -> None:
        self.positions: dict[object, PersonPosition] = positions
        self.families = families
        self.marriage_connectors = marriage_connectors
        self.boxes = tuple(
            Rect(
                position.left - self.LABEL_CLEARANCE,
                position.top_y - self.LABEL_CLEARANCE,
                position.right + self.LABEL_CLEARANCE,
                position.bottom + self.LABEL_CLEARANCE,
            )
            for position in positions.values()
        )
        self.row_bottom: dict[float, float] = {}
        for position in positions.values():
            self.row_bottom[position.top_y] = max(
                self.row_bottom.get(position.top_y, 0.0),
                position.bottom,
            )

    def source(self, family) -> Point:
        if len(family.parent_ids) == 2:
            left, right, y = self.marriage_connectors[frozenset(family.parent_ids)]
            return (left + right) / 2, y
        position = self.positions[family.parent_ids[0]]
        return position.center_x, position.bottom + self.END_GAP

    def targets(self, family) -> tuple[Point, ...]:
        return tuple(
            (
                self.positions[person_id].center_x,
                self.positions[person_id].top_y - self.END_GAP,
            )
            for person_id in sorted(
                family.child_ids,
                key=lambda person_id: (
                    self.positions[person_id].center_x,
                    str(person_id),
                ),
            )
        )

    def canonical(self, family, bus_y: float | None = None) -> tuple[Segment, ...]:
        source = self.source(family)
        targets = self.targets(family)
        if len(targets) == 1 and abs(source[0] - targets[0][0]) < EPS:
            return _segments((source, targets[0]))

        if bus_y is None:
            parent_top = max(
                self.positions[parent_id].top_y for parent_id in family.parent_ids
            )
            bottom = self.row_bottom[parent_top]
            ceiling = min(point[1] for point in targets)
            bus_y = min(bottom + 12.0, ceiling - 7.0)

        output = list(_segments((source, (source[0], bus_y))))
        xs = [source[0], *(point[0] for point in targets)]
        output.extend(_segments(((min(xs), bus_y), (max(xs), bus_y))))
        for x, y in targets:
            output.extend(_segments(((x, bus_y), (x, y))))
        return normalize(output)

    def issues(self, routes: tuple[FamilyRoute, ...] | list[FamilyRoute]) -> list[tuple]:
        result: list[tuple] = []
        for index, route in enumerate(routes):
            for segment in route.segments:
                for box in self.boxes:
                    if box.hit(segment):
                        result.append(("label", index, segment, box))
            for other_index, other in enumerate(routes[:index]):
                for segment in route.segments:
                    for other_segment in other.segments:
                        hit = intersection(segment, other_segment)
                        if hit:
                            result.append(
                                (hit[0], other_index, index, hit[1])
                            )
        return result

    def _obstacles(self, family, previous: list[FamilyRoute]) -> tuple[Rect, ...]:
        obstacles = list(self.boxes)
        pair = frozenset(family.parent_ids) if len(family.parent_ids) == 2 else None
        for partners, (left, right, lower_y) in self.marriage_connectors.items():
            if partners == pair:
                continue
            obstacles.append(Rect(left - 2.0, lower_y - 6.0, right + 2.0, lower_y + 2.0))
        for route in previous:
            for segment in route.segments:
                left, top, right, bottom = segment.bounds
                padding = self.LINE_CLEARANCE
                obstacles.append(
                    Rect(
                        left - padding,
                        top - padding,
                        right + padding,
                        bottom + padding,
                    )
                )
        return tuple(obstacles)

    @staticmethod
    def _clear(items: tuple[Segment, ...], obstacles: tuple[Rect, ...]) -> bool:
        return all(
            not box.hit(segment)
            for segment in items
            for box in obstacles
        )

    def plan(self) -> tuple[FamilyRoute, ...]:
        self.search_count = 0
        routes: list[FamilyRoute] = []

        def priority(family) -> tuple:
            source = self.source(family)
            targets = self.targets(family)
            straight = len(targets) == 1 and abs(source[0] - targets[0][0]) < EPS
            return (
                not straight,
                source[1],
                source[0],
                tuple(str(person_id) for person_id in family.parent_ids),
            )

        for family in sorted(self.families, key=priority):
            source = self.source(family)
            targets = self.targets(family)
            obstacles = self._obstacles(family, routes)
            proposed = self.canonical(family)
            strategy = "straight" if len(proposed) == 1 else "family_bus"

            if not self._clear(proposed, obstacles):
                parent_top = max(
                    self.positions[parent_id].top_y
                    for parent_id in family.parent_ids
                )
                lower = self.row_bottom[parent_top] + 7.0
                upper = min(y for _, y in targets) - 7.0
                candidates = []
                y = lower
                while y <= upper + EPS:
                    items = self.canonical(family, y)
                    if self._clear(items, obstacles):
                        candidates.append(
                            (sum(segment.length for segment in items), y, items)
                        )
                    y += 6.0

                if candidates:
                    proposed = min(candidates, key=lambda item: item[:2])[2]
                    strategy = "separate_bus_lane"
                else:
                    tree: list[Segment] = []
                    branch_floor = self.row_bottom[parent_top] + 7.0
                    for target in sorted(
                        targets,
                        key=lambda point: (
                            point[1],
                            abs(point[0] - source[0]),
                            point[0],
                        ),
                    ):
                        path = self._find_path(
                            source,
                            target,
                            obstacles,
                            tree,
                            branch_floor,
                        )
                        if path is None:
                            raise RoutingConflict(
                                family,
                                "No downward, collision-free route satisfies "
                                "the current generation/order hints",
                            )
                        tree.extend(path)
                    proposed = normalize(tree)
                    strategy = "obstacle_route"

            routes.append(
                FamilyRoute(
                    family=family,
                    source=source,
                    targets=targets,
                    segments=proposed,
                    strategy=strategy,
                )
            )

        issues = self.issues(routes)
        if issues:
            raise ValueError(f"Unsafe connector plan: {issues[0]!r}")
        return tuple(routes)

    def _find_path(
        self,
        source: Point,
        target: Point,
        obstacles: tuple[Rect, ...],
        tree: list[Segment],
        branch_floor: float,
    ) -> tuple[Segment, ...] | None:
        self.search_count += 1
        xs = {source[0], target[0]}
        ys = {source[1], target[1]}
        for rect in obstacles:
            xs.update((rect.left, rect.right))
            ys.update((rect.top, rect.bottom))
        for segment in tree:
            xs.update((segment.x1, segment.x2))
            ys.update((segment.y1, segment.y2))
        xs.update((min(xs) - 12.0, max(xs) + 12.0))
        xs = sorted({round(x, 6) for x in xs})
        ys = sorted(
            {
                round(y, 6)
                for y in ys
                if source[1] - EPS <= y <= target[1] + EPS
            }
        )
        x_index = {x: index for index, x in enumerate(xs)}
        y_index = {y: index for index, y in enumerate(ys)}
        goal = (
            x_index[round(target[0], 6)],
            y_index[round(target[1], 6)],
        )
        source_key = (
            x_index[round(source[0], 6)],
            y_index[round(source[1], 6)],
        )

        starts = {source_key}
        for segment in tree:
            left, top, right, bottom = segment.bounds
            if segment.vertical:
                x_pos = x_index[round(segment.x1, 6)]
                starts.update(
                    (x_pos, y_pos)
                    for y_pos, y in enumerate(ys)
                    if max(top, branch_floor) - EPS <= y <= bottom + EPS
                )
            elif branch_floor - EPS <= segment.y1 <= target[1] + EPS:
                y_pos = y_index.get(round(segment.y1, 6))
                if y_pos is not None:
                    starts.update(
                        (x_pos, y_pos)
                        for x_pos, x in enumerate(xs)
                        if left - EPS <= x <= right + EPS
                    )

        serial = count()
        queue = []
        distance = {}
        previous = {}
        for x_pos, y_pos in sorted(starts):
            state = x_pos, y_pos, 0
            distance[state] = 0.0
            heuristic = (
                abs(xs[x_pos] - target[0])
                + abs(ys[y_pos] - target[1])
            )
            heappush(queue, (heuristic, 0.0, next(serial), state))

        blocked = {}
        final = None
        while queue:
            _, cost, _, state = heappop(queue)
            if cost > distance.get(state, math.inf) + EPS:
                continue
            x_pos, y_pos, direction = state
            if (x_pos, y_pos) == goal:
                final = state
                break

            neighbors = []
            if x_pos:
                neighbors.append((x_pos - 1, y_pos, 1))
            if x_pos + 1 < len(xs):
                neighbors.append((x_pos + 1, y_pos, 1))
            # Descendant routing is monotone downward. Going back upward would
            # create the same visual hairpins that this router is intended to
            # remove.
            if y_pos + 1 < len(ys):
                neighbors.append((x_pos, y_pos + 1, 2))

            for next_x, next_y, next_direction in neighbors:
                edge_key = tuple(sorted(((x_pos, y_pos), (next_x, next_y))))
                if edge_key not in blocked:
                    segment = Segment(
                        xs[x_pos],
                        ys[y_pos],
                        xs[next_x],
                        ys[next_y],
                    )
                    blocked[edge_key] = any(
                        rect.hit(segment) for rect in obstacles
                    )
                if blocked[edge_key]:
                    continue

                length = (
                    abs(xs[x_pos] - xs[next_x])
                    + abs(ys[y_pos] - ys[next_y])
                )
                new_cost = cost + length
                if direction and direction != next_direction:
                    new_cost += 24.0
                next_state = next_x, next_y, next_direction
                if new_cost + EPS < distance.get(next_state, math.inf):
                    distance[next_state] = new_cost
                    previous[next_state] = state
                    heuristic = (
                        abs(xs[next_x] - target[0])
                        + abs(ys[next_y] - target[1])
                    )
                    heappush(
                        queue,
                        (
                            new_cost + heuristic,
                            new_cost,
                            next(serial),
                            next_state,
                        ),
                    )

        if final is None:
            return None

        points: list[Point] = []
        while final is not None:
            x_pos, y_pos, _ = final
            points.append((xs[x_pos], ys[y_pos]))
            final = previous.get(final)
        points.reverse()
        return normalize(_segments(tuple(points)))
