"""
The website: two pages and one small JSON API around engine.answer().

  GET  /            the Ask page
  POST /api/ask     a question in; the answer, the SQL and a chart hint out
  GET  /scorecard   how often the answers are right, from results/
  GET  /healthz     liveness check for systemd and deploys (no model call)

Run locally, from the project folder:  .venv/bin/uvicorn web.main:app --reload --port 8100
(8100 because QuoteRunner uses 8000, on this Mac and on the server.)
"""
import json
import logging
import os
import re
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException

from engine import DEFAULT_MODEL, MAX_ROWS, answer, connect
from limits import Limiter
from web import scores

log = logging.getLogger("plainsight")
HERE = Path(__file__).parent
MAX_QUESTION_CHARS = 300

EXAMPLES = [
    "Which 5 categories have the highest revenue?",
    "How many customers have placed more than one order?",
    "What percentage of delivered orders were late?",
    "Which month had the highest revenue?",
    "What is the profit margin for each category?",
]

# No auto-generated /docs or /openapi.json: a public demo doesn't need an API browser.
app = FastAPI(title="Plainsight", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
templates.env.filters["pct"] = lambda x, digits=0: f"{x * 100:.{digits}f}%"
templates.env.filters["model_name"] = scores.model_name
# Changes whenever a CSS or JS file does, so browsers fetch the new one after a deploy.
# The public address, for link previews: Open Graph needs absolute URLs.
templates.env.globals["site_url"] = os.environ.get("SITE_URL", "https://plainsight.ramiyer.tech").rstrip("/")
templates.env.globals["asset_version"] = str(max(int(p.stat().st_mtime) for p in (HERE / "static").iterdir()))

limiter = Limiter()  # one per process, shared by every visitor


def visitor(request: Request) -> str:
    """The visitor's address. nginx overwrites X-Real-IP with the real one, so it can't be faked."""
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")


def error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status_code)


# ---------------------------------------------------------------------------
# Turning an engine.Answer into what the page shows
# ---------------------------------------------------------------------------
def format_value(value) -> str:
    """One number or word, the way the big answer shows it."""
    value = value.item() if hasattr(value, "item") else value  # numpy number -> plain Python
    if isinstance(value, bool) or value is None:
        return str(value)
    if isinstance(value, float):
        return f"{value:,.2f}".rstrip("0").rstrip(".")  # 8.10 -> 8.1, 12.00 -> 12
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def to_payload(result) -> dict:
    """The JSON the page renders. Every value is JSON-safe (dates as ISO text, NaN as null)."""
    base = {"sql": result.sql, "retried": result.retried}
    if result.refused:
        return base | {"kind": "refused"}
    if result.error:
        return base | {"kind": "error", "error": result.error}

    df = result.df
    if df.shape == (1, 1):
        return base | {"kind": "value", "label": str(df.columns[0]), "value": format_value(df.iloc[0, 0])}

    table = json.loads(df.to_json(orient="split", index=False, date_format="iso"))
    numeric = [df[c].dtype.kind in "iuf" for c in df.columns]
    # A bar chart when there's one label per row and one number: "top 5 categories by revenue".
    chart = len(df.columns) == 2 and 1 < len(df) <= 30 and numeric[1] and df.iloc[:, 0].is_unique
    return base | {
        "kind": "table",
        "columns": [str(c) for c in df.columns],
        "numeric": numeric,
        "rows": table["data"],
        "chart": bool(chart),
        "truncated": len(df) == MAX_ROWS,
    }


def normalise(question: str) -> str:
    return re.sub(r"\s+", " ", question).strip()


@lru_cache(maxsize=512)
def cached_answer(question: str) -> dict:
    """The same question gets the same answer without asking the model again (until a restart)."""
    return to_payload(answer(question))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def scorecard_data():
    """The benchmark results only change with a deploy, so read them once."""
    runs, main_model, ladders = scores.load_runs(preferred=DEFAULT_MODEL)
    return runs, main_model, ladders, scores.headline(runs, main_model) if runs else None


# HEAD as well as GET everywhere a page or check lives, for uptime monitors.
@app.api_route("/healthz", methods=["GET", "HEAD"])
def healthz():
    """The app is up and can open its database. No model call."""
    con = connect()
    try:
        con.execute("SELECT 1").fetchone()
    finally:
        con.close()
    return {"status": "ok"}


@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
def index(request: Request):
    _, main_model, _, headline = scorecard_data()
    return templates.TemplateResponse(request, "index.html", {
        "active": "ask",
        "examples": EXAMPLES,
        "proof": headline,
        "main_model": main_model,
        "model": DEFAULT_MODEL,
        "left": limiter.left(visitor(request)),
        "max_chars": MAX_QUESTION_CHARS,
    })


@app.api_route("/scorecard", methods=["GET", "HEAD"], response_class=HTMLResponse)
def scorecard(request: Request, run: str | None = None):
    runs, main_model, ladders, headline = scorecard_data()
    chosen = next((r for r in runs if r["key"] == run), runs[0] if runs else None)
    return templates.TemplateResponse(request, "scorecard.html", {
        "active": "scorecard",
        "runs": runs,
        "main_model": main_model,
        "headline": headline,
        "ladders": ladders,
        "chosen": chosen,
        "model": DEFAULT_MODEL,
    })


class AskRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)


@app.post("/api/ask")
def ask(body: AskRequest, request: Request):
    who = visitor(request)
    hit = limiter.take(who)
    if hit == "hour":
        return error(429, "You've asked a lot of questions this hour. Please try again later.")
    if hit == "day":
        return error(429, "The site has answered its daily limit of questions. Please come back tomorrow.")

    question = normalise(body.question)
    try:
        payload = cached_answer(question)
    except Exception:
        # Nothing is cached, so asking again really does try again.
        log.exception("Couldn't answer %r", question)
        return error(502, "The model could not be reached. Please try again in a moment.")
    return payload | {"question": question, "left": limiter.left(who)}


@app.exception_handler(404)
def not_found(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api/"):
        return error(404, "Not found.")
    return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
