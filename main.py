import streamlit as st
from jira import JIRA
import os
from dotenv import load_dotenv

# --- Load environment variables ---
load_dotenv()
JIRA_URL = os.getenv("JIRA_URL").rstrip("/")
PROJECT_KEY = os.getenv("PROJECT_KEY")
EMAIL = os.getenv("EMAIL")
API_TOKEN = os.getenv("API_TOKEN")
BOARD_ID = int(os.getenv("BOARD_ID", 1))  # Your Scrum board ID

# --- Connect to Jira ---
jira_client = JIRA(server=JIRA_URL, basic_auth=(EMAIL, API_TOKEN))

st.set_page_config(page_title="DevSense - Jira Cockpit", layout="wide")

# --- DevSense Main Page ---
st.title("🚀 DevSense - Jira Intelligence Suite")
st.markdown("""
**DevSense** is your AI-powered Jira cockpit. It helps you manage your Jira workflow efficiently and intelligently.  
Here’s a quick guide to the sections of DevSense:

- **Main** → Overview of DevSense and its features  
- **Home** → Assign tickets automatically, rebalance sprints, create tickets manually or from MoM  
- **NLQ** → Ask questions in natural language about your Jira projects  
- **Analyzer** → Get AI-powered insights and analytics from your tickets and sprints  
- **Dashboard** → View metrics, charts, and backlog/sprint statistics in one place  

Scroll down to see **Active Sprint Tickets** below.
""")

st.divider()

# --- Function to fetch all issues in a sprint using pagination ---
def get_all_sprint_issues(jira_client, project_key, sprint_id):
    all_issues = []
    start_at = 0
    batch_size = 50

    while True:
        issues = jira_client.search_issues(
            f'project = "{project_key}" AND sprint = {sprint_id}',
            startAt=start_at,
            maxResults=batch_size
        )
        if not issues:
            break
        all_issues.extend(issues)
        start_at += len(issues)
        if len(issues) < batch_size:
            break
    return all_issues

# --- Active Sprint Tickets ---
st.header("📊 Tickets in Active Sprints")

all_sprints = jira_client.sprints(BOARD_ID)
active_sprints = [s for s in all_sprints if s.state.lower() == "active"]

if not active_sprints:
    st.info("No active sprints currently running.")
else:
    for sprint in active_sprints:
        st.subheader(f"🟢 Sprint: {sprint.name}")

        issues = get_all_sprint_issues(jira_client, PROJECT_KEY, sprint.id)

        if not issues:
            st.write("No tickets in this sprint.")
            continue

        sprint_data = []
        for issue in issues:
            sprint_data.append({
                "Key": issue.key,
                "Summary": issue.fields.summary,
                "Type": issue.fields.issuetype.name,
                "Assignee": issue.fields.assignee.displayName if issue.fields.assignee else "Unassigned",
                "Status": issue.fields.status.name,
                "Sprint": sprint.name,
                "Description": issue.fields.description or ""
            })

        st.dataframe(sprint_data, use_container_width=True)
