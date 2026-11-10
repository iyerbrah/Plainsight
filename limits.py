"""Question limits for the public site, so nobody can run up the OpenAI bill.

Two limits, both counted in this process's memory (the site runs as one process):
- each visitor address gets RATE_LIMIT_PER_HOUR questions in any rolling hour;
- the whole site gets DAILY_QUESTION_CAP questions per UTC day.
A restart clears the counts, which is fine for a backstop.
"""
import os
import threading
import time
from collections import defaultdict, deque

from dotenv import load_dotenv

load_dotenv()  # the limits can be set in .env locally, like engine.py's settings

PER_HOUR = int(os.environ.get("RATE_LIMIT_PER_HOUR", "20"))
PER_DAY = int(os.environ.get("DAILY_QUESTION_CAP", "300"))
HOUR = 3600


class Limiter:
    def __init__(self, per_hour=PER_HOUR, per_day=PER_DAY, clock=time.time):
        self.per_hour = per_hour
        self.per_day = per_day
        self.clock = clock
        self.recent = defaultdict(deque)  # visitor -> times of their questions in the last hour
        self.day = None
        self.today = 0
        self.lock = threading.Lock()

    def _tidy(self, visitor, now):
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        if day != self.day:
            self.day, self.today = day, 0
        times = self.recent[visitor]
        while times and times[0] <= now - HOUR:
            times.popleft()
        return times

    def take(self, visitor):
        """Use up one question. Returns None if allowed, else "hour" or "day" for the limit that was hit."""
        with self.lock:
            now = self.clock()
            times = self._tidy(visitor, now)
            if self.today >= self.per_day:
                return "day"
            if len(times) >= self.per_hour:
                return "hour"
            times.append(now)
            self.today += 1
            if len(self.recent) > 10_000:  # forget visitors with nothing in the last hour
                for v in [v for v, t in self.recent.items() if not t or t[-1] <= now - HOUR]:
                    del self.recent[v]
            return None

    def left(self, visitor):
        """Questions this visitor can still ask right now."""
        with self.lock:
            times = self._tidy(visitor, self.clock())
            return max(0, min(self.per_hour - len(times), self.per_day - self.today))
