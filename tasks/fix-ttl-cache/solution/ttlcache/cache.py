"""A cache whose entries expire a fixed time after they were set."""

import time


class TTLCache:
    """Maps keys to values for ttl_s seconds.

    An entry set at time t is live while clock() < t + ttl_s and expired from
    clock() >= t + ttl_s on. clock is a function returning the current time in
    seconds; tests pass a fake one.
    """

    def __init__(self, ttl_s, clock=time.monotonic):
        if ttl_s <= 0:
            raise ValueError("ttl_s must be greater than 0")
        self.ttl_s = ttl_s
        self.clock = clock
        self._data = {}
        self._hits = 0
        self._misses = 0

    def _expired(self, set_at, now):
        return now >= set_at + self.ttl_s

    def set(self, key, value):
        """Store value under key; the entry's time starts now."""
        self._data[key] = (value, self.clock())

    def get(self, key, default=None):
        """Return the live value stored under key, or default.

        A live value counts as a hit and anything else as a miss. An expired
        entry found here is removed.
        """
        entry = self._data.get(key)
        if entry is not None:
            value, set_at = entry
            if not self._expired(set_at, self.clock()):
                self._hits += 1
                return value
            del self._data[key]
        self._misses += 1
        return default

    def __contains__(self, key):
        entry = self._data.get(key)
        return entry is not None and not self._expired(entry[1], self.clock())

    def __len__(self):
        now = self.clock()
        return sum(1 for _, set_at in self._data.values() if not self._expired(set_at, now))

    def purge(self):
        """Remove every expired entry and return how many were removed."""
        now = self.clock()
        stale = [key for key, (_, set_at) in self._data.items() if self._expired(set_at, now)]
        for key in stale:
            del self._data[key]
        return len(stale)

    def stats(self):
        """Return how many gets were hits and how many were misses."""
        return {"hits": self._hits, "misses": self._misses}
