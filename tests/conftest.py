"""Run every test from the project folder, where the app expects its files."""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# Fixed settings, set before the app loads, so a local .env can't change what the tests see.
# The key is a dummy: tests never call OpenAI, and this makes sure they can't use a real key.
os.environ.update({
    "OPENAI_API_KEY": "test-key-not-real",
    "LLM_MODEL": "gpt-5.4-mini",
    "REASONING_EFFORT": "low",
    "RATE_LIMIT_PER_HOUR": "20",
    "DAILY_QUESTION_CAP": "300",
})


class FakeClient:
    """Stands in for the OpenAI client: replies with the given texts in order, and records the prompts."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        self.prompts.append(kwargs["messages"][-1]["content"])
        message = SimpleNamespace(content=self.replies.pop(0))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None)


@pytest.fixture
def fake_client():
    return FakeClient
