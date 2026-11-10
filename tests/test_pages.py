"""Both pages render without errors (no question is asked, so no model is called)."""
from conftest import ROOT
from streamlit.testing.v1 import AppTest


def test_scorecard_page():
    at = AppTest.from_file(str(ROOT / "views/scorecard.py"), default_timeout=30).run()
    assert not at.exception
    assert at.metric[0].label == "Names only"
    assert len(at.dataframe) == 1


def test_scorecard_failure_list_follows_the_chosen_run():
    at = AppTest.from_file(str(ROOT / "views/scorecard.py"), default_timeout=30).run()
    first = [e.label for e in at.expander]
    at.selectbox[0].select_index(1).run()
    assert not at.exception
    assert [e.label for e in at.expander] != first


def test_ask_page_without_a_question():
    at = AppTest.from_file(str(ROOT / "views/ask.py"), default_timeout=30).run()
    assert not at.exception
    assert at.text_input[0].label == "Your question"
