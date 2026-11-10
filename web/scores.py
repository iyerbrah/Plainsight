"""What the Scorecard page shows, read from the files evaluate.py writes into results/."""
import glob
import json
import os

import yaml

SETUP_LABELS = {
    "names_only": "Table and column names only",
    "notes": "+ written notes about the data",
    "notes_examples": "+ worked examples",
    "full": "+ second attempt if the SQL fails",
}
DIFFICULTIES = ["easy", "medium", "hard", "unanswerable"]


def model_name(model):
    """deepseek/deepseek-v4-pro -> deepseek-v4-pro"""
    return model.split("/")[-1]


def setup_order(setup):
    order = list(SETUP_LABELS)
    return order.index(setup) if setup in order else len(order)


def read_runs(folder="results"):
    """Every results file, with its per-difficulty counts and its failures (with their labelled reasons)."""
    labels = {}
    if os.path.exists("failure_labels.yaml"):
        with open("failure_labels.yaml", encoding="utf-8") as f:
            labels = yaml.safe_load(f) or {}

    runs = []
    for path in glob.glob(os.path.join(folder, "*.json")):
        with open(path, encoding="utf-8") as f:
            run = json.load(f)
        run["key"] = os.path.basename(path).removesuffix(".json")
        run["by_difficulty"] = []
        for level in DIFFICULTIES:
            items = [i for i in run["items"] if i["difficulty"] == level]
            run["by_difficulty"].append({"level": level, "right": sum(i["correct"] for i in items), "total": len(items)})
        reasons = labels.get(run["key"], {})
        run["failures"] = [i | {"reason": reasons.get(i["id"])} for i in run["items"] if not i["correct"]]
        runs.append(run)
    return runs


def load_runs(folder="results", preferred=None):
    """The runs the page lists, the main model, and the ladder on every model that has one.

    The main model is the one the site answers with, if it has been benchmarked, else the
    model with the most runs. The page lists its whole ladder, then the other models'
    full-setup runs for comparison.
    """
    runs = read_runs(folder)
    if not runs:
        return [], None, None
    models = {r["model"] for r in runs}
    main_model = preferred if preferred in models else max(models, key=lambda m: sum(r["model"] == m for r in runs))

    ladder = sorted((r for r in runs if r["model"] == main_model), key=lambda r: setup_order(r["setup"]))
    others = sorted((r for r in runs if r["model"] != main_model and r["setup"] == "full"), key=lambda r: r["model"])
    for run in ladder:
        run["label"] = SETUP_LABELS.get(run["setup"], run["setup"])
    for run in others:
        run["label"] = f"Everything, on {model_name(run['model'])}"

    # The same ladder on each model that ran all of it (or most of it), main model first.
    ladder_models = [main_model] + sorted(m for m in models - {main_model} if sum(r["model"] == m for r in runs) > 1)
    accuracy = {(r["model"], r["setup"]): r["accuracy"] for r in runs}
    table = {
        "models": [model_name(m) for m in ladder_models],
        "rows": [
            {"label": label, "values": [accuracy.get((m, setup)) for m in ladder_models]}
            for setup, label in SETUP_LABELS.items()
        ],
    }
    return ladder + others, main_model, table if len(ladder_models) > 1 else None


def headline(runs, main_model):
    """Names only vs with notes, on the main model, if both runs exist."""
    by_setup = {r["setup"]: r for r in runs if r["model"] == main_model}
    if not {"names_only", "notes"} <= by_setup.keys():
        return None
    before, after = by_setup["names_only"]["accuracy"], by_setup["notes"]["accuracy"]
    unanswerable = [i for i in by_setup["notes"]["items"] if i["difficulty"] == "unanswerable"]
    hard = {r["setup"]: next(d for d in r["by_difficulty"] if d["level"] == "hard") for r in by_setup.values()}
    return {
        "before": before,
        "after": after,
        "gain_points": round((after - before) * 100),
        "questions": len(by_setup["notes"]["items"]),
        "hard_before": hard["names_only"],
        "hard_after": hard["notes"],
        "refused": sum(i["correct"] for i in unanswerable),
        "unanswerable": len(unanswerable),
    }
