"""The question limits: per visitor per rolling hour, and for the whole site per UTC day."""
from limits import Limiter


class Clock:
    def __init__(self, now=1_800_000_000):  # a fixed moment, mid-day UTC
        self.now = now

    def __call__(self):
        return self.now


def test_hourly_limit_is_per_visitor():
    lim = Limiter(per_hour=2, per_day=100, clock=Clock())
    assert lim.take("a") is None
    assert lim.take("a") is None
    assert lim.take("a") == "hour"
    assert lim.take("b") is None  # someone else is not affected
    assert lim.left("a") == 0 and lim.left("b") == 1


def test_hour_rolls_over():
    clock = Clock()
    lim = Limiter(per_hour=1, per_day=100, clock=clock)
    assert lim.take("a") is None
    clock.now += 3599
    assert lim.take("a") == "hour"
    clock.now += 2
    assert lim.take("a") is None


def test_daily_cap_covers_everyone_and_resets_next_day():
    clock = Clock()
    lim = Limiter(per_hour=100, per_day=3, clock=clock)
    assert [lim.take(v) for v in "abcd"] == [None, None, None, "day"]
    assert lim.left("e") == 0
    clock.now += 86400
    assert lim.take("e") is None


def test_refused_questions_are_not_counted():
    lim = Limiter(per_hour=1, per_day=100, clock=Clock())
    lim.take("a")
    for _ in range(5):
        assert lim.take("a") == "hour"
    assert lim.today == 1

