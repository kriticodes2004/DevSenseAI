# 🚀 DevSense - Jira Intelligence Suite (Streamlit UI)

**DevSense** is your AI-powered cockpit for Scrum Masters. It simplifies Jira workflow management, provides live insights, and automates ticket assignment and sprint balancing. Built with **Streamlit**, it combines analytics, reporting, and AI-powered insights in a single dashboard.

---

## 🌟 Use Case

DevSense empowers Scrum Masters and agile teams to:

- **Automatically assign tasks** based on team workload and skills.  
- **Rebalance sprints mid-way** to distribute work evenly.  
- **Monitor live sprint progress**, ticket status, and backlog.  
- **Generate AI-powered ticket analysis** and scrum reports.  
- **Query Jira naturally** using plain English, e.g., `"How many tickets are in sprint s1?"`
- - **create tickets manually** in the dashboard itself and push to a new or existing sprint.  

It acts as a **central hub for sprint management**, combining task assignment, analytics, and reporting in one intelligent dashboard.

---

## 🚀 Features

### 🧑‍💼 Smart Task Management

- **Auto Assign** — Allocate unassigned tickets to the least-loaded team members of the respective team that is mapped using a `teams.py` file.  
- **Sprint Rebalancing** — Reassign tasks mid-sprint to balance workloads within teams.

### 📊 Live Insights & Dashboard

- **Scrum Reports** — Generate analytics for sprint, and team progress, along with a real-time dashboard.

### 🧠 AI-Powered Ticket Analysis

- **Summarize & Analyze** — Groq LLM analyzes each ticket for root causes, suggestions, and skill tags.

### ❓ Natural Language Queries

- Regex-based NLQ interprets plain English questions about Jira tickets, including:  
  - Sprint ticket counts  
  - Tickets assigned to a person  
  - Closed ticket percentages  
  - Active or in-progress tickets

---

## ⚙️ Tech Stack & Dependencies

- **Frontend:** Streamlit  
- **Data Handling:** pandas, numpy  
- **API Requests:** requests, HTTPBasicAuth  
- **Environment:** python-dotenv, Streamlit secrets  
- **AI & NLP:** Groq LLM  
- **Embeddings & Similarity:** Custom cosine similarity functions

