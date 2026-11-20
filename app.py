"""AI Analyst Copilot - ask business questions in plain English, get SQL, a table, a chart and an explanation."""
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from copilot.core import Copilot
from copilot.llm import LLMError, get_provider
from copilot.viz import suggest_chart

load_dotenv()
try:  # Streamlit Cloud: keys live in st.secrets
    for k in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY"):
        if k in st.secrets:
            os.environ[k] = st.secrets[k]
except Exception:  # noqa: BLE001  (no secrets file locally is fine)
    pass

st.set_page_config(page_title="AI Analyst Copilot", page_icon="📊", layout="wide")

DB_PATH = Path("data/olist.db")
if not DB_PATH.exists():
    with st.spinner("First run: building the database from CSV files (about 20 seconds)..."):
        import load_olist
        load_olist.build(Path("data/raw"), DB_PATH, log=lambda *_: None)

EXAMPLES = [
    "What are the top 10 product categories by revenue from delivered orders?",
    "How many orders were placed in each month of 2018?",
    "Which 5 customer states have the slowest average delivery time?",
    "What percentage of delivered orders arrived after the estimated date?",
    "What is the average review score for late versus on-time deliveries?",
]

with st.sidebar:
    st.header("Settings")
    provider_name = st.selectbox("LLM provider", ["gemini", "groq", "openrouter"],
                                 index=["gemini", "groq", "openrouter"].index(os.getenv("PROVIDER", "groq")))
    model = st.text_input("Model (blank = default)", value="")
    explain = st.toggle("Explain the answer in words", value=True,
                        help="Uses one extra API call per question.")
    st.divider()
    st.caption("Examples")
    for ex in EXAMPLES:
        if st.button(ex, use_container_width=True):
            st.session_state["pending"] = ex
    st.divider()
    st.caption("Data: Olist Brazilian e-commerce (about 100K orders, 2016-2018). "
               "Queries run read-only with row and time limits.")


@st.cache_resource(show_spinner=False)
def get_copilot(provider_name: str, model: str):
    return Copilot(str(DB_PATH), get_provider(provider_name, model or None, min_interval=1.0))


st.title("📊 AI Analyst Copilot")
st.write("Ask a business question about the Olist e-commerce data in plain English.")

try:
    cp = get_copilot(provider_name, model.strip())
except (LLMError, ImportError) as e:
    st.error(f"Could not start the {provider_name} provider: {e}")
    st.stop()

if "history" not in st.session_state:
    st.session_state["history"] = []


def render(res):
    if res.ok:
        if res.explanation:
            st.markdown(res.explanation)
        st.dataframe(res.df, use_container_width=True, hide_index=True)
        if res.truncated:
            st.warning("Result was cut to the first 1,000 rows.")
        chart = suggest_chart(res.df)
        if chart:
            import plotly.express as px
            kind, x, y = chart
            fig = (px.line(res.df, x=x, y=y, markers=True) if kind == "line" else px.bar(res.df, x=x, y=y))
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("I could not produce a working query for that question.")
        st.code(res.error)
    with st.expander(f"SQL used ({res.attempts} attempt{'s' if res.attempts != 1 else ''})"):
        st.code(res.sql, language="sql")


for item in st.session_state["history"]:
    with st.chat_message("user"):
        st.write(item.question)
    with st.chat_message("assistant"):
        render(item)

question = st.chat_input("e.g. Which product categories have the highest freight cost ratio?")
question = st.session_state.pop("pending", None) or question
if question:
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                res = cp.ask(question, explain=explain)
            except LLMError as e:
                st.error(f"The LLM call failed (often a rate limit - wait a minute and retry): {e}")
                st.stop()
        render(res)
    st.session_state["history"].append(res)
