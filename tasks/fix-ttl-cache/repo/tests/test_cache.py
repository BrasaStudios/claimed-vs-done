from ttlcache import TTLCache


class FakeClock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def test_value_is_returned_while_live():
    clock = FakeClock(100.0)
    cache = TTLCache(10, clock=clock)
    cache.set("a", 1)
    clock.now = 105.0
    assert cache.get("a") == 1


def test_missing_key_gives_the_default():
    cache = TTLCache(10, clock=FakeClock())
    assert cache.get("a") is None
    assert cache.get("a", "none") == "none"


def test_contains_and_len_while_live():
    clock = FakeClock()
    cache = TTLCache(10, clock=clock)
    cache.set("a", 1)
    cache.set("b", 2)
    clock.now = 3.0
    assert "a" in cache
    assert "z" not in cache
    assert len(cache) == 2
