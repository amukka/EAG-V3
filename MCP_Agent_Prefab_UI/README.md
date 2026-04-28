# 🇮ran War News Collector — MCP + Agent System

## 📌 Overview

This project demonstrates a complete **Model Context Protocol (MCP)** workflow using:

- 🧠 **Agent (LLM loop with Gemini)**
- 🛠 **MCP Server (tool provider)**
- 🌐 **Real-time data (Iran War Headlines RSS feed)**
- 💾 **Local storage (CRUD operations)**
- 🖥 **Prefab UI (visual interface)**

The system fetches Iran-related news headlines, saves them locally, and displays them in an interactive UI.

---

## 🧩 Architecture
facts_agent.py ──calls──▶ facts_server.py
│ │
│ ├── fetch_news() → Iran War Headlines
│ ├── save_fact() → facts.json
│ ├── read_facts()
│ ├── delete_fact()
│ └── show_iran_war_headlines() → UI
│
└──────────────▶ agent_log.json (step tracking)


---

## 📁 Project Structure
├── facts_server.py # MCP server (tools + UI)
├── facts_agent.py # Agent loop (Gemini-based)
├── facts.json # Stored headlines (auto-created)
├── agent_log.json # Agent execution log (auto-created)
├── .env # API keys
└── README.md'


---

## 🛠 MCP Server (`facts_server.py`)

Defines tools exposed via MCP:

| Tool | Type | Description |
|------|------|-------------|
| `fetch_news()` | 🌐 Internet | Fetches top 4 Iran-related headlines from BBC RSS |
| `save_fact(fact)` | 💾 CRUD | Saves a headline |
| `read_facts()` | 💾 CRUD | Reads saved headlines |
| `delete_fact(index)` | 💾 CRUD | Deletes headline by index |
| `show_iran_war_headlines()` | 🖥 UI | Displays headlines + logs |

---

## 🧠 Agent (`facts_agent.py`)

Implements an **agentic loop**:

- Connects to MCP server via stdio
- Uses Gemini to decide next action
- Calls tools one-by-one
- Logs every step

---

## 🔄 Agent Workflow
fetch_news → save_fact × 4 → show_iran_war_headlines → FINAL_ANSWER


### Execution Pattern
Query → LLM → Tool Call → Tool Result → LLM → Next Action → Final Answer


---

## ⚙️ Setup Instructions

### 1. Create Virtual Environment

```bash
cd <dir>
"C:\Program Files\Python311\python.exe" -m venv venv
venv\Scripts\activate

2. Install Dependencies

pip install "fastmcp[apps]" fastmcp prefab-ui requests mcp google-genai python-dotenv

3. Configure Environment Variables
Create a .env file:
GEMINI_API_KEY=your_api_key_here

🔧 1. Setup (First Time Only)

cd <dir>

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Install dependencies
pip install fastmcp "fastmcp[apps]" prefab-ui requests mcp google-genai python-dotenv

🖥️ 2. Terminal 1 — Start the UI Server

venv\Scripts\activate
fastmcp dev apps facts_server.py

🌐 Open in browser:

http://localhost:8080

What this does:

Starts MCP server
Launches Prefab UI
Exposes tools like:
fetch_fact
save_fact
show_iran_war_headlines

🤖 3. Terminal 2 — Run the Agent

venv\Scripts\activate
python facts_agent.py

What happens:

    Agent connects to MCP server
    Calls tools step-by-step:
    Fetch headlines
    Save each headline
    Show UI

🧾 4. View the UI

http://localhost:8080

Then:

    Select show_iran_war_headlines
    Click Launch

## 🎯 Key Features

### ✅ MCP Server
- ✅ Tool registration
- ✅ Tool execution
- ✅ App registration
- ✅ UI hosting

### ✅ Agent
- ✅ Tool calling
- ✅ Step-by-step execution
- ✅ Logging
- ✅ Gemini integration

### ✅ UI
- ✅ Card layout
- ✅ Badge styling
- ✅ Interactive buttons
- ✅ Real-time updates