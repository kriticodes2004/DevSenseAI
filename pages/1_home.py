import streamlit as st
from datetime import date
from jira import JIRA
from jira_assign import JiraAutoAssigner
from jira_sprint_rebalance import rebalance_sprint
import os
from dotenv import load_dotenv

load_dotenv()
JIRA_URL = os.getenv("JIRA_URL").rstrip("/")
PROJECT_KEY = os.getenv("PROJECT_KEY")
EMAIL = os.getenv("EMAIL")
API_TOKEN = os.getenv("API_TOKEN")
BOARD_ID = int(os.getenv("BOARD_ID", 1)) 

jira_client = JIRA(server=JIRA_URL, basic_auth=(EMAIL, API_TOKEN))

st.title("Home - Ticket Management")

col1, col2 = st.columns(2)

with col1:
    st.header("Assign Tickets")
    if st.button("Auto-assign tickets"):
        try:
            JiraAutoAssigner().run()
            st.success("✅ Tickets assigned successfully!")
        except Exception as e:
            st.error(f" Failed to assign: {e}")

with col2:
    st.header("Rebalance Sprint")
    sprint_id = st.text_input("Enter Sprint ID")
    if st.button("Rebalance tickets"):
        if not sprint_id:
            st.warning("⚠ Please enter a sprint ID first")
        else:
            try:
                rebalance_sprint(sprint_id)
                st.success("✅ Tickets rebalanced successfully!")
            except Exception as e:
                st.error(f"Failed to rebalance: {e}")

st.divider()

st.header("Create Manual Ticket in Backlog")
summary = st.text_input("Summary")
description = st.text_area("Description")
issue_type = st.selectbox("Type", ["Bug", "Feature", "Task", "Request"])

if st.button("Create Manual Ticket"):
    if not summary.strip() or not description.strip():
        st.warning("⚠ Summary and Description are required")
    else:
        new_issue = jira_client.create_issue(
            project=PROJECT_KEY,
            summary=summary,
            description=description,
            issuetype={"name": issue_type}
        )
        st.success(f"✅ Ticket {new_issue.key} created in backlog!")

st.divider()

st.header("Backlog Tickets")
backlog_issues = jira_client.search_issues(
    f'project = "{PROJECT_KEY}" AND sprint IS EMPTY AND statusCategory = "To Do"',
    maxResults=100
)
backlog_data = [
    {
        "Key": issue.key,
        "Summary": issue.fields.summary,
        "Type": issue.fields.issuetype.name,
        "Assignee": issue.fields.assignee.displayName if issue.fields.assignee else "Unassigned",
        "Description": issue.fields.description or ""
    }
    for issue in backlog_issues
]
st.table(backlog_data)

st.divider()

st.header(" Add Backlog to Sprint")
sprint_name = st.text_input("Sprint Name")

if st.button("Add Backlog to Sprint"):
    if not sprint_name.strip():
        st.warning("⚠ Please enter a sprint name")
    else:
        
        sprints = jira_client.sprints(BOARD_ID)
        sprint = next((s for s in sprints if s.name == sprint_name), None)

        if not sprint:
            
            sprint = jira_client.create_sprint(
                name=sprint_name,
                board_id=BOARD_ID,
                startDate=str(date.today())
            )
            st.info(f"Created new sprint '{sprint_name}' starting today")

        
        backlog_issues = jira_client.search_issues(
            f'project = "{PROJECT_KEY}" AND sprint IS EMPTY AND statusCategory = "To Do"',
            maxResults=100
        )

        
        sprint_issues = jira_client.search_issues(f'project = "{PROJECT_KEY}" AND sprint = {sprint.id}')
        sprint_keys = [i.key for i in sprint_issues]
        issue_keys_to_add = [i.key for i in backlog_issues if i.key not in sprint_keys]

        if issue_keys_to_add:
            jira_client.add_issues_to_sprint(sprint.id, issue_keys_to_add)
            st.success(f"✅ {len(issue_keys_to_add)} backlog tickets added to sprint '{sprint_name}'")
        else:
            st.info("No tickets in backlog to add")
