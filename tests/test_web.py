"""The website: pages render, and /api/ask turns each kind of answer into JSON, with a fake model."""
import math
import re

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import engine
from engine import CANNOT_ANSWER, Answer
from limits import Limiter
from web import main


@pytest.fixture
def client(monkeypatch):
    main.cached_answer.cache_clear()
    monkeypatch.setattr(main, "limiter", Limiter(per_hour=20, per_day=300))
    yield TestClient(main.app)
    main.cached_answer.cache_clear()


def model_says(monkeypatch, fake_client, *replies):
    fake = fake_client(*replies)
    monkeypatch.setattr(engine, "make_client", lambda: fake)
    return fake


def test_pages_render(client):
    home = client.get("/")
    assert home.status_code == 200
    assert "What do you want to know?" in home.text
    assert "20 questions left" in home.text
    scorecard = client.get("/scorecard")
    assert scorecard.status_code == 200
    assert "Table and column names only" in scorecard.text


def test_pages_have_link_preview_tags(client):
    for path, title in [("/", "Plainsight: ask a database in plain English"), ("/scorecard", "Scorecard · Plainsight")]:
        page = client.get(path).text
        tags = dict(re.findall(r'<meta (?:property|name)="((?:og|twitter):[a-z:_]+)" content="([^"]*)"', page))
        assert tags["og:title"] == title
        assert tags["og:url"] == f"https://plainsight.ramiyer.tech{path}"
        assert tags["og:image"] == "https://plainsight.ramiyer.tech/static/og.png"
        assert tags["og:description"] and tags["twitter:card"] == "summary_large_image"
    image = client.get("/static/og.png")
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"


def test_scorecard_leads_with_the_model_the_site_uses(client):
    page = client.get("/scorecard").text
    assert "the model this site answers with" in page
    assert "Everything, on deepseek-v4-pro" in page  # other models are there for comparison
    assert "The same ladder on other models" in page


def test_scorecard_shows_the_chosen_runs_failures(client):
    names_only = client.get("/scorecard").text  # the first run is the default
    full = client.get("/scorecard?run=full__gpt-5.4-mini").text
    assert "filtered on the Portuguese category name" in names_only
    assert "No failures in this run." in full


def test_health_and_not_found(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.head("/").status_code == 200  # uptime monitors send HEAD
    assert client.get("/nope").status_code == 404
    assert client.get("/api/nope").json() == {"error": "Not found."}


def test_single_value(client, monkeypatch, fake_client):
    model_says(monkeypatch, fake_client, "SELECT count(*) AS orders FROM orders")
    data = client.post("/api/ask", json={"question": "How many orders?"}).json()
    assert data["kind"] == "value"
    assert data["value"] == "99,441" and data["label"] == "orders"
    assert data["sql"] == "SELECT count(*) AS orders FROM orders"
    assert data["left"] == 19


def test_label_and_number_gets_a_chart(client, monkeypatch, fake_client):
    sql = "SELECT customer_state, count(*) AS customers FROM customers GROUP BY 1 ORDER BY 2 DESC LIMIT 5"
    model_says(monkeypatch, fake_client, sql)
    data = client.post("/api/ask", json={"question": "Top 5 states?"}).json()
    assert data["kind"] == "table" and data["chart"] is True
    assert data["columns"] == ["customer_state", "customers"]
    assert data["numeric"] == [False, True]
    assert data["rows"][0] == ["SP", 41746]


def test_refusal_and_failed_query(client, monkeypatch, fake_client):
    model_says(monkeypatch, fake_client, CANNOT_ANSWER)
    assert client.post("/api/ask", json={"question": "Profit margin?"}).json()["kind"] == "refused"

    model_says(monkeypatch, fake_client, "SELECT nope FROM orders", "SELECT still_nope FROM orders")
    data = client.post("/api/ask", json={"question": "Broken?"}).json()
    assert data["kind"] == "error" and data["retried"] is True
    assert "still_nope" in data["error"]


def test_same_question_is_answered_from_the_cache(client, monkeypatch, fake_client):
    fake = model_says(monkeypatch, fake_client, "SELECT 1 AS x")
    client.post("/api/ask", json={"question": "One?"})
    client.post("/api/ask", json={"question": "  One?  "})
    assert len(fake.prompts) == 1


def test_model_down_is_a_502_and_not_cached(client, monkeypatch):
    def broken():
        raise RuntimeError("no key")
    monkeypatch.setattr(engine, "make_client", broken)
    response = client.post("/api/ask", json={"question": "Anything?"})
    assert response.status_code == 502
    assert main.cached_answer.cache_info().currsize == 0


def test_limits(client, monkeypatch, fake_client):
    monkeypatch.setattr(main, "limiter", Limiter(per_hour=1, per_day=300))
    model_says(monkeypatch, fake_client, "SELECT 1 AS x")
    assert client.post("/api/ask", json={"question": "One?"}, headers={"X-Real-IP": "1.2.3.4"}).status_code == 200
    blocked = client.post("/api/ask", json={"question": "Two?"}, headers={"X-Real-IP": "1.2.3.4"})
    assert blocked.status_code == 429 and "this hour" in blocked.json()["error"]


def test_question_length_is_checked(client):
    assert client.post("/api/ask", json={"question": "   "}).status_code == 422
    assert client.post("/api/ask", json={"question": "x" * 301}).status_code == 422


def test_numbers_read_naturally():
    assert main.format_value(8.1) == "8.1"
    assert main.format_value(12.0) == "12"
    assert main.format_value(1234567.891) == "1,234,567.89"
    assert main.format_value(99441) == "99,441"


def test_payload_is_json_safe():
    df = pd.DataFrame({"day": pd.to_datetime(["2018-01-01", "2018-01-02"]), "value": [1.5, math.nan]})
    data = main.to_payload(Answer("SELECT ...", df))
    assert data["rows"] == [["2018-01-01T00:00:00.000", 1.5], ["2018-01-02T00:00:00.000", None]]
    assert data["numeric"] == [False, True]
