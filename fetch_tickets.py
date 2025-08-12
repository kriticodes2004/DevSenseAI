import os
import json
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv


load_dotenv()

JIRA_URL = os.getenv("JIRA_URL")
EMAIL = os.getenv("EMAIL")
API_TOKEN = os.getenv("API_TOKEN")
PROJECT_KEY = os.getenv("PROJECT_KEY")
OUTFILE = "backlog_issues.json"

if not all([JIRA_URL, EMAIL, API_TOKEN, PROJECT_KEY]):
    raise ValueError("Missing one or more required environment variables in .env")

# ----------------------
# Helpers
# ----------------------
auth = HTTPBasicAuth(EMAIL, API_TOKEN)
headers = {"Accept": "application/json"}

def fetch_issues_by_jql(jql, max_per_page=50):
    start_at = 0
    total = None
    issues = []
    while True:
        params = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": max_per_page,
            "fields": "summary,description,issuetype,priority,status,assignee,created,updated,labels"
        }
        resp = requests.get(f"{JIRA_URL}/rest/api/3/search", headers=headers, params=params, auth=auth)
        resp.raise_for_status()
        data = resp.json()
        if total is None:
            total = data.get("total", 0)
            print(f"Total matching issues: {total}")
        batch = data.get("issues", [])
        issues.extend(batch)
        start_at += len(batch)
        if start_at >= total:
            break
    return issues

def simplify_issue(issue):
    fields = issue.get("fields", {})
    assignee = fields.get("assignee")
    assignee_info = None
    if assignee:
        assignee_info = {
            "displayName": assignee.get("displayName"),
            "accountId": assignee.get("accountId"),
            "email": assignee.get("emailAddress", None)
        }
    return {
        "key": issue.get("key"),
        "id": issue.get("id"),
        "summary": fields.get("summary"),
        "description": fields.get("description"),
        "issue_type": fields.get("issuetype", {}).get("name"),
        "priority": fields.get("priority", {}).get("name") if fields.get("priority") else None,
        "status": fields.get("status", {}).get("name") if fields.get("status") else None,
        "assignee": assignee_info,
        "labels": fields.get("labels", []),
        "created": fields.get("created"),
        "updated": fields.get("updated")
    }

# ----------------------
# Main
# ----------------------
def main():
    jql = f'project = "{PROJECT_KEY}" AND sprint is EMPTY ORDER BY created DESC'
    print("Running JQL:", jql)

    issues = fetch_issues_by_jql(jql)
    simplified = [simplify_issue(i) for i in issues]

    print(f"Fetched {len(simplified)} backlog issues.")
    for s in simplified:
        print(f"{s['key']} | {s['issue_type']} | {s['status']} | {s['summary']}")

    with open(OUTFILE, "w", encoding="utf-8") as f:
        json.dump(simplified, f, ensure_ascii=False, indent=2)
    print(f"Wrote backlog to {OUTFILE}")

if __name__ == "__main__":
    main()
