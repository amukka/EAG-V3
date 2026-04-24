# Youtube link for reference
https://youtu.be/lVLoCUwGvos

# Agentic Chrome Plugin (Python Backend)

This implementation uses:
- Python backend (`chrome_agent.py`) running on `http://localhost:5000`
- Chrome extension popup UI calling backend API `/api/analyze`

Agent loop pattern:

`Query -> LLM Response -> Tool Call -> Tool Result -> Query -> ... -> Final Answer`

The popup displays each step in a reasoning timeline.

## Files

- `manifest.json` - Chrome extension manifest (MV3)
- `chrome_agent.py` - Flask backend with LLM + tools + agentic loop
- `popup.html` - popup UI
- `popup.css` - popup styling
- `popup.js` - frontend API integration + reasoning rendering

## Custom Tools

- `get_product_details(product_name)`
- `compare_products(product_1, product_2)`
- `get_review_summary(product_name)`

## Backend Setup (Run First)

1. Open terminal in this folder:
   - `cd D:\Aswani\EAG_V3\agentic_chrome_plugin`
2. Create and activate venv (recommended):
   - `py -m venv .venv`
   - `.\.venv\Scripts\Activate.ps1`
3. Install dependencies:
   - `pip install flask flask-cors google-genai python-dotenv`
4. Add `.env` file in this folder:
   - `GEMINI_API_KEY=your_key_here`
   - `GEMINI_MODEL=gemini-2.5-flash-lite`
5. Start backend:
   - `python chrome_agent.py`

You should see:
- `Server starting on http://localhost:5000`
- `Chrome extension will call: http://localhost:5000/api/analyze`

## How to Load in Chrome

1. Open `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked**
4. Select this folder: `agentic_chrome_plugin`
5. Click **Reload** if already loaded

## How to Use

1. Start backend first (`python chrome_agent.py`)
2. Click extension icon -> open **Smart Purchase Advisor**
3. Enter query like:
   - `Should I buy samsung or iphone?`
   - `Should I buy dell laptop or hp?`
4. Click **Analyze**
5. See:
   - Agent Reasoning Chain timeline
   - Tool calls + tool results
   - Final Recommendation
   - Reasoning Summary
