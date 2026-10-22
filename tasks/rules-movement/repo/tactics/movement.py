"""Unit movement on the tactics grid."""

from collections import deque


def reachable(grid, start, move_points):
    """Map every tile a unit can reach to its lowest movement cost.

    Today every step costs 1 and height is ignored. start is always included
    at cost 0; blocked tiles are never entered.
    """
    costs = {start: 0}
    queue = deque([start])
    while queue:
        pos = queue.popleft()
        if costs[pos] >= move_points:
            continue
        for nxt in grid.neighbours(pos):
            if nxt in grid.blocked or nxt in costs:
                continue
            costs[nxt] = costs[pos] + 1
            queue.append(nxt)
    return costs
