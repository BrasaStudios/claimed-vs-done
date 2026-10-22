from tactics.grid import Grid


def test_in_bounds_covers_exactly_the_grid():
    grid = Grid(3, 2, {}, frozenset())
    assert grid.in_bounds((0, 0))
    assert grid.in_bounds((2, 1))
    assert not grid.in_bounds((3, 0))
    assert not grid.in_bounds((0, 2))
    assert not grid.in_bounds((-1, 0))


def test_height_defaults_to_zero_and_neighbours_keep_their_order():
    grid = Grid(3, 3, {(1, 1): 2}, frozenset())
    assert grid.height_at((1, 1)) == 2
    assert grid.height_at((0, 0)) == 0
    assert list(grid.neighbours((1, 1))) == [(1, 0), (2, 1), (1, 2), (0, 1)]
    assert list(grid.neighbours((0, 0))) == [(1, 0), (0, 1)]
