from tactics.grid import Grid
from tactics.movement import reachable


def flat_grid(width, height, blocked=()):
    return Grid(width, height, {}, frozenset(blocked))


def test_start_costs_nothing():
    grid = flat_grid(3, 3)
    assert reachable(grid, (1, 1), 0) == {(1, 1): 0}


def test_costs_grow_by_one_per_step():
    grid = flat_grid(4, 1)
    assert reachable(grid, (0, 0), 2) == {(0, 0): 0, (1, 0): 1, (2, 0): 2}


def test_moves_are_orthogonal_only():
    grid = flat_grid(3, 3)
    assert reachable(grid, (0, 0), 1) == {(0, 0): 0, (1, 0): 1, (0, 1): 1}


def test_blocked_tiles_are_not_entered():
    grid = flat_grid(3, 3, blocked=[(1, 1)])
    result = reachable(grid, (0, 0), 10)
    assert (1, 1) not in result
    assert result[(2, 2)] == 4


def test_grid_edges_clip_the_search():
    grid = flat_grid(2, 2)
    assert set(reachable(grid, (0, 0), 5)) == {(0, 0), (1, 0), (0, 1), (1, 1)}
