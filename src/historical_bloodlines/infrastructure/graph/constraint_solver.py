"""Small deterministic convex layout solver (no extra numerical dependency)."""
from __future__ import annotations


def _inverse(matrix):
    n = len(matrix)
    work = [list(row) + [float(i == j) for j in range(n)] for i, row in enumerate(matrix)]
    for k in range(n):
        pivot = max(range(k, n), key=lambda i: abs(work[i][k]))
        if abs(work[pivot][k]) < 1e-12:
            raise ValueError("Singular layout objective")
        work[k], work[pivot] = work[pivot], work[k]
        scale = work[k][k]
        work[k] = [x / scale for x in work[k]]
        for i in range(n):
            if i == k:
                continue
            scale = work[i][k]
            if abs(scale) > 1e-15:
                work[i] = [a - scale * b for a, b in zip(work[i], work[k])]
    return [row[n:] for row in work]


def constrained_positions(keys, goals, bounds, reference):
    """Minimise weighted pair distances subject to x[b]-x[a] >= distance.

    Hildreth's dual coordinate descent projects in the objective's metric, so
    moving a tight row also moves its aligned ancestral/descendant block.
    """
    keys = sorted(keys)
    index = {key: i for i, key in enumerate(keys)}
    n = len(keys)
    if not n:
        return {}
    h = [[0.0] * n for _ in range(n)]
    f = [0.0] * n
    # Tiny regularisation fixes global translation without preserving large
    # arbitrary gaps from the old per-row layout.
    for key, i in index.items():
        h[i][i] = 0.005
        f[i] = 0.005 * reference.get(key, 0.0)
    for a, b, d, w in goals:
        if a == b:
            continue
        i, j = index[a], index[b]
        h[i][i] += w
        h[j][j] += w
        h[i][j] -= w
        h[j][i] -= w
        f[i] -= w * d
        f[j] += w * d
    inv = _inverse(h)
    x = [sum(a * b for a, b in zip(row, f)) for row in inv]
    constraints = []
    for a, b, d in bounds:
        if a == b:
            if d > 1e-6:
                raise ValueError("Infeasible aligned block")
            continue
        i, j = index[a], index[b]
        direction = [row[j] - row[i] for row in inv]
        denominator = direction[j] - direction[i]
        constraints.append((i, j, d, direction, denominator))
    multipliers = [0.0] * len(constraints)
    for _ in range(5000):
        change = 0.0
        for k, (i, j, d, direction, denominator) in enumerate(constraints):
            value = max(0.0, multipliers[k] + (d - x[j] + x[i]) / denominator)
            delta = value - multipliers[k]
            multipliers[k] = value
            if abs(delta) > 1e-12:
                for q in range(n):
                    x[q] += delta * direction[q]
                change = max(change, abs(delta) * max(abs(z) for z in direction))
        if change < 1e-7:
            break
    violation = max((d - x[index[b]] + x[index[a]] for a, b, d in bounds), default=0)
    if violation > 1e-4:
        raise ValueError(f"Layout solver did not converge; overlap={violation:.6g}")
    return {key: x[i] for key, i in index.items()}
