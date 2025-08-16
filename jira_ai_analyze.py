from dotenv import load_dotenv
import os
import requests
from requests.auth import HTTPBasicAuth
from groq import Groq
from datetime import datetime
from teams import TEAM_MEMBERS   

load_dotenv()
JIRA_URL = os.getenv("JIRA_URL")
PROJECT_KEY = os.getenv("PROJECT_KEY")
EMAIL = os.getenv("EMAIL")
API_TOKEN = os.getenv("API_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


def parse_adf(adf):
    """Parse Jira ADF description into plain text."""
    if isinstance(adf, str):
        return adf
    if not adf or "content" not in adf:
        return ""
    text_parts = []
    for block in adf.get("content", []):
        if block.get("type") == "paragraph":
            para_text = []
            for node in block.get("content", []):
                if node.get("type") == "text":
                    para_text.append(node.get("text", ""))
            text_parts.append(" ".join(para_text))
    return "\n".join(text_parts).strip()


def get_sprint(fields):
    """Extract sprint name like S1, S2 or return None."""
    sprint_field = fields.get("customfield_10020")
    if sprint_field and isinstance(sprint_field, list) and sprint_field:
        sprint_info = sprint_field[0]
        sprint_name = None
        if isinstance(sprint_info, str):
            for part in sprint_info.split(","):
                if part.strip().startswith("name="):
                    sprint_name = part.split("=", 1)[1]
        elif isinstance(sprint_info, dict):
            sprint_name = sprint_info.get("name")
        return sprint_name
    return None


def get_team(assignee_name_or_email: str) -> str:
    """Find team from TEAM_MEMBERS mapping."""
    if not assignee_name_or_email:
        return "Unassigned"
    for team, members in TEAM_MEMBERS.items():
        if assignee_name_or_email in members:
            return team
    return "Other"

def fetch_all_tickets():
    """Fetch ALL Jira tickets using pagination."""
    search_url = f"{JIRA_URL}/rest/api/3/search"
    jql = f"project={PROJECT_KEY} ORDER BY created DESC"
    auth = HTTPBasicAuth(EMAIL, API_TOKEN)
    headers = {"Accept": "application/json"}

    start_at, max_results = 0, 100
    tickets = []

    while True:
        r = requests.get(
            search_url,
            headers=headers,
            auth=auth,
            params={"jql": jql, "startAt": start_at, "maxResults": max_results}
        )
        r.raise_for_status()
        data = r.json()

        total = data.get("total", 0)
        issues = data.get("issues", [])
        print(f"Jira reports total issues: {total}")
        print(f"Fetched this page: {len(issues)} (startAt={start_at})")

        for issue in issues:
            fields = issue["fields"]
            created = datetime.strptime(fields["created"], "%Y-%m-%dT%H:%M:%S.%f%z")

            assignee_name = (
                fields.get("assignee", {}).get("displayName")
                if fields.get("assignee") else "Unassigned"
            )

            tickets.append({
                "key": issue["key"],
                "status": fields["status"]["name"],
                "assignee": assignee_name,
                "team": get_team(assignee_name),
                "sprint": get_sprint(fields),
                "created": created,   
                "summary": fields.get("summary", ""),
                "description": parse_adf(fields.get("description", "")),
            })

        
        if start_at + max_results >= total:
            break
        start_at += max_results

    return tickets


def analyze_ticket(summary, description):
    """Send ticket data to Groq AI for insights."""
    client = Groq(api_key=GROQ_API_KEY)
    prompt = f"""
You are an AI assistant for a scrum master.
Analyze the following JIRA ticket and provide:

1. Concise summary.
2. Possible root causes.
3. Suggested fixes.
4. Suggested skill tags (frontend, backend, devops, general, etc).

Ticket Summary: {summary}
Ticket Description: {description}
    """
    completion = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    return completion.choices[0].message.content.strip()


if __name__ == "__main__":
    tickets = fetch_all_tickets()
    print(f"\n✅ Found {len(tickets)} issues from project {PROJECT_KEY}\n")

    for t in tickets:
        print(f"--- {t['key']} ---")
        print(f"Status: {t['status']}")
        print(f"Assigned to: {t['assignee']} (Team: {t['team']})")
        print(f"Sprint: {t['sprint']}")
        print(f"Created: {t['created'].strftime('%d %b %Y %H:%M')}")
        print(f"Summary: {t['summary']}")
        print(f"Description: {t['description']}\n")

        ai_out = analyze_ticket(t["summary"], t["description"])
        print("Analysis:")
        print(ai_out)
        print("\n" + "-"*60 + "\n")
