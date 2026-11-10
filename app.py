"""Entry point. Run with: streamlit run app.py"""
import os

import streamlit as st

st.set_page_config(page_title="Plainsight", page_icon=":material/database:")

try:
    os.environ.setdefault("OPENAI_API_KEY", st.secrets["OPENAI_API_KEY"])
except Exception:
    pass  # no secrets file: fall back to the environment variable

pages = [
    st.Page("views/ask.py", title="Ask", icon=":material/chat:", default=True),
    st.Page("views/scorecard.py", title="Scorecard", icon=":material/fact_check:", url_path="Scorecard"),
]
st.navigation(pages).run()
