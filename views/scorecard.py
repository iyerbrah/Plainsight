"""Scorecard page. Reads the files evaluate.py writes into results/."""
import glob
import json
import os

import pandas as pd
import streamlit as st
import yaml

from charts import bar_chart

SETUP_LABELS = {
    "names_only": "Table and column names only",
    "notes": "+ written notes about the data",
    "notes_examples": "+ worked examples",
    "full": "+ second attempt if the SQL fails",
}
DIFFICULTIES = ["easy", "medium", "hard", "unanswerable"]

st.title("Scorecard")
st.write("How often the generated SQL returns the same result as a checked reference query, "
         "on 60 test questions.")

paths = glob.glob("results/*.json")
if not paths:
    st.info("No results yet. Run `python evaluate.py` first.")
    st.stop()

runs = [json.load(open(p, encoding="utf-8")) | {"key": os.path.basename(p).removesuffix(".json")} for p in paths]
main_model = max((r["model"] for r in runs), key=lambda m: sum(r["model"] == m for r in runs))
for run in runs:
    model = run["model"].split("/")[-1]
    run["label"] = SETUP_LABELS.get(run["setup"], run["setup"])
    if run["model"] != main_model:
        run["label"] = f"Everything, on {model}"
runs.sort(key=lambda r: (r["model"] != main_model, list(SETUP_LABELS).index(r["setup"])))

by_setup = {r["setup"]: r for r in runs if r["model"] == main_model}
if {"names_only", "notes"} <= by_setup.keys():
    before, after = by_setup["names_only"]["accuracy"], by_setup["notes"]["accuracy"]
    left, middle, right = st.columns(3)
    left.metric("Names only", f"{before:.0%}")
    middle.metric("With written notes", f"{after:.0%}", f"{(after - before) * 100:+.0f} points")
    right.metric("Test questions", len(runs[0]["items"]))

st.subheader("Accuracy by what the model was given")
st.caption(f"Each row adds one thing to the row above. Model: {main_model.split('/')[-1]}, one run per row.")
summary = pd.DataFrame({"Setup": [r["label"] for r in runs], "Accuracy": [r["accuracy"] for r in runs]})
st.altair_chart(bar_chart(summary, "Setup", "Accuracy", ".0%", show_values=True, domain=[0, 1.08]))

st.subheader("Correct answers by difficulty")
table = []
for run in runs:
    row = {"Setup": run["label"]}
    for level in DIFFICULTIES:
        items = [i for i in run["items"] if i["difficulty"] == level]
        row[level.capitalize()] = f"{sum(i['correct'] for i in items)} of {len(items)}"
    table.append(row)
st.dataframe(pd.DataFrame(table), width="stretch", hide_index=True)
st.caption("Hard questions depend on a business rule or a trap in the data. "
           "Unanswerable questions should be refused.")

st.subheader("What went wrong")
chosen = st.selectbox("Run", runs, format_func=lambda r: r["label"])
labels = {}
if os.path.exists("failure_labels.yaml"):
    labels = (yaml.safe_load(open("failure_labels.yaml", encoding="utf-8")) or {}).get(chosen["key"], {})

failures = [i for i in chosen["items"] if not i["correct"]]
if not failures:
    st.success("No failures in this run.")
for item in failures:
    with st.expander(f"{item['question']}  ·  {item['difficulty']}"):
        st.markdown(f"**Why it failed:** {labels.get(item['id'], 'not labelled yet')}")
        generated, reference = st.columns(2)
        generated.caption("Generated")
        generated.code(item["pred_sql"], language="sql", wrap_lines=True)
        reference.caption("Reference")
        reference.code(item["gold_sql"], language="sql", wrap_lines=True)
        if item["error"]:
            st.caption(f"Error: {item['error']}")
