import os
import json
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
import google.generativeai as genai
from team import TEAM_MEMBERS

# Load environment variables
load_dotenv()

JIRA_URL = os.getenv("JIRA_URL")
EMAIL = os.getenv("EMAIL")
API_TOKEN = os.getenv("API_TOKEN")
PROJECT_KEY = os.getenv("PROJECT_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-1.5-flash")

auth = HTTPBasicAuth(EMAIL, API_TOKEN)
headers = {"Accept": "application/json", "Content-Type": "application/json"}


# ---------- 1. Fetch backlog tickets ----------
def fetch_backlog_tickets():
    jql = f'project = "{PROJECT_KEY}" AND sprint is EMPTY ORDER BY created DESC'
    params = {
        "jql": jql,
        "fields": "summary,description,assignee"
    }
    resp = requests.get(f"{JIRA_URL}/rest/api/3/search", headers=headers, params=params, auth=auth)
    resp.raise_for_status()
    return resp.json().get("issues", [])


# ---------- 2. AI estimate story points ----------
def ai_estimate_story_points(title, description):
    prompt = f"""
    You are a Jira Scrum Master.
    Estimate the story points for this ticket based on its title and description:
    Title: {title}
    Description: {description or 'No description'}
    Give only a number (1, 2, 3, 5, 8, 13).
    """
    resp = gemini_model.generate_content(prompt)
    try:
        return int(resp.text.strip().split()[0])
    except:
        return 3  # fallback


# ---------- 3. AI assign team member ----------
def ai_assign_team(description):
    prompt = f"""
    You are assigning a Jira ticket to a team member.
    Choose one of these teams based on the work described:
    {list(TEAM_MEMBERS.keys())}
    Ticket description: {description or 'No description'}
    Respond with only the team name.
    """
    resp = gemini_model.generate_content(prompt)
    team_name = resp.text.strip()
    return TEAM_MEMBERS.get(team_name, TEAM_MEMBERS["General"])


# ---------- 4. Create sprint ----------
def create_sprint(sprint_name, start_date=None, end_date=None):
    payload = {
        "name": sprint_name,
        "originBoardId": get_board_id(),
    }
    if start_date and end_date:
        payload["startDate"] = start_date
        payload["endDate"] = end_date

    resp = requests.post(f"{JIRA_URL}/rest/agile/1.0/sprint", headers=headers, auth=auth, json=payload)
    resp.raise_for_status()
    return resp.json()


def get_board_id():
    resp = requests.get(f"{JIRA_URL}/rest/agile/1.0/board", headers=headers, auth=auth)
    resp.raise_for_status()
    boards = resp.json().get("values", [])
    if not boards:
        raise ValueError("No boards found")
    return boards[0]["id"]


# ---------- 5. Add issues to sprint ----------
def add_issues_to_sprint(sprint_id, issue_ids):
    for issue_id in issue_ids:
        url = f"{JIRA_URL}/rest/agile/1.0/sprint/{sprint_id}/issue"
        payload = {"issues": [issue_id]}
        resp = requests.post(url, headers=headers, auth=auth, json=payload)
        resp.raise_for_status()


# ---------- MAIN ----------
def main():
    backlog = fetch_backlog_tickets()
    print(f"Fetched {len(backlog)} backlog tickets")

    sprint_name = input("Enter sprint name: ")
    sprint = create_sprint(sprint_name)
    sprint_id = sprint["id"]

    issues_to_add = []
    for ticket in backlog:
        key = ticket["key"]
        summary = ticket["fields"]["summary"]
        description = ticket["fields"].get("description", "")
        assignee = ticket["fields"].get("assignee")

        # Assign story points if missing (customfield_10016 is common for story points in Jira)
        story_points = ai_estimate_story_points(summary, description)
        print(f"{key}: Story points = {story_points}")

        # Assign member if not assigned
        if not assignee:
            email = ai_assign_team(description)
            print(f"Assigning {key} to {email}")
            assign_issue(key, email)

        issues_to_add.append(key)

    # Add to sprint
    add_issues_to_sprint(sprint_id, issues_to_add)
    print(f"Added {len(issues_to_add)} issues to sprint '{sprint_name}'")


def assign_issue(issue_key, email):
    # Find accountId from email
    resp = requests.get(f"{JIRA_URL}/rest/api/3/user/search?query={email}", headers=headers, auth=auth)
    resp.raise_for_status()
    users = resp.json()
    if not users:
        print(f"No Jira user found for email {email}")
        return
    account_id = users[0]["accountId"]

    payload = {"accountId": account_id}
    url = f"{JIRA_URL}/rest/api/3/issue/{issue_key}/assignee"
    resp = requests.put(url, headers=headers, auth=auth, json=payload)
    resp.raise_for_status()


if __name__ == "__main__":
    main()
