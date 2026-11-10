# Plainsight

Ask a business question in plain English and get the answer from a real database, along
with the SQL that produced it. Then see how often those answers are actually right.

**Try it:** https://ask-the-olist-data-5bcmydxcckwd6pjb5cybm7.streamlit.app/

**Built with:** Python, SQL (DuckDB), Streamlit, Altair, sqlglot, the OpenAI API (gpt-5.4-mini)

![The Scorecard page: accuracy for each setup on the 60 test questions](docs/scorecard.png)

## The finding

> These results were measured on DeepSeek V4 Pro before the app moved to OpenAI's gpt-5.4-mini.
> A rerun on gpt-5.4-mini, three runs per setup with ten harder questions, is in progress.

A language model given only the table and column names answered **83%** of 60 test
questions correctly. Given a page of written notes explaining what the data means, it
answered **98%**. Nothing else that was tried made a measurable difference.

The model was never bad at SQL. It was missing what the business means by its own words:
what counts as revenue, and what counts as a customer.

## Why I built it

Tools that let people ask data questions in plain English are easy to demo and hard to
trust: a wrong number looks exactly like a right one. I wanted to measure how often the
answers are right, and find out what actually makes them right.

## What it does

Type a question such as *"Which 5 categories have the highest revenue?"* and the app:

1. Sends the question to a language model, together with notes describing the database.
2. Gets a SQL query back.
3. Checks the query is safe to run (read-only, one statement).
4. Runs it and shows the result table, a chart, and the SQL itself.

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

| What the model was given | Correct | Hard questions |
|---|---|---|
| Table and column names only | 50 of 60 (83%) | 6 of 15 |
| + written notes about the data | 59 of 60 (98%) | 15 of 15 |
| + six worked examples | 58 of 60 (97%) | 15 of 15 |
| + a second attempt if the SQL fails | 59 of 60 (98%) | 15 of 15 |
| Everything, on a model costing a fifth as much | 57 of 60 (95%) | 15 of 15 |

What this shows:

- **The written notes do almost all the work.** Without them, 9 of the 15 hard questions
  fail, and every failure is a missing business rule. The SQL was valid each time.
- **Worked examples and the second attempt added nothing measurable.** Those rows differ
  by one question, which is within the variation between runs. The second attempt was
  never needed: no generated query failed to run.
- **The examples caused a new mistake.** One example filters revenue to delivered orders.
  After seeing it, both models added that filter to questions that did not ask for it.
  All three errors of the cheaper model are this one mistake.
- **The "cannot be answered" questions are too easy.** All 10 were refused in every row,
  so they are not a real test yet.

Every failed question, with the generated and the reference SQL side by side, is on the
Scorecard page of the live app.

## Limits

- Each row is one run, so a difference of one or two questions means nothing.
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
  has a ceiling.

The tests in `tests/` check each of these on every pull request.

## Cost

All five benchmark runs together cost about $0.09 in model usage.

## Run it yourself

1. With Python 3.11 or newer: `pip install -r requirements.txt`
2. Download the Olist dataset from Kaggle and unzip the CSVs into `data/`.
3. `python build_db.py`
4. Create `.streamlit/secrets.toml` containing one line: `OPENAI_API_KEY = "sk-..."` (or set the `OPENAI_API_KEY` environment variable).
5. `streamlit run app.py`

To rerun the benchmark: `python evaluate.py --setup all`

To run the tests (offline, no API key needed): `pip install -r requirements-dev.txt`, then `pytest`

## Files

| File | Purpose |
|---|---|
| `app.py` | Entry point and page navigation |
| `views/ask.py`, `views/scorecard.py` | The two pages of the app |
| `charts.py` | The bar chart both pages use |
| `engine.py` | Builds the prompt, calls the model, checks and runs the SQL |
| `limits.py` | Questions per visitor per hour, and per day for the whole site |
| `tests/` | Offline tests: SQL safety, scoring, every reference query, limits, both pages |
| `schema.md` | The written notes about the data that are sent to the model |
| `examples.yaml` | The six worked examples |
| `benchmark.yaml` | The 60 test questions and reference SQL |
| `evaluate.py` | Runs the benchmark and writes a results file per run |
| `results/` | Every question, generated query and outcome for each run |
| `failure_labels.yaml` | The reason for each failed question |
| `build_db.py` | Loads the CSVs into the database file |
| `olist.duckdb` | The database itself, so the app runs without the download |
| `docs/` | Screenshot used in this README |
