"""Run the benchmark and write results/<setup>__<model>.json.

    python evaluate.py                          # full setup, default model
    python evaluate.py --setup names_only
    python evaluate.py --setup all              # the whole ablation ladder
    python evaluate.py --model gpt-5.4-nano      # any OpenAI chat model

Every question is one API call (two if the retry fires).
"""
import argparse
import json
import math
import os
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from itertools import permutations

import yaml

from engine import CANNOT_ANSWER, DEFAULT_MODEL, SETUPS, USAGE, answer, make_client, run

WORKERS = 6


def clean(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "NULL"
    try:
        return str(round(float(value), 2))
    except (TypeError, ValueError):
        return str(value)


def normalise(df):
    """Rows as a sorted list, so row order and column names don't matter."""
    return sorted(tuple(clean(v) for v in row) for row in df.itertuples(index=False))


def same_result(pred, gold):
    """True if the gold table appears in the predicted one.

    Row order, column order and column names are ignored, and the prediction may
    carry extra columns (a query that also returns a label is not wrong).
    """
    if len(pred) != len(gold) or len(pred.columns) < len(gold.columns) or len(pred.columns) > 6:
        return False
    target = normalise(gold)
    return any(
        normalise(pred.iloc[:, list(cols)]) == target
        for cols in permutations(range(len(pred.columns)), len(gold.columns))
    )


def score(item, setup, model, client):
    result = answer(item["question"], setup=setup, model=model, client=client)
    gold = item["gold_sql"].strip()
    if gold == CANNOT_ANSWER:
        correct = result.refused
    elif result.refused or result.error:
        correct = False
    else:
        correct = same_result(result.df, run(gold))
    return {
        "id": item["id"],
        "difficulty": item["difficulty"],
        "question": item["question"],
        "gold_sql": gold,
        "pred_sql": result.sql,
        "correct": bool(correct),
        "error": result.error,
        "retried": result.retried,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup", default="full", choices=[*SETUPS, "all"])
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    benchmark = yaml.safe_load(open("benchmark.yaml", encoding="utf-8"))
    client = make_client()
    model_slug = args.model.replace("/", "-").replace(":", "-")  # safe in a Windows file name
    os.makedirs("results", exist_ok=True)

    for setup in SETUPS if args.setup == "all" else [args.setup]:
        before = dict(USAGE)
        with ThreadPoolExecutor(WORKERS) as pool:
            items = list(pool.map(partial(score, setup=setup, model=args.model, client=client), benchmark))
        usage = {key: USAGE[key] - before[key] for key in USAGE}
        accuracy = sum(i["correct"] for i in items) / len(items)
        failed = ", ".join(i["id"] for i in items if not i["correct"]) or "none"
        print(f"{setup} / {args.model}: {accuracy:.0%} of {len(items)}  failed: {failed}")
        print(f"  {usage}")
        path = f"results/{setup}__{model_slug}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {"setup": setup, "model": args.model, "accuracy": accuracy, "usage": usage, "items": items},
                f, indent=2,
            )


if __name__ == "__main__":
    main()
