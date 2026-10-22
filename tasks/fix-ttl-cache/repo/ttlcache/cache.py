"""A cache whose entries expire a fixed time after they were set."""

import time


class TTLCache:
    """Maps keys to values for ttl_s seconds.

    clock is a function returning the current time in seconds; tests pass a
    fake one.
    """

    def __init__(self, ttl_s, clock=time.monotonic):
        self.ttl_s = ttl_s
        self.clock = clock
        self._data = {}

    def set(self, key, value):
        """Store value under key; the entry's time starts now."""
        self._data[key] = (value, self.clock())

    def get(self, key, default=None):
        """Return the value stored under key, or default."""
        entry = self._data.get(key)
        if entry is None:
            return default
        value, set_at = entry
        if self.clock() <= set_at + self.ttl_s:
            return value
        return default

    def __contains__(self, key):
        entry = self._data.get(key)
        return entry is not None and self.clock() <= entry[1] + self.ttl_s

    def __len__(self):
        return len(self._data)
