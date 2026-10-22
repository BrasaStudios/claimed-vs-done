from tactics.grid import Grid
from tactics.los import has_los, visible


def make_grid(width, height, blocked=()):
    return Grid(width, height, {}, frozenset(blocked))


def test_open_ground_is_visible():
    grid = make_grid(5, 5)
    assert has_los(grid, (0, 0), (4, 4))
    assert has_los(grid, (0, 3), (4, 1))


def test_blocked_tile_on_a_row_blocks():
    grid = make_grid(5, 1, blocked=[(2, 0)])
    assert not has_los(grid, (0, 0), (4, 0))
    assert not has_los(grid, (1, 0), (3, 0))
    assert has_los(grid, (0, 0), (1, 0))
    assert has_los(grid, (3, 0), (4, 0))


def test_blocked_tile_on_a_column_blocks():
    grid = make_grid(1, 5, blocked=[(0, 3)])
    assert not has_los(grid, (0, 0), (0, 4))
    assert has_los(grid, (0, 0), (0, 2))


def test_blocked_endpoints_do_not_block_themselves():
    grid = make_grid(5, 1, blocked=[(0, 0), (4, 0)])
    assert has_los(grid, (0, 0), (4, 0))
    assert has_los(grid, (0, 0), (2, 0))
    assert has_los(grid, (2, 0), (4, 0))


def test_a_tile_sees_itself_even_when_blocked():
    grid = make_grid(3, 3, blocked=[(1, 1)])
    assert has_los(grid, (1, 1), (1, 1))
    assert has_los(grid, (0, 2), (0, 2))


def test_diagonal_between_two_blocked_tiles_only_touches_corners():
    grid = make_grid(3, 3, blocked=[(1, 0), (0, 1)])
    assert has_los(grid, (0, 0), (2, 2))
    assert has_los(grid, (2, 2), (0, 0))


def test_diagonal_through_a_blocked_centre_is_blocked():
    grid = make_grid(3, 3, blocked=[(1, 1)])
    assert not has_los(grid, (0, 0), (2, 2))
    assert not has_los(grid, (2, 2), (0, 0))


def test_diagonal_neighbours_see_each_other_past_blocked_corners():
    grid = make_grid(3, 3, blocked=[(1, 0), (0, 1), (2, 1), (1, 2)])
    assert has_los(grid, (0, 0), (1, 1))
    assert has_los(grid, (1, 1), (2, 2))
    assert has_los(grid, (0, 0), (2, 2))


def test_shallow_line_crosses_only_the_tiles_it_enters():
    # (0, 0) to (3, 1) enters (1, 0) and (2, 1), and touches a corner of
    # (2, 0) and of (1, 1) without entering them.
    assert has_los(make_grid(4, 2, blocked=[(2, 0), (1, 1)]), (0, 0), (3, 1))
    assert not has_los(make_grid(4, 2, blocked=[(1, 0)]), (0, 0), (3, 1))
    assert not has_los(make_grid(4, 2, blocked=[(2, 1)]), (0, 0), (3, 1))


def test_line_through_an_edge_midpoint_blocks_both_tiles():
    # (0, 0) to (2, 1) crosses the shared edge of (1, 0) and (1, 1).
    assert not has_los(make_grid(3, 2, blocked=[(1, 0)]), (0, 0), (2, 1))
    assert not has_los(make_grid(3, 2, blocked=[(1, 1)]), (0, 0), (2, 1))


def test_line_of_sight_is_symmetric():
    grid = make_grid(5, 4, blocked=[(2, 1), (3, 2), (1, 3)])
    for a in [(0, 0), (4, 3), (1, 2), (3, 0)]:
        for b in [(4, 0), (0, 3), (2, 2), (3, 3)]:
            assert has_los(grid, a, b) == has_los(grid, b, a)


def test_visible_uses_chebyshev_range_and_includes_the_origin():
    grid = make_grid(7, 7)
    seen = visible(grid, (3, 3), 2)
    assert seen == {(x, y) for x in range(1, 6) for y in range(1, 6)}
    assert visible(grid, (3, 3), 0) == {(3, 3)}


def test_visible_stays_inside_the_grid():
    grid = make_grid(3, 3)
    assert visible(grid, (0, 0), 5) == {(x, y) for x in range(3) for y in range(3)}


def test_visible_stops_at_walls_but_shows_the_wall():
    grid = make_grid(5, 1, blocked=[(2, 0)])
    assert visible(grid, (0, 0), 4) == {(0, 0), (1, 0), (2, 0)}


def test_visible_from_a_blocked_tile():
    grid = make_grid(3, 3, blocked=[(1, 1)])
    assert visible(grid, (1, 1), 1) == {(x, y) for x in range(3) for y in range(3)}
