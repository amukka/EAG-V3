"""
Chrome Extension Backend - Agentic Purchase Advisor

Run:
  pip install flask flask-cors google-genai python-dotenv
  python chrome_agent.py

Server:
  http://localhost:5000
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from google import genai

# Load .env from multiple likely locations:
# 1) current working directory
# 2) this script folder (agentic_chrome_plugin)
# 3) repo root (EAG_V3) - useful for shared project config
load_dotenv()
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
load_dotenv(SCRIPT_DIR / ".env")
load_dotenv(REPO_ROOT / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
THROTTLE_SECONDS = float(os.getenv("THROTTLE_SECONDS", "0.6"))

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is required in environment or .env")

client = genai.Client(api_key=GEMINI_API_KEY)

app = Flask(__name__)
CORS(app)


PRODUCT_DB = {
    "iphone 15": {
        "name": "iPhone 15",
        "brand": "Apple",
        "price": "Rs79,900",
        "display": "6.1in OLED, 60Hz",
        "chip": "A16 Bionic",
        "camera": "48MP + 12MP",
        "battery": "3349mAh",
    },
    "samsung galaxy s24": {
        "name": "Samsung Galaxy S24",
        "brand": "Samsung",
        "price": "Rs74,999",
        "display": "6.2in AMOLED, 120Hz",
        "chip": "Snapdragon 8 Gen 3",
        "camera": "50MP + 12MP + 10MP",
        "battery": "4000mAh",
    },
    "dell xps 14": {
        "name": "Dell XPS 14",
        "brand": "Dell",
        "price": "Rs1,69,999",
        "display": "14.5in 3.2K OLED",
        "chip": "Intel Core Ultra",
        "ram": "16GB",
        "battery": "69.5Wh",
    },
    "hp spectre x360": {
        "name": "HP Spectre x360",
        "brand": "HP",
        "price": "Rs1,54,999",
        "display": "14in OLED touch",
        "chip": "Intel Core Ultra",
        "ram": "16GB",
        "battery": "68Wh",
    },
}

REVIEW_DB = {
    "iphone 15": {
        "overall_sentiment": "Very Positive",
        "satisfaction_score": 4.6,
        "pros": ["Excellent video", "Long software support", "Strong resale value"],
        "cons": ["60Hz display", "Accessories expensive"],
    },
    "samsung galaxy s24": {
        "overall_sentiment": "Positive",
        "satisfaction_score": 4.5,
        "pros": ["Excellent display", "Versatile camera", "High customization"],
        "cons": ["Preinstalled apps", "Battery depends on usage profile"],
    },
    "dell xps 14": {
        "overall_sentiment": "Positive",
        "satisfaction_score": 4.4,
        "pros": ["Premium build", "Great display", "Solid productivity performance"],
        "cons": ["Premium price", "Limited ports"],
    },
    "hp spectre x360": {
        "overall_sentiment": "Positive",
        "satisfaction_score": 4.3,
        "pros": ["2-in-1 flexibility", "Premium design", "Great OLED panel"],
        "cons": ["Can run warm", "Pricey variants"],
    },
}

ALIASES = {
    "samsung": "samsung galaxy s24",
    "iphone": "iphone 15",
    "apple": "iphone 15",
    "dell": "dell xps 14",
    "hp": "hp spectre x360",
}


def _norm(text) -> str:
    # LLM occasionally passes a dict instead of a plain string; coerce safely
    if isinstance(text, dict):
        text = json.dumps(text)
    return (str(text) if text else "").strip().lower()


def _resolve_product(name: str) -> str:
    key = _norm(name)
    if key in PRODUCT_DB:
        return key
    if key in ALIASES:
        return ALIASES[key]
    if "iphone" in key or "apple" in key:
        return "iphone 15"
    if "samsung" in key or "galaxy" in key:
        return "samsung galaxy s24"
    if "dell" in key:
        return "dell xps 14"
    if key == "hp" or "hp " in key:
        return "hp spectre x360"
    return key


def get_product_details(product_name: str) -> dict[str, Any]:
    key = _resolve_product(product_name)
    if key not in PRODUCT_DB:
        return {"error": f"No details found for '{product_name}'"}
    return {"product_name": PRODUCT_DB[key]["name"], "details": PRODUCT_DB[key]}


def compare_products(product_1: str, product_2: str) -> dict[str, Any]:
    k1 = _resolve_product(product_1)
    k2 = _resolve_product(product_2)
    p1 = PRODUCT_DB.get(k1)
    p2 = PRODUCT_DB.get(k2)
    if not p1 or not p2:
        return {"error": "Could not resolve one or both products"}
    return {
        "comparison": {
            "product_1": p1["name"],
            "product_2": p2["name"],
            "price": {p1["name"]: p1["price"], p2["name"]: p2["price"]},
            "display": {p1["name"]: p1["display"], p2["name"]: p2["display"]},
            "camera": {p1["name"]: p1.get("camera", "N/A"), p2["name"]: p2.get("camera", "N/A")},
            "battery": {p1["name"]: p1["battery"], p2["name"]: p2["battery"]},
        }
    }


def get_review_summary(product_name: str) -> dict[str, Any]:
    key = _resolve_product(product_name)
    if key not in REVIEW_DB:
        return {"error": f"No reviews found for '{product_name}'"}
    return {"product_name": PRODUCT_DB[key]["name"], "reviews": REVIEW_DB[key]}


TOOLS = {
    "get_product_details": get_product_details,
    "compare_products": compare_products,
    "get_review_summary": get_review_summary,
}


SYSTEM_PROMPT = """You are a custom purchase advisor agent.
You must use tools to decide between products.

Tools:
1) get_product_details(product_name)
2) compare_products(product_1, product_2)
3) get_review_summary(product_name)

If user gives broad names (Samsung/iPhone/Dell/HP), map to:
- Samsung => Samsung Galaxy S24
- iPhone/Apple => iPhone 15
- Dell => Dell XPS 14
- HP => HP Spectre x360

Return ONLY JSON in one of these formats:

Tool call:
{"tool_name":"<name>","tool_arguments":{"arg":"value"},"reasoning_step":"brief reason"}

Final:
{
  "answer":"final recommendation",
  "reasoning_chain":["step1","step2","step3"],
  "confidence":"low|medium|high"
}
"""


def _call_llm(prompt: str) -> str:
    if THROTTLE_SECONDS > 0:
        time.sleep(THROTTLE_SECONDS)
    resp = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    return (resp.text or "").strip()


def _parse_llm_json(raw: str) -> dict[str, Any]:
    txt = raw.strip()
    if txt.startswith("```"):
        txt = txt.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", txt, re.DOTALL)
        if not m:
            raise
        return json.loads(m.group(0))


def _build_query(history: list[dict[str, str]]) -> str:
    out = []
    for item in history:
        role = item["role"]
        content = item["content"]
        if role == "system":
            out.append(content)
        elif role == "user":
            out.append(f"USER QUERY: {content}")
        elif role == "assistant":
            out.append(f"LLM RESPONSE: {content}")
        else:
            out.append(f"TOOL RESULT: {content}")
    return "\n\n".join(out)


def run_agentic_loop(user_query: str, max_iterations: int = 6) -> dict[str, Any]:
    history = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_query},
    ]
    trace = [{"type": "user_query", "title": "User Query", "payload": user_query}]

    for i in range(max_iterations):
        query_text = _build_query(history)
        trace.append({"type": "query", "title": f"Query{i+1} -> LLM", "payload": query_text})

        llm_raw = _call_llm(query_text)
        trace.append({"type": "llm_response", "title": "LLM Response", "payload": llm_raw})

        try:
            parsed = _parse_llm_json(llm_raw)
        except Exception as exc:  # noqa: BLE001
            err = {"error": f"Invalid JSON from LLM: {str(exc)}"}
            history.append({"role": "assistant", "content": llm_raw})
            history.append({"role": "tool", "content": json.dumps(err)})
            trace.append({"type": "error", "title": "Parse Error", "payload": err})
            continue

        if "answer" in parsed:
            result = {
                "answer": parsed["answer"],
                "reasoning_chain": parsed.get("reasoning_chain", []),
                "confidence": parsed.get("confidence", "medium"),
            }
            trace.append({"type": "result", "title": "Final Recommendation", "payload": result["answer"]})
            return {"trace": trace, "result": result}

        tool_name = parsed.get("tool_name")
        tool_args = parsed.get("tool_arguments", {})
        reason = parsed.get("reasoning_step", "No reasoning step provided")
        trace.append({"type": "reason", "title": "Reasoning", "payload": reason})
        trace.append({"type": "tool_call", "title": f"Tool Call: {tool_name}()", "payload": tool_args})

        if tool_name not in TOOLS:
            tool_result = {"error": f"Unknown tool: {tool_name}"}
        else:
            try:
                tool_result = TOOLS[tool_name](**tool_args)
            except TypeError as exc:
                tool_result = {"error": f"Bad arguments for {tool_name}: {str(exc)}"}

        trace.append({"type": "tool_result", "title": "Tool Result", "payload": tool_result})
        history.append({"role": "assistant", "content": llm_raw})
        history.append({"role": "tool", "content": json.dumps(tool_result)})

    return {
        "trace": trace,
        "result": {
            "answer": "Could not complete within max iterations.",
            "reasoning_chain": ["Agent hit iteration limit"],
            "confidence": "low",
        },
    }


@app.get("/health")
def health():
    return jsonify({"status": "ok", "model": GEMINI_MODEL})


@app.post("/api/analyze")
def analyze():
    data = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"error": "query is required"}), 400

    payload = run_agentic_loop(query)
    return jsonify(payload)


if __name__ == "__main__":
    print("\nChrome Extension Backend Running")
    print("--------------------------------")
    print("Server starting on http://localhost:5000")
    print("Chrome extension will call: http://localhost:5000/api/analyze\n")
    app.run(host="127.0.0.1", port=5000, debug=True)
