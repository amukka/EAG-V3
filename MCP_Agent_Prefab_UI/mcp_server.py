import json
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List

from fastmcp import FastMCP
from prefab_ui.app import PrefabApp
from prefab_ui.components import (
    Badge,
    Card,
    CardContent,
    CardHeader,
    CardTitle,
    Column,
    Dot,
    Row,
    Text,
    Muted,
)

# =========================================================
# CONFIG
# =========================================================
mcp = FastMCP("Iran News Collector")

BASE_DIR = Path(__file__).parent
FACTS_FILE = BASE_DIR / "facts.json"
LOG_FILE = BASE_DIR / "agent_log.json"

RSS_URL = "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml"

KEYWORDS = [
    "iran", "tehran", "israel", "missile",
    "strike", "attack", "war", "nuclear"
]

# =========================================================
# FILE UTILITIES (SAFE)
# =========================================================
def _safe_load(path: Path) -> List:
    try:
        if not path.exists():
            return []
        return json.loads(path.read_text())
    except Exception:
        return []


def _safe_save(path: Path, data: List):
    path.write_text(json.dumps(data, indent=2))


def _load_facts() -> List[str]:
    return _safe_load(FACTS_FILE)


def _load_log() -> List[str]:
    return _safe_load(LOG_FILE)


def _save_facts(facts: List[str]):
    _safe_save(FACTS_FILE, facts)


def _log_step(step: str):
    log = _load_log()
    log.append(step)
    _safe_save(LOG_FILE, log)


# =========================================================
# TOOL: FETCH NEWS
# =========================================================
@mcp.tool()
def fetch_news() -> str:
    """
    Fetch latest Middle East news from BBC RSS,
    filter for Iran-related headlines, and return top 4.
    """
    try:
        response = requests.get(RSS_URL, timeout=10)
        response.raise_for_status()

        root = ET.fromstring(response.content)
        items = root.findall("./channel/item")

        if not items:
            msg = "No news found."
            _log_step(msg)
            return msg

        def relevance(item):
            text = (
                (item.findtext("title") or "") + " " +
                (item.findtext("description") or "")
            ).lower()
            return sum(keyword in text for keyword in KEYWORDS)

        # Sort by relevance
        items_sorted = sorted(items, key=relevance, reverse=True)
        top_items = items_sorted[:4]

        headlines = []
        for item in top_items:
            title = item.findtext("title") or "No title"
            pub_date = item.findtext("pubDate") or "No date"
            headlines.append(f"[{pub_date}] {title}")

        result = "\n".join(
            f"{i + 1}. {headline}" for i, headline in enumerate(headlines)
        )

        _log_step(f"Fetched {len(headlines)} headlines")
        return result

    except Exception as e:
        error_msg = f"Error fetching news: {str(e)}"
        _log_step(error_msg)
        return error_msg


# =========================================================
# TOOL: SAVE
# =========================================================
@mcp.tool()
def save_fact(fact: str) -> str:
    """Save a headline to local storage."""
    facts = _load_facts()
    facts.append(fact)
    _save_facts(facts)

    msg = f"Saved! You now have {len(facts)} item(s)."
    _log_step(msg)
    return msg


# =========================================================
# TOOL: READ
# =========================================================
@mcp.tool()
def read_facts() -> str:
    """Read all saved headlines."""
    facts = _load_facts()

    if not facts:
        msg = "No items saved yet."
        _log_step(msg)
        return msg

    result = "\n".join(
        f"{i + 1}. {fact}" for i, fact in enumerate(facts)
    )

    _log_step("Read all items")
    return result


# =========================================================
# TOOL: DELETE
# =========================================================
@mcp.tool()
def delete_fact(index: int) -> str:
    """Delete a saved item by 1-based index."""
    facts = _load_facts()

    if index < 1 or index > len(facts):
        msg = f"Invalid index. You have {len(facts)} item(s)."
        _log_step(msg)
        return msg

    removed = facts.pop(index - 1)
    _save_facts(facts)

    msg = f"Deleted: {removed}"
    _log_step(msg)
    return msg


# =========================================================
# TOOL: UI
# =========================================================
@mcp.tool(app=True)
def show_iran_war_headlines() -> PrefabApp:
    """Display Iran War latest News headlines and logs these in UI."""
    facts = _load_facts()
    log = _load_log()

    badge_variants = ["default", "secondary", "info", "success", "warning"]

    with PrefabApp(css_class="max-w-2xl mx-auto") as app:

        # -------------------------
        # HEADLINES CARD
        # -------------------------
        with Card(css_class="border-blue-300 bg-blue-50"):
            with CardHeader(css_class="bg-blue-100 rounded-t-lg"):
                with Row(gap=2):
                    Dot(variant="info")
                    CardTitle("Iran War Headlines")

            with CardContent():
                with Column(gap=3):
                    if facts:
                        Badge(f"{len(facts)} saved", variant="info")

                        for i, fact in enumerate(facts, 1):
                            with Row(gap=2, css_class="items-start"):
                                Badge(str(i), variant=badge_variants[i % len(badge_variants)])
                                Text(fact)
                    else:
                        Muted("No headlines saved yet.")

        # -------------------------
        # LOG CARD
        # -------------------------
        with Card(css_class="border-purple-300 bg-purple-50"):
            with CardHeader(css_class="bg-purple-100 rounded-t-lg"):
                with Row(gap=2):
                    Dot(variant="default")
                    CardTitle("Agent Activity Log")

            with CardContent():
                with Column(gap=2):
                    if log:
                        for i, step in enumerate(log):
                            with Row(gap=2, css_class="items-start"):
                                Badge(f"Step {i + 1}", variant="secondary")
                                Muted(step)
                    else:
                        Muted("No agent activity yet.")

    return app


# =========================================================
# ENTRYPOINT
# =========================================================
if __name__ == "__main__":
    mcp.run()