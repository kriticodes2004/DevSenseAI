# pages/4_dashboard.py
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from sprint_report import generate_scrum_sprint_report

st.title("📊 Dashboard - Jira Metrics")

sprint = st.text_input("Sprint Name (e.g., S1)")
start = st.date_input("Start Date")
end = st.date_input("End Date")

def plot_bar_chart_with_labels(data_dict, title):
    fig, ax = plt.subplots(figsize=(5, 3))
    keys = list(data_dict.keys())
    values = list(data_dict.values())
    bars = ax.bar(keys, values, color="skyblue")
    ax.set_title(title)
    ax.bar_label(bars, labels=[str(v) for v in values], padding=2)
    plt.xticks(rotation=45, ha="right")
    st.pyplot(fig)

def plot_pie_chart(data_dict, title):
    fig, ax = plt.subplots(figsize=(5, 3))
    ax.pie(data_dict.values(), labels=data_dict.keys(), autopct="%1.1f%%", startangle=90, colors=plt.cm.Paired.colors)
    ax.set_title(title)
    st.pyplot(fig)

if st.button("Generate Report"):
    from jira_ai_analyze import fetch_all_tickets

    tickets = fetch_all_tickets()  # list of dicts
    tickets_df = pd.DataFrame(tickets)

    if tickets_df.empty:
        st.warning("No tickets found. Please check your Jira connection or filters.")
    else:
        metrics = generate_scrum_sprint_report(tickets_df, sprint, start, end)

        # ---- Charts in two columns ----
        col1, col2 = st.columns(2)

        with col1:
            if metrics["ticket_by_status"]:
                plot_pie_chart(metrics["ticket_by_status"], "Tickets by Status")
            else:
                st.info("No status data available.")

        with col2:
            if metrics["ticket_by_team"]:
                plot_bar_chart_with_labels(metrics["ticket_by_team"], "Tickets by Team")
            else:
                st.info("No team data available.")

        # Next row for person-based charts
        col3, col4 = st.columns(2)
        with col3:
            if metrics["most_tickets_closed"]:
                plot_bar_chart_with_labels(metrics["most_tickets_closed"], "Most Tickets Closed by Person")
            else:
                st.info("No data for Most Tickets Closed.")

        with col4:
            if metrics["load_per_person"]:
                plot_bar_chart_with_labels(metrics["load_per_person"], "Load per Person (Open Tickets)")
            else:
                st.info("No data for Load per Person.")

        # ---- Sprint Progress Metric ----
        st.subheader("Sprint Progress (%)")
        st.metric(label="Completion", value=f"{metrics['sprint_progress']:.2f}%")

        # ---- Tables ----
        st.subheader("Open Tickets")
        if metrics["open_tickets_list"]:
            st.dataframe(pd.DataFrame(metrics["open_tickets_list"]))
        else:
            st.info("No open tickets.")

        st.subheader("Closed Tickets")
        if metrics["closed_tickets_list"]:
            st.dataframe(pd.DataFrame(metrics["closed_tickets_list"]))
        else:
            st.info("No closed tickets.")
