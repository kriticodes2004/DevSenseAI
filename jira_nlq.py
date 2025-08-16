import os
import re
import math
from datetime import datetime, timedelta, timezone
from collections import defaultdict, Counter

import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

# Your skill/team data + text utils
from teams import TEAM_SKILLS, TEAM_MEMBERS
from embeddings import embed_text, cosine_sim, extract_text_from_jira_description

# ============== Env & Jira setup ==============
load_dotenv()
JIRA_URL = os.getenv("JIRA_URL", "").rstrip("/")
PROJECT_KEY = os.getenv("PROJECT_KEY")
EMAIL = os.getenv("EMAIL")
API_TOKEN = os.getenv("API_TOKEN")

if not all([JIRA_URL, PROJECT_KEY, EMAIL, API_TOKEN]):
    raise SystemExit("❌ Missing env vars. Ensure JIRA_URL, PROJECT_KEY, EMAIL, API_TOKEN are in your .env")

AUTH = HTTPBasicAuth(EMAIL, API_TOKEN)
HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}

# ============== Helpers ==============

def parse_adf_to_text(adf):
    if not adf:
        return ""
    if isinstance(adf, str):
        return adf
    out = []
    for block in adf.get("content", []):
        t = block.get("type")
        if t == "paragraph":
            segs = [node.get("text", "") for node in block.get("content", []) or [] if node.get("type") == "text"]
            if segs: out.append(" ".join(segs))
        elif t in ("bulletList", "orderedList"):
            for li in block.get("content", []) or []:
                for inner in li.get("content", []) or []:
                    line = [node.get("text", "") for node in inner.get("content", []) or [] if node.get("type") == "text"]
                    if line: out.append("- " + " ".join(line))
        elif t == "codeBlock":
            code_txt = [node.get("text", "") for node in block.get("content", []) or [] if node.get("type") == "text"]
            if code_txt: out.append("```" + "\n".join(code_txt) + "```")
    return "\n".join(x for x in out if x).strip()

def parse_sprint_field(fields):
    sf = fields.get("customfield_10020")
    if not sf or not isinstance(sf, list) or not sf: return (None, None)
    spr = sf[0]
    name, state = None, None
    if isinstance(spr, dict):
        name = spr.get("name")
        state = spr.get("state")
    elif isinstance(spr, str):
        for part in spr.split(","):
            p = part.strip()
            if p.startswith("name="): name = p.split("=",1)[1]
            elif p.startswith("state="): state = p.split("=",1)[1]
    return (name, state)

def parse_dt(s):
    if not s: return None
    try:
        if s.endswith("Z"): return datetime.fromisoformat(s.replace("Z", "+00:00"))
        if re.search(r"[+-]\d{4}$", s): s = s[:-5] + s[-5:-2] + ":" + s[-2:]
        return datetime.fromisoformat(s)
    except Exception: return None

# ============== Fetch & Normalize ==============

def fetch_all_issues(jql, max_results=1000):
    url = f"{JIRA_URL}/rest/api/3/search"
    start_at = 0
    issues = []
    while start_at < max_results:
        r = requests.get(
            url, headers=HEADERS, auth=AUTH,
            params={"jql": jql, "maxResults": min(100, max_results-start_at), "startAt": start_at}
        )
        r.raise_for_status()
        data = r.json()
        batch = data.get("issues", [])
        issues.extend(batch)
        if start_at + len(batch) >= data.get("total", 0) or not batch: break
        start_at += len(batch)
    return issues

def build_team_embeddings():
    return {team: embed_text(sk) for team, sk in TEAM_SKILLS.items()}

def detect_team(summary, description, team_embeds):
    text = f"{summary or ''}\n{description or ''}".strip()
    if not text: return "General"
    emb = embed_text(text)
    best_team, best_score = "General", -1.0
    for team, t_emb in team_embeds.items():
        score = cosine_sim(emb, t_emb)
        if score > best_score: best_team, best_score = team, score
    return best_team if best_score >= 0.30 else "General"

def normalize_issue(issue, team_embeds):
    fields = issue.get("fields", {})
    key = issue.get("key")
    status_name = (fields.get("status") or {}).get("name")
    status_cat = ((fields.get("status") or {}).get("statusCategory") or {}).get("name")
    assignee = fields.get("assignee") or {}
    assignee_name = assignee.get("displayName")
    assignee_email = assignee.get("emailAddress")
    summary = fields.get("summary") or ""
    description = fields.get("description")
    desc_txt = parse_adf_to_text(description) if isinstance(description, dict) else (description or "")
    created = parse_dt(fields.get("created"))
    updated = parse_dt(fields.get("updated"))
    resolved = parse_dt(fields.get("resolutiondate"))
    sprint_name, sprint_state = parse_sprint_field(fields)
    priority = (fields.get("priority") or {}).get("name")
    duedate = parse_dt(fields.get("duedate"))
    team = detect_team(summary, desc_txt, team_embeds)
    return {
        "key": key,
        "summary": summary,
        "description": desc_txt,
        "status": status_name,
        "statusCategory": status_cat,
        "assigneeName": assignee_name,
        "assigneeEmail": assignee_email,
        "created": created,
        "updated": updated,
        "resolved": resolved,
        "priority": priority,
        "due": duedate,
        "sprint": sprint_name,
        "sprintState": sprint_state,
        "team": team,
    }

def load_dataset():
    jql = f'project = "{PROJECT_KEY}" ORDER BY created DESC'
    raw = fetch_all_issues(jql, max_results=1000)
    team_embeds = build_team_embeddings()
    return [normalize_issue(it, team_embeds) for it in raw]

# ============== Aggregations ==============

def count_by(predicate, data): return sum(1 for r in data if predicate(r))
def group_by(keyfn, data):
    buckets = defaultdict(list)
    for r in data: buckets[keyfn(r)].append(r)
    return buckets
def pct(n, d): return 0.0 if d==0 else round((n/d)*100,1)
def days_ago(n): return datetime.now(timezone.utc) - timedelta(days=n)

# ============== Answer Functions ==============
def ans_how_many_backlog(data):
    # Backlog heuristics: statusCategory To Do and no sprint
    n = count_by(lambda r: (r["statusCategory"] == "To Do") and (r["sprint"] is None), data)
    return f"{n} ticket(s) are in the backlog."

def ans_how_many_in_sprint(data, sprint_name):
    n = count_by(lambda r: (r["sprint"] or "").lower() == sprint_name.lower(), data)
    return f"{n} ticket(s) are in sprint '{sprint_name}'."

def ans_how_many_assigned_to_person(data, person):
    n = count_by(lambda r: (r["assigneeName"] and r["assigneeName"].lower() == person.lower()) or
                           (r["assigneeEmail"] and r["assigneeEmail"].lower() == person.lower()), data)
    return f"{n} ticket(s) are assigned to {person}."

def ans_how_many_unassigned(data):
    n = count_by(lambda r: not r["assigneeEmail"], data)
    return f"{n} ticket(s) are unassigned."

def ans_percent_closed(data):
    total = len(data)
    closed = count_by(lambda r: r["statusCategory"] == "Done", data)
    return f"{pct(closed, total)}% of tickets are closed ({closed}/{total})."

def ans_closed_last_period(data, days):
    since = days_ago(days)
    n = count_by(lambda r: r["resolved"] and r["resolved"] >= since, data)
    label = "week" if days == 7 else f"{days} days"
    return f"{n} ticket(s) closed in the last {label}."

def ans_in_progress_count(data):
    n = count_by(lambda r: r["statusCategory"] == "In Progress", data)
    return f"{n} ticket(s) are currently in progress."

def ans_list_active(data):
    active = [r for r in data if r["statusCategory"] in ("To Do", "In Progress")]
    if not active:
        return "No active tickets."
    lines = [f"- {r['key']}: {r['summary']}  • {r['status']}  • {r.get('assigneeName') or 'Unassigned'}" for r in active[:50]]
    more = "" if len(active) <= 50 else f"\n(and {len(active)-50} more...)"
    return "Active tickets:\n" + "\n".join(lines) + more

def ans_list_by_status(data):
    buckets = group_by(lambda r: r["status"] or "Unknown", data)
    lines = []
    for st in sorted(buckets.keys()):
        lines.append(f"{st}: {len(buckets[st])}")
    return "Tickets by status:\n" + "\n".join(lines)

def ans_list_closed(data):
    closed = [r for r in data if r["statusCategory"] == "Done"]
    count = len(closed)
    if not closed:
        return "No closed tickets found."
    lines = [f"Found {count} closed ticket(s):"]
    for r in closed[:50]:
        resolved_date = r.get('resolved')
        resolved_str = resolved_date.strftime('%d %b %Y') if resolved_date else 'N/A'
        lines.append(f"- {r['key']}: {r['summary']}  • Resolved: {resolved_str}")
    more = "" if count <= 50 else f"\n(and {count-50} more...)"
    return "\n".join(lines) + more

def ans_team_most_tickets(data):
    buckets = group_by(lambda r: r["team"], data)
    if not buckets:
        return "No tickets found."
    best = max(buckets.items(), key=lambda kv: len(kv[1]))
    return f"Team with the most tickets: {best[0]} ({len(best[1])})."

def ans_team_least_tickets(data):
    buckets = group_by(lambda r: r["team"], data)
    if not buckets:
        return "No tickets found."
    best = min(buckets.items(), key=lambda kv: len(kv[1]))
    return f"Team with the least tickets: {best[0]} ({len(best[1])})."

def ans_team_percent_closed(data, team):
    subset = [r for r in data if (r["team"] or "").lower() == team.lower()]
    if not subset:
        return f"No tickets for team '{team}'."
    closed = count_by(lambda r: r["statusCategory"] == "Done", subset)
    return f"{pct(closed, len(subset))}% of {team} tickets are closed ({closed}/{len(subset)})."

def ans_backlog_for_team(data, team):
    subset = [r for r in data if (r["team"] or "").lower() == team.lower() and r["statusCategory"] == "To Do" and r["sprint"] is None]
    if not subset:
        return f"No backlog tickets for team '{team}'."
    lines = [f"- {r['key']}: {r['summary']}" for r in subset[:50]]
    more = "" if len(subset) <= 50 else f"\n(and {len(subset)-50} more...)"
    return f"Backlog tickets for {team}:\n" + "\n".join(lines) + more

def ans_member_efficiency(data, team, days=30):
    since = days_ago(days)
    subset = [r for r in data if (r["team"] or "").lower() == team.lower()]
    if not subset:
        return f"No tickets for team '{team}'."
    # efficiency: closed in window / assigned in window (or total assigned if none)
    per_member = defaultdict(lambda: {"assigned": 0, "closed": 0})
    for r in subset:
        m = r["assigneeEmail"] or r["assigneeName"]
        if not m:
            continue
        if r["created"] and r["created"] >= since:
            per_member[m]["assigned"] += 1
        # Consider closed in window if resolved in window
        if r["resolved"] and r["resolved"] >= since:
            per_member[m]["closed"] += 1
    if not per_member:
        return f"No assignees found for team '{team}'."
    scores = []
    for m, v in per_member.items():
        denom = v["assigned"] if v["assigned"] > 0 else 1
        eff = v["closed"] / denom
        scores.append((m, eff, v["closed"], v["assigned"]))
    scores.sort(key=lambda x: x[1], reverse=True)
    best = scores[0]
    return f"Most efficient member in {team}: {best[0]} (closed {best[2]} / assigned {best[3]} last {days} days, efficiency {best[1]:.2f})."

def ans_member_least_active(data, team, days=30):
    since = days_ago(days)
    subset = [r for r in data if (r["team"] or "").lower() == team.lower()]
    per_member_closed = Counter()
    for r in subset:
        m = r["assigneeEmail"] or r["assigneeName"]
        if not m:
            continue
        if r["resolved"] and r["resolved"] >= since:
            per_member_closed[m] += 1
    if not per_member_closed:
        return f"No resolved tickets for team '{team}' in last {days} days."
    least = min(per_member_closed.items(), key=lambda kv: kv[1])
    return f"Least active member in {team}: {least[0]} ({least[1]} ticket(s) closed in last {days} days)."

def ans_member_with_most_open(data):
    per_member_open = Counter()
    for r in data:
        if r["statusCategory"] != "Done":
            m = r["assigneeEmail"] or r["assigneeName"]
            if m:
                per_member_open[m] += 1
    if not per_member_open:
        return "No open tickets per member."
    who = max(per_member_open.items(), key=lambda kv: kv[1])
    return f"Member with most unclosed tickets: {who[0]} ({who[1]})."

def ans_closed_last_month_top_member(data):
    now = datetime.now(timezone.utc)
    first_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month_end = first_of_this_month - timedelta(seconds=1)
    last_month_start = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    per_member = Counter()
    for r in data:
        if r["resolved"] and last_month_start <= r["resolved"] <= last_month_end:
            m = r["assigneeEmail"] or r["assigneeName"]
            if m:
                per_member[m] += 1
    if not per_member:
        return "No tickets were closed last month."
    top = max(per_member.items(), key=lambda kv: kv[1])
    return f"{top[0]} closed the most tickets last month ({top[1]})."

def ans_best_suited_for_ticket(data, key):
    # Find the issue and pick the team, then recommend least-loaded member of that team
    issue = next((r for r in data if r["key"].lower() == key.lower()), None)
    if not issue:
        return f"Ticket {key} not found."
    team = issue["team"] or "General"
    members = TEAM_MEMBERS.get(team, TEAM_MEMBERS.get("General", []))
    if not members:
        return f"No members found for team {team}."
    # compute current load across project
    per_member_open = Counter()
    for r in data:
        if r["statusCategory"] != "Done":
            m = r["assigneeEmail"] or r["assigneeName"]
            if m:
                per_member_open[m] += 1
    # Choose least loaded among team
    ranked = sorted(members, key=lambda m: per_member_open.get(m, 0))
    choice = ranked[0]
    return f"Best suited for {key}: {choice} (team {team}, current open load {per_member_open.get(choice,0)})."

def ans_created_in_period(data, days):
    since = days_ago(days)
    n = count_by(lambda r: r["created"] and r["created"] >= since, data)
    label = "week" if days == 7 else f"{days} days"
    return f"{n} ticket(s) were created in the last {label}."

def ans_resolved_in_period(data, days):
    since = days_ago(days)
    n = count_by(lambda r: r["resolved"] and r["resolved"] >= since, data)
    label = "week" if days == 7 else f"{days} days"
    return f"{n} ticket(s) were resolved in the last {label}."

def ans_stale_in_status(data, status_name, days):
    since = days_ago(days)
    stale = [r for r in data if (r["status"] or "").lower() == status_name.lower() and (r["updated"] and r["updated"] < since)]
    if not stale:
        return f"No tickets in '{status_name}' for more than {days} days."
    lines = [f"- {r['key']}: {r['summary']}" for r in stale[:50]]
    more = "" if len(stale) <= 50 else f"\n(and {len(stale)-50} more...)"
    return f"Tickets in '{status_name}' for more than {days} days:\n" + "\n".join(lines) + more

def ans_changed_last_24h(data):
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    changed = [r for r in data if r["updated"] and r["updated"] >= since]
    if not changed:
        return "No tickets changed status in the last 24 hours."
    lines = [f"- {r['key']}: {r['summary']}  • updated {r['updated'].astimezone().strftime('%d %b %Y %H:%M')}" for r in changed[:50]]
    more = "" if len(changed) <= 50 else f"\n(and {len(changed)-50} more...)"
    return "Recently changed (24h):\n" + "\n".join(lines) + more

def ans_idle_gt_days(data, days):
    since = days_ago(days)
    idle = [r for r in data if (r["updated"] and r["updated"] < since) and r["statusCategory"] != "Done"]
    if not idle:
        return f"No tickets idle for more than {days} days."
    lines = [f"- {r['key']}: {r['summary']}" for r in idle[:50]]
    more = "" if len(idle) <= 50 else f"\n(and {len(idle)-50} more...)"
    return f"Tickets idle for more than {days} days:\n" + "\n".join(lines) + more

def ans_sprint_unassigned(data, sprint_name):
    n = count_by(lambda r: (r["sprint"] or "").lower() == sprint_name.lower() and not r["assigneeEmail"], data)
    return f"{n} unassigned ticket(s) in sprint '{sprint_name}'."

def ans_sprint_overloaded_members(data, sprint_name):
    # overloaded: > ceil(avg tickets per member) in that sprint
    in_sprint = [r for r in data if (r["sprint"] or "").lower() == sprint_name.lower() and r["statusCategory"] != "Done"]
    per_member = Counter(r["assigneeEmail"] or r["assigneeName"] for r in in_sprint if (r["assigneeEmail"] or r["assigneeName"]))
    if not per_member:
        return f"No assigned, open tickets in sprint '{sprint_name}'."
    avg = math.ceil(sum(per_member.values()) / max(1, len(per_member)))
    overloaded = [(m, c) for m, c in per_member.items() if c > avg]
    if not overloaded:
        return f"No overloaded members detected in sprint '{sprint_name}'."
    overloaded.sort(key=lambda x: x[1], reverse=True)
    lines = [f"- {m}: {c} open in sprint (avg threshold {avg})" for m, c in overloaded]
    return f"Overloaded members in sprint '{sprint_name}':\n" + "\n".join(lines)

def ans_sprint_team_with_most(data, sprint_name):
    in_sprint = [r for r in data if (r["sprint"] or "").lower() == sprint_name.lower()]
    if not in_sprint:
        return f"No tickets in sprint '{sprint_name}'."
    grp = group_by(lambda r: r["team"], in_sprint)
    best = max(grp.items(), key=lambda kv: len(kv[1]))
    return f"In sprint '{sprint_name}', {best[0]} has the most tickets ({len(best[1])})."

def ans_sprint_closure_rate(data, sprint_name):
    in_sprint = [r for r in data if (r["sprint"] or "").lower() == sprint_name.lower()]
    if not in_sprint:
        return f"No tickets in sprint '{sprint_name}'."
    done = sum(1 for r in in_sprint if r["statusCategory"] == "Done")
    return f"Sprint '{sprint_name}' closure rate: {pct(done, len(in_sprint))}% ({done}/{len(in_sprint)})."

def ans_backlog_size_by_team(data):
    backlog = [r for r in data if r["statusCategory"] == "To Do" and r["sprint"] is None]
    if not backlog:
        return "Backlog is empty."
    grp = group_by(lambda r: r["team"], backlog)
    lines = [f"- {team}: {len(rows)}" for team, rows in sorted(grp.items(), key=lambda kv: kv[0])]
    return "Backlog size by team:\n" + "\n".join(lines)

def ans_backlog_growth_last_month(data):
    # growth = created last 30d minus resolved last 30d (approx backlog delta)
    created = count_by(lambda r: r["created"] and r["created"] >= days_ago(30), data)
    resolved = count_by(lambda r: r["resolved"] and r["resolved"] >= days_ago(30), data)
    delta = created - resolved
    trend = "grew" if delta > 0 else ("shrunk" if delta < 0 else "stayed flat")
    return f"Backlog {trend} by {abs(delta)} in the last 30 days (created {created}, resolved {resolved})."

def ans_backlog_older_than(data, days):
    cutoff = days_ago(days)
    oldies = [r for r in data if r["statusCategory"] == "To Do" and (r["sprint"] is None) and r["created"] and r["created"] < cutoff]
    if not oldies:
        return f"No backlog tickets older than {days} days."
    lines = [f"- {r['key']}: {r['summary']}" for r in oldies[:50]]
    more = "" if len(oldies) <= 50 else f"\n(and {len(oldies)-50} more...)"
    return f"Backlog tickets older than {days} days:\n" + "\n".join(lines) + more

# ============== Intent Router ==============

INTENT_PATTERNS = [
    (re.compile(r"how many tickets.* in backlog|backlog.* size|how many.* backlog tickets", re.I), lambda m, d: ans_how_many_backlog(d)),
    (re.compile(r"how many tickets.* in sprint ([\w\s-]+)", re.I), lambda m, d: ans_how_many_in_sprint(d, m.group(1).strip())),
    (re.compile(r"(?:how many tickets.* assigned to|tickets for) (.+)", re.I), lambda m, d: ans_how_many_assigned_to_person(d, m.group(1).strip())),
    (re.compile(r"how many.* unassigned tickets|number of unassigned tickets|unassigned ticket count", re.I), lambda m, d: ans_how_many_unassigned(d)),
    (re.compile(r"what percentage.* closed|closed tickets percentage|percent.* closed tickets", re.I), lambda m, d: ans_percent_closed(d)),
    (re.compile(r"how many.* closed.* last week|closed tickets.* last week", re.I), lambda m, d: ans_closed_last_period(d, 7)),
    (re.compile(r"how many.* closed.* last (\d+)\s*days|closed tickets.* last (\d+)\s*days", re.I), lambda m, d: ans_closed_last_period(d, int(m.group(1)))),
    (re.compile(r"how many tickets.* in progress|in progress ticket count|number of.* in progress", re.I), lambda m, d: ans_in_progress_count(d)),
    (re.compile(r"list.* active tickets|show.* active tickets", re.I), lambda m, d: ans_list_active(d)),
    (re.compile(r"list tickets by status|ticket count by status|tickets by status", re.I), lambda m, d: ans_list_by_status(d)),
    (re.compile(r"list.* closed tickets|show.* closed tickets", re.I), lambda m, d: ans_list_closed(d)),

    (re.compile(r"which team has the most tickets|team with most tickets", re.I), lambda m, d: ans_team_most_tickets(d)),
    (re.compile(r"which team has the least tickets|team with least tickets", re.I), lambda m, d: ans_team_least_tickets(d)),
    (re.compile(r"what percentage of tickets for (.+) are closed", re.I), lambda m, d: ans_team_percent_closed(d, m.group(1).strip())),
    (re.compile(r"show.* backlog tickets for (.+)|backlog for (.+)", re.I), lambda m, d: ans_backlog_for_team(d, m.group(1) or m.group(2))),

    (re.compile(r"who is the most efficient member of (.+)|most efficient in (.+)", re.I), lambda m, d: ans_member_efficiency(d, m.group(1) or m.group(2))),
    (re.compile(r"who is the least active member of (.+)|least active in (.+)", re.I), lambda m, d: ans_member_least_active(d, m.group(1) or m.group(2))),
    (re.compile(r"which member has the most unclosed tickets|most open tickets by member", re.I), lambda m, d: ans_member_with_most_open(d)),
    (re.compile(r"who closed the most tickets last month", re.I), lambda m, d: ans_closed_last_month_top_member(d)),

    (re.compile(r"who is best suited for ticket ([A-Z]+-\d+)|best person for ([A-Z]+-\d+)", re.I), lambda m, d: ans_best_suited_for_ticket(d, m.group(1) or m.group(2))),

    (re.compile(r"how many tickets.* created.* last week", re.I), lambda m, d: ans_created_in_period(d, 7)),
    (re.compile(r"how many tickets.* resolved.* last week", re.I), lambda m, d: ans_resolved_in_period(d, 7)),
    (re.compile(r"list tickets in (?:to do|todo) for more than (\d+)\s*days", re.I), lambda m, d: ans_stale_in_status(d, "To Do", int(m.group(1)))),
    (re.compile(r"list tickets in progress for more than (\d+)\s*days", re.I), lambda m, d: ans_stale_in_status(d, "In Progress", int(m.group(1)))),
    (re.compile(r"which tickets changed.* last 24 hours", re.I), lambda m, d: ans_changed_last_24h(d)),
    (re.compile(r"which tickets.* idle for more than (\d+)\s*days", re.I), lambda m, d: ans_idle_gt_days(d, int(m.group(1)))),

    (re.compile(r"how many.* unassigned.* in sprint ([\w\s-]+)", re.I), lambda m, d: ans_sprint_unassigned(d, m.group(1).strip())),
    (re.compile(r"which members in sprint ([\w\s-]+) are overloaded|overloaded members in sprint ([\w\s-]+)", re.I), lambda m, d: ans_sprint_overloaded_members(d, m.group(1) or m.group(2))),
    (re.compile(r"which team in sprint ([\w\s-]+) is handling the most tickets|team with most tickets in sprint ([\w\s-]+)", re.I), lambda m, d: ans_sprint_team_with_most(d, m.group(1) or m.group(2))),
    (re.compile(r"closure rate for sprint ([\w\s-]+)", re.I), lambda m, d: ans_sprint_closure_rate(d, m.group(1).strip())),

    (re.compile(r"backlog size by team", re.I), lambda m, d: ans_backlog_size_by_team(d)),
    (re.compile(r"backlog growth.* last month", re.I), lambda m, d: ans_backlog_growth_last_month(d)),
    (re.compile(r"backlog tickets older than (\d+)\s*days", re.I), lambda m, d: ans_backlog_older_than(d, int(m.group(1)))),
]


HELP_TEXT = """
Examples you can ask:
- How many tickets are in backlog?
- How many tickets are in sprint s1?
- How many tickets are assigned to kriti khurana?
- How many tickets are unassigned?
- What percentage of tickets are closed?
- How many tickets have been closed in the last week?
- How many tickets are in progress?
- List all active tickets
- List tickets by status
- List all closed tickets

Team insights:
- Which team has the most tickets?
- Which team has the least tickets?
- What percentage of tickets for Backend are closed?
- Show me backlog tickets for QA

Member insights:
- Who is the most efficient member of Backend?
- Who is the least active member of DevOps?
- Which member has the most unclosed tickets?
- Who closed the most tickets last month?

Recommendations:
- Who is best suited for ticket SCRUM-41?

Time-based:
- How many tickets were created in the last week?
- How many tickets were resolved in the last week?
- List tickets in To Do for more than 14 days
- Which tickets changed status in the last 24 hours?
- Which tickets have been idle for more than 7 days?

Sprint:
- How many tickets in sprint s1 are unassigned?
- Which members in sprint s1 are overloaded?
- Which team in sprint s1 is handling the most tickets?
- Closure rate for sprint s1

Backlog health:
- Backlog size by team
- Backlog growth in the last month
- Backlog tickets older than 30 days

Type 'refresh' to reload data, 'help' to see this list, or 'exit' to quit.
"""


def answer_query(q, data):
    """
    Finds a matching intent pattern for the user's query and returns the answer.
    """
    q = q.strip()
    for pattern, fn in INTENT_PATTERNS:
        match = pattern.search(q)
        if match:
            try:
                # Pass the match object to the handler function
                return fn(match, data)
            except Exception as e:
                return f"⚠️ Error answering that: {e}"
    
    # Fallback response if no pattern matches
    return "Sorry, that query is not in the question bank. Type 'help' to see what I can answer."


def main():
    print("🔄 Loading Jira data...")
    data = load_dataset()
    print(f"✅ Loaded {len(data)} issue(s) from project {PROJECT_KEY}. Type 'help' for examples.\n")
    while True:
        try: q = input("nlq> ").strip()
        except (EOFError, KeyboardInterrupt): print("\n👋 Bye!"); break
        if not q: continue
        if q.lower() in ("exit", "quit", ":q"): print("👋 Bye!"); break
        if q.lower() == "help": print(HELP_TEXT); continue
        if q.lower() == "refresh": print("🔄 Refreshing..."); data = load_dataset(); print(f"✅ Reloaded {len(data)} issue(s).\n"); continue
        print(answer_query(q, data), "\n")

if __name__ == "__main__":
    main()