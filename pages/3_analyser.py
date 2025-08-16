import streamlit as st
from jira_ai_analyze import fetch_all_tickets, analyze_ticket

st.title("🧠 AI Ticket Analyzer")

tickets = fetch_all_tickets()

if not tickets:
    st.warning("No tickets found in Jira.")
else:
    
    ticket_keys = [f"{t.get('key', 'N/A')} - {t.get('summary', 'No summary')}" for t in tickets]
    selected = st.selectbox("Select a ticket to analyze:", ticket_keys)

    
    chosen_ticket = tickets[ticket_keys.index(selected)]

    st.write("### Ticket Details")
    st.write(f"**Key:** {chosen_ticket.get('key', 'N/A')}")
    st.write(f"**Summary:** {chosen_ticket.get('summary', 'N/A')}")
    st.write(f"**Status:** {chosen_ticket.get('status', 'N/A')}")
    st.write(f"**Assignee:** {chosen_ticket.get('assignee', 'Unassigned')}")
    st.write(f"**Sprint:** {chosen_ticket.get('sprint', 'No sprint assigned')}")
    st.write(f"**Created:** {chosen_ticket.get('created', 'N/A')}")
    st.write(f"**Description:** {chosen_ticket.get('description', 'No description')}")

    if st.button("Run AI Analysis"):
        insights = analyze_ticket(
            chosen_ticket.get("summary", ""),
            chosen_ticket.get("description", "")
        )
        st.subheader("AI Insights")
        st.write(insights)
