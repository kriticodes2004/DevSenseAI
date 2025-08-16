import os
from collections import defaultdict
from jira import JIRA
from dotenv import load_dotenv
from teams import TEAM_MEMBERS, TEAM_SKILLS
from embeddings import embed_text, cosine_sim, extract_text_from_jira_description

load_dotenv()
JIRA_URL = os.getenv("JIRA_URL")
EMAIL = os.getenv("EMAIL")
API_TOKEN = os.getenv("API_TOKEN")
PROJECT_KEY = os.getenv("PROJECT_KEY")

jira = JIRA(server=JIRA_URL, basic_auth=(EMAIL, API_TOKEN))

def get_team_for_issue(issue):
   
    summary = issue.fields.summary or ""
    description = ""

    if issue.fields.description:
        if isinstance(issue.fields.description, dict):
            description = extract_text_from_jira_description(issue.fields.description)
        else:
            description = issue.fields.description

    issue_text = summary + " " + description
    issue_emb = embed_text(issue_text)

    best_team = None
    best_score = -1
    for team, skills in TEAM_SKILLS.items():
        team_emb = embed_text(skills)
        score = cosine_sim(issue_emb, team_emb)
        if score > best_score:
            best_score = score
            best_team = team

    if best_score < 0.3:
        return "General"

    return best_team


def rebalance_sprint(sprint_id):
   

    jql = f'project = "{PROJECT_KEY}" AND sprint = {sprint_id}'
    issues = jira.search_issues(jql, maxResults=False)

    print(f"Found {len(issues)} issues in sprint {sprint_id}")

   
    team_issues = defaultdict(list)
    for issue in issues:
        team = get_team_for_issue(issue)
        team_issues[team].append(issue)

    for team, team_issues_list in team_issues.items():
        members = TEAM_MEMBERS.get(team, TEAM_MEMBERS["General"])
        if not members:
            continue

        assignments = {}
        for i, issue in enumerate(team_issues_list):
            member = members[i % len(members)]
            jira.assign_issue(issue.key, member)
            assignments[issue.key] = member

        print(f"\nRebalanced team '{team}':")
        for key, member in assignments.items():
            print(f"  - {key} → {member}")

    print("\nSprint rebalancing complete ")


if __name__ == "__main__":
    sprint_id = input("Enter Sprint ID to rebalance: ").strip()
    rebalance_sprint(sprint_id)
