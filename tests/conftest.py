"""Run every test from the project folder, where the app expects its files."""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


class FakeClient:
    """Stands in for the OpenAI client: replies with the given texts in order, and records the prompts."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.prompts.append(kwargs["messages"][-1]["content"])
        message = SimpleNamespace(content=self.replies.pop(0))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None)


@pytest.fixture
def fake_client():
    return FakeClient
