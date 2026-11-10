"""answer(): what happens to the model's reply, with a fake model so nothing is sent anywhere."""
import pytest

import engine
from engine import CANNOT_ANSWER, answer, api_key, make_client


def test_runs_the_query(fake_client):
    result = answer("How many orders?", setup="notes", client=fake_client("SELECT count(*) AS n FROM orders"))
    assert result.error is None
    assert result.df["n"][0] == 99441


def test_strips_code_fences_and_semicolon(fake_client):
    result = answer("q", setup="notes", client=fake_client("```sql\nSELECT 1 AS x;\n```"))
    assert result.sql == "SELECT 1 AS x"
    assert result.df["x"][0] == 1


def test_refusal(fake_client):
    result = answer("What is the profit margin?", setup="notes", client=fake_client(CANNOT_ANSWER))
    assert result.refused and result.df is None


def test_no_retry_without_the_retry_setup(fake_client):
    client = fake_client("SELECT no_such_column FROM orders")
    result = answer("q", setup="notes", client=client)
    assert result.error and not result.retried
    assert len(client.prompts) == 1


def test_retry_sends_the_error_back_and_uses_the_fix(fake_client):
    client = fake_client("SELECT no_such_column FROM orders", "SELECT count(*) AS n FROM orders")
    result = answer("How many orders?", setup="full", client=client)
    assert result.retried and result.error is None
    assert result.df["n"][0] == 99441
    assert "no_such_column" in client.prompts[1]


def test_unsafe_sql_is_never_run(fake_client):
    result = answer("q", setup="notes", client=fake_client("DROP TABLE orders"))
    assert result.df is None
    assert "Only a single SELECT" in result.error


def test_calls_openai_with_gpt5_settings(fake_client):
    """GPT-5 models take max_completion_tokens and a reasoning effort, and reject a custom temperature."""
    client = fake_client("SELECT 1")
    answer("q", setup="notes", client=client)
    call = client.calls[0]
    assert call["model"] == "gpt-5.4-mini"
    assert call["reasoning_effort"] == "low"
    assert "max_completion_tokens" in call
    assert "temperature" not in call and "max_tokens" not in call


def test_openrouter_uses_its_own_address_and_key(monkeypatch):
    monkeypatch.setattr(engine, "LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test-key")
    client = make_client()
    assert str(client.base_url).startswith("https://openrouter.ai/api/v1")
    assert client.api_key == "or-test-key"


def test_missing_key_says_where_to_put_it(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "  ")
    with pytest.raises(RuntimeError, match=r"\.env"):
        api_key()
