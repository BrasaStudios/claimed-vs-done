"""A rectangular tactics grid with terrain heights and impassable tiles."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Grid:
    """Grid(width, height, heights, blocked).

    A tile is an (x, y) pair with 0 <= x < width and 0 <= y < height.
    heights maps (x, y) to an integer height level; a tile missing from it
    has height 0. blocked is a set of impassable tiles.
    """

    width: int
    height: int
    heights: dict = field(default_factory=dict)
    blocked: frozenset = frozenset()

    def in_bounds(self, pos):
        """True when pos lies inside the grid."""
        x, y = pos
        return 0 <= x < self.width and 0 <= y < self.height

    def height_at(self, pos):
        """The height level of pos (0 when the tile is missing from heights)."""
        return self.heights.get(pos, 0)

    def neighbours(self, pos):
        """Yield the in-bounds neighbours of pos: up, right, down, left."""
        x, y = pos
        for nxt in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
            if self.in_bounds(nxt):
                yield nxt
