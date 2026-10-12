"""Exit KT graph tests: Gemini is always mocked; queries run against a disposable WorkWeave database given by
WORKWEAVE_TEST_DATABASE_URL (e.g. the backend's workweave_test). Skipped when it isn't set."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_exit_knowledge_transfer as kt  # noqa: E402

URL = os.environ.get("WORKWEAVE_TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def db():
    if not URL:
        pytest.skip("WORKWEAVE_TEST_DATABASE_URL isn't set")
    kt.configure(URL)
    return URL


@pytest.fixture()
def gemini(monkeypatch):
    """Replace Gemini: tests queue the structured outputs (a dict, or a function of the prompt)."""
    calls = {"prompts": [], "queue": []}

    def generate_json(prompt, model):
        calls["prompts"].append(prompt)
        out = calls["queue"].pop(0)
        return model.model_validate(out(prompt) if callable(out) else out)

    monkeypatch.setattr(kt, "generate_json", generate_json)
    monkeypatch.setattr(kt, "embed", lambda text: [0.0] * 768)
    return calls
