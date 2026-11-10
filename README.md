# Plainsight

Ask a business question in plain English and get the answer from a real database, along
with the SQL that produced it. Then see how often those answers are actually right.

**Live:** https://plainsight.ramiyer.tech

**Built with:** Python, SQL (DuckDB), FastAPI, sqlglot, the OpenAI API (gpt-5.4-mini), and plain
HTML, CSS and JavaScript for the pages

![The Ask page: a question box over the data, with an example question, its SQL and its answer](docs/home.jpg)

## The finding

A language model given only the table and column names answered **85%** of 60 test
questions correctly. Given a page of written notes explaining what the data means, it
answered **100%**. Nothing else that was tried made a measurable difference.

That's gpt-5.4-mini, the model the site uses. The same test on DeepSeek V4 Pro, run first,
gave the same picture: 83% without the notes, 98% with them.

The model was never bad at SQL. It was missing what the business means by its own words:
what counts as revenue, and what counts as a customer.

![The Scorecard page: accuracy for each setup on the 60 test questions](docs/scorecard.jpg)

## Why I built it

Tools that let people ask data questions in plain English are easy to demo and hard to
trust: a wrong number looks exactly like a right one. I wanted to measure how often the
answers are right, and find out what actually makes them right.

## What it does

Type a question such as *"Which 5 categories have the highest revenue?"* and the app:

1. Sends the question to a language model, together with notes describing the database.
2. Gets a SQL query back.
3. Checks the query is safe to run (read-only, one statement).
4. Runs it and shows the answer: one big number, or a bar chart and the rows, always with the SQL itself.

| category | revenue |
|---|---|
| health_beauty | 1,233,131.72 |
| watches_gifts | 1,166,176.98 |
| bed_bath_table | 1,023,434.76 |
| sports_leisure | 954,852.55 |
| computers_accessories | 888,724.61 |

The data is the public Olist dataset: about 100,000 orders from a Brazilian online
marketplace, 2016 to 2018, across eight tables.

## How accuracy is measured

The repository contains 60 test questions, each with a reference SQL query whose answer
was checked against the database.

| Difficulty | Questions | Example |
|---|---|---|
| Easy | 15 | How many orders were canceled? |
| Medium | 20 | Which 5 customer states placed the most orders? |
| Hard | 15 | How many customers have placed more than one order? |
| Cannot be answered | 10 | What is the profit margin for each category? |

A generated query counts as correct when it returns the same table as the reference
query. The SQL text does not have to match, because two different queries can both be
right. For the last group, the correct response is to say the data cannot answer it.

The hard questions are hard because of the data, not the SQL. For example, the customer
id in this dataset changes with every order, so counting repeat customers with the
obvious column always gives zero.

## Results

Each row adds one thing to the row above it, to show what that addition is worth.
gpt-5.4-mini ran with reasoning effort `low`, as on the site.

| What the model was given | gpt-5.4-mini | Hard questions | DeepSeek V4 Pro |
|---|---|---|---|
| Table and column names only | 51 of 60 (85%) | 7 of 15 | 50 of 60 (83%) |
| + written notes about the data | 60 of 60 (100%) | 15 of 15 | 59 of 60 (98%) |
| + six worked examples | 59 of 60 (98%) | 15 of 15 | 58 of 60 (97%) |
| + a second attempt if the SQL fails | 60 of 60 (100%) | 15 of 15 | 59 of 60 (98%) |

DeepSeek V4 Flash, a model costing a fifth as much as V4 Pro, got 57 of 60 (95%) with everything.

What this shows:

- **The written notes do the work.** Without them, gpt-5.4-mini gets 8 of the 15 hard
  questions wrong. Seven are a missing business rule: what counts as revenue, which orders
  count, and the customer id that is new for every order. The eighth is a query that
  referred to a table it never named. With the notes, all 15 are right.
- **Worked examples and the second attempt added nothing measurable.** Those rows differ
  by one question, which is within the variation between runs. The second attempt was
  never needed: with the notes, no generated query failed to run.
- **The examples caused a new mistake.** One example filters revenue to delivered orders.
  After seeing it, every model added that filter to a question that did not ask for it.
  All three errors of DeepSeek V4 Flash are this one mistake.
- **The "cannot be answered" questions are nearly too easy.** With the notes, all 10 were
  refused on every model. Without them, gpt-5.4-mini answered one: it called item prices
  the cost of goods sold.

Every failed question, with the generated and the reference SQL side by side and the
reason it failed, is on the Scorecard page.

## Limits

- Each row is one run, so a difference of one or two questions means nothing. A perfect
  score on 60 questions doesn't mean the next question will be answered right.
- 60 questions on one database is a small test.
- The notes and the questions were written together, so the hard questions measure
  whether the model follows stated rules, not whether it could work them out.
- Scoring is lenient: a result with extra columns still counts as correct.

## Safety

The app runs SQL written by a model, from text typed by anyone, so it does not rely on
the model behaving:

- The query is parsed, and anything other than a single `SELECT` is rejected.
- The database connection is read-only.
- Queries cannot read files or web addresses.
- Results are capped at 1,000 rows and 15 seconds.
- Each visitor can ask 20 questions an hour, and the whole site 300 a day, so the model bill
  has a ceiling. nginx adds a looser per-address cap on the live server as a backstop.

The tests in `tests/` check each of these on every pull request.

## Cost

The four gpt-5.4-mini benchmark runs (240 questions) cost about $0.29 at OpenAI's list
price of $0.75 per million input tokens and $4.50 per million output tokens. The five earlier
DeepSeek runs cost about $0.09 together.

On the site, one question costs about $0.0015, so even a day at the 300-question cap costs
under $0.50.

## Run it yourself

With Python 3.11 or newer, from the project folder:

1. `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`
2. `cp .env.example .env`, then paste your OpenAI key after `OPENAI_API_KEY=` in `.env`
   (it's ignored by git, so the key never gets committed).
3. `.venv/bin/uvicorn web.main:app --reload --port 8100`, then open http://127.0.0.1:8100

Restart the app after changing `.env`; it reads the file when it starts.

- Tests (offline: no key, no model calls, no cost): `.venv/bin/pytest`
- Rerun the benchmark (about $0.30 on gpt-5.4-mini): `.venv/bin/python evaluate.py --setup all`
- The database (`olist.duckdb`) is in the repository. To rebuild it from the source: download
  the Olist dataset from Kaggle, unzip the CSVs into `data/` and run `.venv/bin/python build_db.py`.

## Files

| File | Purpose |
|---|---|
| `web/` | The website: `main.py` (pages and the `/api/ask` endpoint), `scores.py` (Scorecard data), templates, CSS and JavaScript |
| `engine.py` | Builds the prompt, calls the model, checks and runs the SQL |
| `limits.py` | Questions per visitor per hour, and per day for the whole site |
| `tests/` | Offline tests: SQL safety, scoring, every reference query, limits, the website |
| `schema.md` | The written notes about the data that are sent to the model |
| `examples.yaml` | The six worked examples |
| `benchmark.yaml` | The 60 test questions and reference SQL |
| `evaluate.py` | Runs the benchmark and writes a results file per run |
| `results/` | Every question, generated query and outcome for each run |
| `failure_labels.yaml` | The reason for each failed question |
| `build_db.py` | Loads the CSVs into the database file |
| `olist.duckdb` | The database itself, so the app runs without the download |
| `.env.example` | Every setting, with what it does; copy it to `.env` for local use |
| `.github/workflows/ci.yml` | Lint and the offline tests on every pull request |
| `docs/` | Screenshots used in this README |
