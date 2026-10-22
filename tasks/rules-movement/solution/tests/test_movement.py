from tactics.grid import Grid
from tactics.movement import path_to, reachable


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


def test_climbing_one_level_costs_two():
    grid = Grid(3, 1, {(1, 0): 1}, frozenset())
    assert reachable(grid, (0, 0), 3) == {(0, 0): 0, (1, 0): 2, (2, 0): 3}
    assert reachable(grid, (0, 0), 1) == {(0, 0): 0}


def test_climbing_two_levels_is_impossible_but_dropping_is_not():
    grid = Grid(3, 1, {(1, 0): 2}, frozenset())
    assert reachable(grid, (0, 0), 10) == {(0, 0): 0}
    assert reachable(grid, (1, 0), 10) == {(1, 0): 0, (0, 0): 1, (2, 0): 1}


def test_a_big_drop_costs_one():
    grid = Grid(3, 1, {(0, 0): 3}, frozenset())
    assert reachable(grid, (0, 0), 2) == {(0, 0): 0, (1, 0): 1, (2, 0): 2}
    assert reachable(grid, (1, 0), 5) == {(1, 0): 0, (2, 0): 1}


def test_stairs_add_up():
    grid = Grid(4, 1, {(1, 0): 1, (2, 0): 2, (3, 0): 3}, frozenset())
    assert reachable(grid, (0, 0), 5) == {(0, 0): 0, (1, 0): 2, (2, 0): 4}
    assert reachable(grid, (0, 0), 6)[(3, 0)] == 6


def test_path_includes_both_ends():
    grid = flat_grid(3, 1)
    assert path_to(grid, (0, 0), (2, 0), 2) == [(0, 0), (1, 0), (2, 0)]


def test_path_to_the_start_is_just_the_start():
    grid = flat_grid(2, 2)
    assert path_to(grid, (1, 1), (1, 1), 0) == [(1, 1)]


def test_path_is_none_when_out_of_reach():
    grid = flat_grid(4, 1)
    assert path_to(grid, (0, 0), (3, 0), 2) is None
    walled = Grid(3, 1, {(1, 0): 2}, frozenset())
    assert path_to(walled, (0, 0), (2, 0), 10) is None


def test_path_is_none_for_blocked_or_off_grid_goals():
    grid = flat_grid(3, 3, blocked=[(2, 2)])
    assert path_to(grid, (0, 0), (2, 2), 10) is None
    assert path_to(grid, (0, 0), (3, 0), 10) is None


def test_ties_go_to_the_smallest_path():
    grid = flat_grid(3, 3)
    assert path_to(grid, (0, 0), (2, 2), 4) == [(0, 0), (0, 1), (0, 2), (1, 2), (2, 2)]
    assert path_to(grid, (2, 2), (0, 0), 4) == [(2, 2), (1, 2), (0, 2), (0, 1), (0, 0)]


def test_ties_between_a_climb_and_a_detour():
    grid = Grid(2, 2, {(1, 0): 1, (1, 1): 1}, frozenset())
    assert path_to(grid, (0, 0), (1, 1), 3) == [(0, 0), (0, 1), (1, 1)]
    assert path_to(grid, (0, 0), (1, 1), 2) is None


def test_path_goes_around_a_wall():
    grid = flat_grid(3, 3, blocked=[(1, 1)])
    assert path_to(grid, (2, 0), (0, 2), 4) == [(2, 0), (1, 0), (0, 0), (0, 1), (0, 2)]


def test_calls_leave_the_grid_alone():
    heights = {(1, 0): 1}
    grid = Grid(3, 2, heights, frozenset([(2, 1)]))
    reachable(grid, (0, 0), 5)
    path_to(grid, (0, 0), (2, 0), 5)
    assert heights == {(1, 0): 1}
    assert grid.blocked == frozenset([(2, 1)])
