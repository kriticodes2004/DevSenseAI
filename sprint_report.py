# sprint_report.py
import pandas as pd
from teams import TEAM_MEMBERS, TEAM_SKILLS
from embeddings import embed_text, cosine_sim, extract_text_from_jira_description

# --- Helper to assign team based on ticket summary + description ---
def detect_team(summary: str, description: str) -> str:
    issue_text = f"{summary} {description}".strip()
    issue_emb = embed_text(issue_text)
    best_team, best_score = None, -1
    for team, skills in TEAM_SKILLS.items():
        team_emb = embed_text(skills)
        score = cosine_sim(issue_emb, team_emb)
        if score > best_score:
            best_score = score
            best_team = team
    return best_team if best_score >= 0.3 else "General"

def generate_scrum_sprint_report(tickets_df, sprint_name=None, start_date=None, end_date=None):
    df = tickets_df.copy()

    # --- Normalize sprint ---
    if "sprint" in df.columns:
        df["sprint"] = (
            df["sprint"].astype(str)
            .str.extract(r"([Ss]\d+)", expand=False)
            .str.upper()
        )

    # --- Assign team using summary + description ---
    df["team"] = df.apply(
        lambda row: detect_team(
            row.get("summary", ""), 
            row.get("description", "")
        ),
        axis=1
    )

    # --- Convert created column to datetime ---
    if "created" in df.columns:
        df["created"] = pd.to_datetime(df["created"], errors="coerce")
        if pd.api.types.is_datetime64_any_dtype(df["created"]):
            df["created"] = df["created"].dt.tz_localize(None)

    # --- Debug info ---
    if "created" in df.columns:
        print("📌 Data created range:", df["created"].min(), "→", df["created"].max())
    print("📌 Unique sprints in data:", df["sprint"].dropna().unique())
    print("📌 Unique teams detected:", df["team"].dropna().unique())

    # --- Filtering ---
    if sprint_name:
        df = df[df["sprint"] == sprint_name.upper()]
    if start_date:
        start_dt = pd.to_datetime(str(start_date))
        df = df[df["created"] >= start_dt]
    if end_date:
        end_dt = pd.to_datetime(str(end_date)) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        df = df[df["created"] <= end_dt]

    # --- Metrics ---
    ticket_by_status = df["status"].value_counts().to_dict()
    ticket_by_team = df["team"].value_counts().to_dict()

    total_tickets = len(df)
    closed_tickets = len(df[df["status"].str.lower() == "done"])
    sprint_progress = (closed_tickets / total_tickets * 100) if total_tickets > 0 else 0

    closed_by_person = df[df["status"].str.lower() == "done"].groupby("assignee").size().to_dict()
    most_tickets_closed = dict(sorted(closed_by_person.items(), key=lambda x: x[1], reverse=True))

    load_per_person = df[df["status"].str.lower() != "done"].groupby("assignee").size().to_dict()

    open_tickets_list = df[df["status"].str.lower() != "done"].to_dict(orient="records")
    closed_tickets_list = df[df["status"].str.lower() == "done"].to_dict(orient="records")

    print("📊 ticket_by_status:", ticket_by_status)
    print("📊 ticket_by_team:", ticket_by_team)
    print("📊 sprint_progress:", sprint_progress)

    return {
        "ticket_by_status": ticket_by_status,
        "ticket_by_team": ticket_by_team,
        "sprint_progress": sprint_progress,
        "most_tickets_closed": most_tickets_closed,
        "load_per_person": load_per_person,
        "open_tickets_list": open_tickets_list,
        "closed_tickets_list": closed_tickets_list,
    }
