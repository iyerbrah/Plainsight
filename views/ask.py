"""Ask page."""
import streamlit as st

from charts import bar_chart
from engine import DEFAULT_MODEL, answer
from limits import Limiter

EXAMPLES = [
    "Which 5 categories have the highest revenue?",
    "How many customers have placed more than one order?",
    "What percentage of delivered orders were late?",
    "Which month had the highest revenue?",
    "What is the profit margin for each category?",
]


@st.cache_data(show_spinner=False)
def cached_answer(question):
    return answer(question)


@st.cache_resource
def limiter():
    """One limiter shared by every visitor's session."""
    return Limiter()


def visitor():
    """The visitor's address. nginx overwrites X-Real-IP with the real one, so it can't be faked."""
    address = st.context.headers.get("X-Real-IP") or st.context.ip_address
    return address if isinstance(address, str) and address else "unknown"


def show_result(result):
    if result.refused:
        st.warning("This can't be answered from the data in this database.", icon=":material/block:")
        st.caption("The database has orders, items, payments, reviews, customers, products and sellers. "
                   "It has no costs, product names, customer details or marketing data.")
        return
    if result.error:
        st.error("The generated query could not be run.", icon=":material/error:")
        with st.expander("Details"):
            st.code(result.sql, language="sql", wrap_lines=True)
            st.caption(result.error)
        return

    df = result.df
    if df.shape == (1, 1):
        value = df.iloc[0, 0]
        value = value.item() if hasattr(value, "item") else value  # numpy number -> plain Python
        if isinstance(value, float):
            shown = f"{value:,.2f}"
        elif isinstance(value, int):
            shown = f"{value:,}"
        else:
            shown = str(value)
        st.metric("Answer", shown)
    else:
        numeric = df.dtypes.iloc[-1].kind in "if"
        if len(df.columns) == 2 and 1 < len(df) <= 30 and numeric and df.iloc[:, 0].is_unique:
            st.altair_chart(bar_chart(df.astype({df.columns[0]: str}), df.columns[0], df.columns[1], ",.2~f"))
        st.dataframe(df, width="stretch", hide_index=True)
        if len(df) == 1000:
            st.caption("Showing the first 1,000 rows.")

    with st.expander("SQL used for this answer", expanded=True):
        st.code(result.sql, language="sql", wrap_lines=True)
        if result.retried:
            st.caption("The first attempt failed; this is the corrected query.")


def show_sidebar():
    with st.sidebar:
        st.subheader("About")
        st.write("Questions are turned into SQL by a language model, checked, and run on a read-only "
                 "database of about 100,000 orders from a Brazilian marketplace (2016 to 2018).")
        st.write("The **Scorecard** page shows how often the answers are right.")
        st.caption(f"Model: {DEFAULT_MODEL}")
        st.caption(f"Questions you can ask this hour: {limiter().left(visitor())}")


st.title("Plainsight")
st.write("Ask a business question in plain English. You get the answer and the SQL that produced it.")

picked = st.pills("Try one", EXAMPLES, label_visibility="collapsed")
if picked and picked != st.session_state.get("last_pick"):
    st.session_state["last_pick"] = picked
    st.session_state["question"] = picked

question = st.text_input("Your question", key="question", placeholder="Which 5 states have the most customers?")

if question:
    # Count each new question once; Streamlit reruns this script on every click.
    if question != st.session_state.get("counted"):
        hit = limiter().take(visitor())
        if hit:
            st.error("You've asked a lot of questions this hour. Please try again later." if hit == "hour"
                     else "The site has answered its daily limit of questions. Please come back tomorrow.",
                     icon=":material/hourglass:")
            show_sidebar()
            st.stop()
        st.session_state["counted"] = question

    show_sidebar()
    try:
        with st.spinner("Writing and running SQL..."):
            result = cached_answer(question)
    except Exception:
        st.error("The model could not be reached. Please try again in a moment.", icon=":material/cloud_off:")
        st.stop()
    show_result(result)
else:
    show_sidebar()
