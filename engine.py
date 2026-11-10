"""Question -> SQL -> safety check -> result."""
import os
import threading
from dataclasses import dataclass

import duckdb
import pandas as pd
import sqlglot
import yaml
from dotenv import load_dotenv
from openai import OpenAI
from sqlglot import exp

# Settings and the API key come from the environment. Locally they can sit in a .env file
# in the project folder (see .env.example); real environment variables win over it.
load_dotenv()

DB_PATH = "olist.duckdb"
# Who serves the model: "openai", or "openrouter" (same API, different address and key).
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openai").strip().lower()
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# Each provider has its own model setting, so switching LLM_PROVIDER is the only change needed.
MODEL_DEFAULTS = {
    "openai": ("OPENAI_MODEL", "gpt-5.4-mini"),
    "openrouter": ("OPENROUTER_MODEL", "nvidia/nemotron-3.5-super-vl:free"),
}
_model_var, _model_default = MODEL_DEFAULTS.get(LLM_PROVIDER, MODEL_DEFAULTS["openai"])
DEFAULT_MODEL = os.environ.get(_model_var, "").strip() or _model_default
# How long the model thinks before answering: none, low, medium or high.
REASONING_EFFORT = os.environ.get("REASONING_EFFORT", "low")
CANNOT_ANSWER = "CANNOT_ANSWER"
MAX_ROWS = 1000
QUERY_TIMEOUT_S = 15

# Running token totals for this process, so evaluate.py can report what a run used.
USAGE = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
_usage_lock = threading.Lock()

# The ablation ladder: each setup adds one thing to the one before it.
SETUPS = {
    "names_only": dict(notes=False, examples=False, retry=False),
    "notes": dict(notes=True, examples=False, retry=False),
    "notes_examples": dict(notes=True, examples=True, retry=False),
    "full": dict(notes=True, examples=True, retry=True),
}


@dataclass
class Answer:
    sql: str
    df: pd.DataFrame | None = None
    error: str | None = None
    retried: bool = False

    @property
    def refused(self):
        return self.sql == CANNOT_ANSWER


def api_key():
    """The provider's key (OPENAI_API_KEY or OPENROUTER_API_KEY) from the environment or the local .env file."""
    if LLM_PROVIDER not in ("openai", "openrouter"):
        raise RuntimeError(f"LLM_PROVIDER must be openai or openrouter, not {LLM_PROVIDER!r}.")
    name = "OPENROUTER_API_KEY" if LLM_PROVIDER == "openrouter" else "OPENAI_API_KEY"
    key = os.environ.get(name, "").strip()
    if not key:
        raise RuntimeError(f"{name} isn't set. Paste your key into .env in the project folder (see .env.example).")
    return key


def make_client():
    if LLM_PROVIDER == "openrouter":
        return OpenAI(api_key=api_key(), base_url=OPENROUTER_BASE_URL)
    return OpenAI(api_key=api_key())


def connect():
    con = duckdb.connect(DB_PATH, read_only=True)
    con.execute("SET enable_external_access = false")  # no reading files or URLs from SQL
    return con


def names_only_schema():
    con = connect()
    try:
        rows = con.execute(
            "SELECT table_name, string_agg(column_name || ' ' || data_type, ', ' ORDER BY ordinal_position) "
            "FROM information_schema.columns GROUP BY table_name ORDER BY table_name"
        ).fetchall()
    finally:
        con.close()
    return "\n".join(f"{table}({cols})" for table, cols in rows)


def build_system(notes, examples):
    schema = open("schema.md", encoding="utf-8").read() if notes else names_only_schema()
    system = (
        "You write DuckDB SQL for the database described below.\n"
        "Reply with exactly one SELECT query and nothing else: no explanation, no code fences.\n"
        f"If the question cannot be answered from this data, reply with exactly: {CANNOT_ANSWER}\n\n"
        f"{schema}"
    )
    if examples:
        pairs = yaml.safe_load(open("examples.yaml", encoding="utf-8")) or []
        shots = "\n\n".join(f"Question: {p['question']}\nSQL: {p['sql']}" for p in pairs)
        system += f"\n\n## Examples\n\n{shots}"
    return system


def generate_sql(client, system, question, model, error=None):
    content = question
    if error:
        content += f"\n\nYour previous query failed with this error:\n{error}\nReturn a corrected query."
    response = client.chat.completions.create(
        model=model,
        max_completion_tokens=8000,
        reasoning_effort=REASONING_EFFORT,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": content}],
    )
    if response.usage:
        with _usage_lock:
            USAGE["calls"] += 1
            USAGE["input_tokens"] += response.usage.prompt_tokens
            USAGE["output_tokens"] += response.usage.completion_tokens
    text = (response.choices[0].message.content or "").strip()
    return text.removeprefix("```sql").removeprefix("```").removesuffix("```").strip().rstrip(";")


def check(sql):
    statements = sqlglot.parse(sql, read="duckdb")
    if len(statements) != 1 or not isinstance(statements[0], (exp.Select, exp.Union)):
        raise ValueError("Only a single SELECT query is allowed.")


def run(sql):
    con = connect()
    timer = threading.Timer(QUERY_TIMEOUT_S, con.interrupt)
    timer.start()
    try:
        return con.execute(f"SELECT * FROM ({sql}) LIMIT {MAX_ROWS}").df()
    finally:
        timer.cancel()
        con.close()


def answer(question, setup="full", model=DEFAULT_MODEL, client=None):
    client = client or make_client()
    cfg = SETUPS[setup]
    system = build_system(cfg["notes"], cfg["examples"])

    sql = generate_sql(client, system, question, model)
    if sql == CANNOT_ANSWER:
        return Answer(sql)
    try:
        check(sql)
        return Answer(sql, run(sql))
    except Exception as e:
        # Python clears `e` when the except block ends, so keep the message.
        first_error = str(e)
        if not cfg["retry"]:
            return Answer(sql, error=first_error)

    sql = generate_sql(client, system, question, model, error=first_error)
    if sql == CANNOT_ANSWER:
        return Answer(sql, retried=True)
    try:
        check(sql)
        return Answer(sql, run(sql), retried=True)
    except Exception as second_error:
        return Answer(sql, error=str(second_error), retried=True)
