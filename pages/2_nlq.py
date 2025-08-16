import streamlit as st
import re
from jira_nlq import answer_query, load_dataset, HELP_TEXT

# Load Jira data once when app starts
if "jira_data" not in st.session_state:
    st.session_state.jira_data = load_dataset()

st.title("💬 NLQ - Ask Jira in Natural Language")

query = st.text_input("Ask a question (e.g., 'How many tickets are in Sprint 1?')")

if st.button("Run Query") and query.strip():
    result = answer_query(query, st.session_state.jira_data)
    st.write("### Answer")
    st.write(result)

# Extra help option
if st.button("Show Examples"):
    st.markdown(f"```\n{HELP_TEXT}\n```")

# Option to refresh Jira dataset
if st.button("🔄 Refresh Data"):
    st.session_state.jira_data = load_dataset()
    st.success("Jira data reloaded!")
