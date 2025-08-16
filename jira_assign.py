import os
from collections import defaultdict
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
import requests
from teams import TEAM_SKILLS, TEAM_MEMBERS
from embeddings import embed_text, cosine_sim, extract_text_from_jira_description  # You must have these ready

# Load environment variables
load_dotenv()
JIRA_URL = os.getenv("JIRA_URL").rstrip("/")
PROJECT_KEY = os.getenv("PROJECT_KEY")
EMAIL = os.getenv("EMAIL")
API_TOKEN = os.getenv("API_TOKEN")

auth = HTTPBasicAuth(EMAIL, API_TOKEN)
headers = {"Accept": "application/json", "Content-Type": "application/json"}

class JiraAutoAssigner:
    def __init__(self):
        self.team_embeddings = {team: embed_text(skills) for team, skills in TEAM_SKILLS.items()}
        self.assignments = {}  # issue_key -> assigned member email
        self.member_load = defaultdict(int)  # email -> count

    def get_issues(self, jql):
        url = f"{JIRA_URL}/rest/api/3/search"
        params = {"jql": jql, "maxResults": 100}
        r = requests.get(url, headers=headers, params=params, auth=auth)
        r.raise_for_status()
        return r.json().get("issues", [])

    def count_current_load(self):
        """Count open issues per member to ensure fair distribution"""
        load_count = defaultdict(int)
        jql = f'project = "{PROJECT_KEY}" AND statusCategory != Done'
        issues = self.get_issues(jql)
        for issue in issues:
            assignee = issue["fields"].get("assignee")
            if assignee and assignee.get("emailAddress"):
                load_count[assignee["emailAddress"]] += 1
        self.member_load = load_count

    def detect_team(self, summary, description):
        issue_text = f"{summary} {description}".strip()
        issue_emb = embed_text(issue_text)
        best_team, best_score = None, -1
        for team, emb in self.team_embeddings.items():
            score = cosine_sim(issue_emb, emb)
            if score > best_score:
                best_score = score
                best_team = team
        return best_team if best_score >= 0.3 else "General"

    def assign_issue(self, issue):
        fields = issue.get("fields", {})
        if fields.get("assignee"):  # Skip if already assigned
            return None

        summary = fields.get("summary") or ""
        description_field = fields.get("description")
        description = (
            extract_text_from_jira_description(description_field)
            if isinstance(description_field, dict)
            else description_field or ""
        )

        team = self.detect_team(summary, description)
        members = TEAM_MEMBERS.get(team, TEAM_MEMBERS["General"])
        if not members:
            print(f"⚠ No members for team {team} — skipping {issue['key']}")
            return None

        # Pick least loaded member
        chosen_member = min(members, key=lambda m: self.member_load.get(m, 0))
        self.assignments[issue["key"]] = chosen_member
        self.member_load[chosen_member] += 1
        print(f"✅ {issue['key']}: Assigned to '{chosen_member}' (Team: {team})")

    def get_account_id(self, email):
        url = f"{JIRA_URL}/rest/api/3/user/search"
        params = {"query": email}
        r = requests.get(url, headers=headers, params=params, auth=auth)
        r.raise_for_status()
        users = r.json()
        if not users:
            raise ValueError(f"No account found for email: {email}")
        return users[0]["accountId"]

    def update_jira_assignment(self, issue_key, email):
        url = f"{JIRA_URL}/rest/api/3/issue/{issue_key}/assignee"
        payload = {"accountId": self.get_account_id(email)}
        r = requests.put(url, json=payload, headers=headers, auth=auth)
        if r.status_code == 204:
            print(f"   ↳ Jira updated for {issue_key}")
        else:
            print(f"❌ Failed to update {issue_key}: {r.text}")

    def run(self):
        print("🔍 Fetching unassigned issues...")
        jql = f'project = "{PROJECT_KEY}" AND assignee IS EMPTY AND statusCategory != Done'
        unassigned = self.get_issues(jql)
        if not unassigned:
            print("🎉 No unassigned issues found.")
            return

        self.count_current_load()
        print(f"Found {len(unassigned)} unassigned issues. Assigning...")

        for issue in unassigned:
            self.assign_issue(issue)

        print("\n📤 Updating Jira with assignments...")
        for key, email in self.assignments.items():
            self.update_jira_assignment(key, email)

        print("\n✅ Assignment complete.")

if __name__ == "__main__":
    JiraAutoAssigner().run()
