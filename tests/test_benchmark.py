"""The benchmark itself: every reference query must run, and nothing may leak from the examples."""
from collections import Counter

import pytest
import yaml

from engine import CANNOT_ANSWER, check, run

BENCHMARK = yaml.safe_load(open("benchmark.yaml", encoding="utf-8"))
EXAMPLES = yaml.safe_load(open("examples.yaml", encoding="utf-8"))
ANSWERABLE = [i for i in BENCHMARK if i["gold_sql"].strip() != CANNOT_ANSWER]


def test_ids_are_unique():
    ids = [i["id"] for i in BENCHMARK]
    assert len(ids) == len(set(ids))


def test_counts_match_the_readme():
    counts = Counter(i["difficulty"] for i in BENCHMARK)
    assert counts == {"easy": 15, "medium": 20, "hard": 15, "unanswerable": 10}


def test_only_unanswerable_questions_are_refused():
    for item in BENCHMARK:
        refused = item["gold_sql"].strip() == CANNOT_ANSWER
        assert refused == (item["difficulty"] == "unanswerable"), item["id"]


@pytest.mark.parametrize("item", ANSWERABLE, ids=[i["id"] for i in ANSWERABLE])
def test_reference_query_is_safe_and_returns_rows(item):
    check(item["gold_sql"])
    assert len(run(item["gold_sql"])) > 0


def test_examples_do_not_overlap_the_benchmark():
    questions = {i["question"].strip().lower() for i in BENCHMARK}
    assert not [e for e in EXAMPLES if e["question"].strip().lower() in questions]
