"""Unit movement on the tactics grid."""

import heapq


def _step_cost(grid, here, nxt):
    """Cost of moving from here to the adjacent tile nxt, or None if impossible."""
    if not grid.in_bounds(nxt) or nxt in grid.blocked:
        return None
    rise = grid.height_at(nxt) - grid.height_at(here)
    if rise <= 0:
        return 1
    if rise == 1:
        return 2
    return None


def reachable(grid, start, move_points):
    """Map every tile a unit can reach within move_points to its lowest cost.

    A step to a tile no higher than the current one costs 1, a climb of one
    level costs 2, and a climb of two or more levels is impossible. start is
    always included at cost 0; blocked tiles are never entered.
    """
    costs = {start: 0}
    heap = [(0, start)]
    settled = set()
    while heap:
        cost, pos = heapq.heappop(heap)
        if pos in settled:
            continue
        settled.add(pos)
        for nxt in grid.neighbours(pos):
            step = _step_cost(grid, pos, nxt)
            if step is None:
                continue
            total = cost + step
            if total > move_points:
                continue
            if total < costs.get(nxt, total + 1):
                costs[nxt] = total
                heapq.heappush(heap, (total, nxt))
    return costs


def _costs_to(grid, goal, allowed):
    """Lowest cost of walking from each tile in allowed to goal.

    Steps are not symmetric (a climb costs more than the drop back), so this
    searches backwards from the goal and prices each step in its walking
    direction.
    """
    to_goal = {goal: 0}
    heap = [(0, goal)]
    settled = set()
    while heap:
        cost, pos = heapq.heappop(heap)
        if pos in settled:
            continue
        settled.add(pos)
        for before in grid.neighbours(pos):
            if before not in allowed:
                continue
            step = _step_cost(grid, before, pos)
            if step is None:
                continue
            total = cost + step
            if total < to_goal.get(before, total + 1):
                to_goal[before] = total
                heapq.heappush(heap, (total, before))
    return to_goal


def path_to(grid, start, goal, move_points):
    """Return a cheapest path from start to goal, or None when out of reach.

    The path lists every tile from start to goal inclusive. Among cheapest
    paths the smallest one wins, comparing paths as lists of (x, y) tuples.
    """
    costs = reachable(grid, start, move_points)
    if goal not in costs:
        return None
    best = costs[goal]
    to_goal = _costs_to(grid, goal, costs)
    path = [start]
    here = start
    spent = 0
    while here != goal:
        for nxt in sorted(grid.neighbours(here)):
            step = _step_cost(grid, here, nxt)
            if step is None or nxt not in to_goal:
                continue
            if spent + step + to_goal[nxt] == best:
                spent += step
                here = nxt
                path.append(nxt)
                break
        else:
            raise AssertionError("no cheapest continuation from %r" % (here,))
    return path
