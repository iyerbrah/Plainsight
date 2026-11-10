"""same_result(): when a generated table counts as the same answer as the reference."""
import pandas as pd

from evaluate import same_result

GOLD = pd.DataFrame({"state": ["SP", "RJ"], "orders": [41746, 12852]})


def test_ignores_row_order_and_column_names():
    pred = pd.DataFrame({"s": ["RJ", "SP"], "n": [12852, 41746]})
    assert same_result(pred, GOLD)


def test_ignores_column_order():
    assert same_result(GOLD[["orders", "state"]], GOLD)


def test_allows_an_extra_column():
    pred = GOLD.assign(share=[0.7, 0.3])
    assert same_result(pred, GOLD)


def test_rounds_to_two_decimals():
    gold = pd.DataFrame({"x": [1.234]})
    assert same_result(pd.DataFrame({"x": [1.2349]}), gold)
    assert not same_result(pd.DataFrame({"x": [1.25]}), gold)


def test_wrong_values_or_row_count_fail():
    assert not same_result(pd.DataFrame({"s": ["SP", "RJ"], "n": [41746, 1]}), GOLD)
    assert not same_result(GOLD.head(1), GOLD)


def test_missing_column_fails():
    assert not same_result(GOLD[["state"]], GOLD)


def test_nulls_match_nulls():
    gold = pd.DataFrame({"x": [None, 1.0]})
    assert same_result(pd.DataFrame({"y": [float("nan"), 1.0]}), gold)
