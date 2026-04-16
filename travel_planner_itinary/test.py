import urllib.request
import json
import re
import os

print("1. Reading API Key from .env...")
api_key = None
script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(script_dir, '.env')

try:
    with open(env_path, 'r') as f:
        for line in f:
            if line.startswith('GEMINI_API_KEY='):
                api_key = line.strip().split('=', 1)[1]
                break
except Exception as e:
    print(f"Failed to open .env at {env_path}:", e)

if not api_key:
    print("Error: Could not find GEMINI_API_KEY in .env")
    exit(1)

print("2. Scraping Munnar Travel Blog...")
url = "https://beantowntraveller.com/2023/03/19/munnar-a-complete-travel-guide/"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req) as response:
        html = response.read().decode('utf-8')
except Exception as e:
    print(f"Error fetching URL: {e}")
    exit(1)

# Extract paragraphs naively
paragraphs = re.findall(r'<p>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
text_content = " ".join([re.sub(r'<[^>]+>', '', p) for p in paragraphs])
print(f"   Extracted {len(text_content)} characters of text.")

print("3. Calling Gemini 3.1 Flash Lite Preview...")
prompt = f"""You are an expert travel planner and an intelligent text analyzer. Your goal is to analyze the following text extracted from a travel blog, and generate structured, actionable, and beautiful insights.
Please provide your response strictly in a valid JSON format (without markdown codeblocks) with the following keys:
1. "destination": The main city or country being discussed.
2. "highlights": An array of objects, each with a "name" and a short "description" of the best places, foods, or experiences.
3. "best_time_to_visit": The recommended time to visit based on the text.
4. "approximate cost": The approximate cost of the trip based on the text.
5. "itinerary": An array of objects for a day-by-day travel plan. Include "day" (e.g., 'Day 1'), "title", and an array of "activities" (strings).
If the text is clearly not about travel, return {{"error": "This page does not appear to be a travel blog."}}.

Text:
{text_content[:30000]}"""

gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite-preview:generateContent?key={api_key}"
payload = {
    "contents": [{"parts": [{"text": prompt}]}],
    "generationConfig": {
        "temperature": 0.3,
        "responseMimeType": "application/json"
    }
}

req = urllib.request.Request(
    gemini_url, 
    data=json.dumps(payload).encode('utf-8'),
    headers={'Content-Type': 'application/json'},
    method='POST'
)

try:
    with urllib.request.urlopen(req) as response:
        result = json.loads(response.read().decode('utf-8'))
        raw_text = result['candidates'][0]['content']['parts'][0]['text']
        print("\n=================")
        print("GEMINI JSON RESPONSE:")
        print("=================\n")
        print(raw_text)
except Exception as e:
    print("Error calling Gemini:", e)
    if hasattr(e, 'read'):
        print(e.read().decode('utf-8'))
