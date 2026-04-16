document.addEventListener('DOMContentLoaded', () => {
  const analyzeBtn = document.getElementById('analyze-btn');
  const retryBtn = document.getElementById('retry-btn');
  
  const stateInitial = document.getElementById('initial-state');
  const stateLoading = document.getElementById('loading-state');
  const stateError = document.getElementById('error-state');
  const stateResult = document.getElementById('result-state');
  
  const errorMessage = document.getElementById('error-message');

  function switchState(stateElement) {
    [stateInitial, stateLoading, stateError, stateResult].forEach(el => {
      el.classList.remove('active');
    });
    stateElement.classList.add('active');
  }

  async function getApiKey() {
    try {
      const response = await fetch(chrome.runtime.getURL('.env'));
      const text = await response.text();
      // Match GEMINI_API_KEY=...
      const match = text.match(/GEMINI_API_KEY=([^\r\n]+)/);
      if (match && match[1]) {
        return match[1].trim();
      }
      throw new Error("API Key not found in .env file.");
    } catch (e) {
      console.error("Error reading .env:", e);
      throw new Error("Could not read API Key. Is .env file properly configured?");
    }
  }

  async function analyzePage() {
    switchState(stateLoading);
    
    try {
      // 1. Get the current active tab
      let [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab) throw new Error("No active tab found.");

      // 2. Execute content script to scrape text
      const injectionResults = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ['content.js']
      });

      const extractedText = injectionResults[0].result;
      if (!extractedText || extractedText.length < 50) {
        throw new Error("Could not find enough readable text on this page.");
      }

      // 3. Get API Key from .env
      const apiKey = await getApiKey();

      // 4. Call Gemini API
      const prompt = `You are an expert travel planner and an intelligent text analyzer. Your goal is to analyze the following text extracted from a travel blog, and generate structured, actionable, and beautiful insights.
Please provide your response strictly in a valid JSON format (without markdown codeblocks) with the following keys:
1. "destination": The main city or country being discussed.
2. "highlights": An array of objects, each with a "name" and a short "description" of the best places, foods, or experiences.
3. "best_time_to_visit": The recommended time to visit based on the text.
4. "estimated_cost": Provide a comprehensive estimated total budget for this trip (e.g., "≈ $500 - $800 total" or "₹15,000 - ₹20,000"). Use your general knowledge of the destination's average hotel, food, and transport costs to give a holistic estimate. Do not just quote isolated prices from the text.
5. "itinerary": An array of objects for a day-by-day travel plan. Include "day" (e.g., 'Day 1'), "title", and an array of "activities" (strings).
If the text is clearly not about travel, return {"error": "This page does not appear to be a travel blog."}.

Text:
${extractedText.substring(0, 30000)} // sending up to 30000 chars`;

      const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite-preview:generateContent?key=${apiKey}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contents: [{ parts: [{ text: prompt }] }],
          generationConfig: {
            temperature: 0.3,
            responseMimeType: "application/json"
          }
        })
      });

      if (!response.ok) {
        const errDetails = await response.text();
        console.error("Gemini API Error:", errDetails);
        throw new Error(`Failed to fetch from Gemini API: ${response.status}`);
      }

      const data = await response.json();
      const rawText = data.candidates[0].content.parts[0].text;
      
      let parsedData;
      try {
        parsedData = JSON.parse(rawText.replace(/```json\n?|\n?```/g, '').trim());
      } catch (parseError) {
        console.error("Failed to parse JSON:", rawText);
        throw new Error("Invalid response format from Gemini.");
      }

      if (parsedData.error) {
        throw new Error(parsedData.error);
      }

      // 5. Populate UI
      populateUI(parsedData);
      switchState(stateResult);

    } catch (error) {
      console.error(error);
      errorMessage.textContent = error.message;
      switchState(stateError);
    }
  }

  function populateUI(data) {
    document.getElementById('destination-title').textContent = data.destination || "Unknown Destination";
    document.getElementById('best-time-text').textContent = data.best_time_to_visit || "Anytime";
    document.getElementById('estimated-cost-text').textContent = data.estimated_cost || "Cost varies";

    // Populate highlights
    const highlightsList = document.getElementById('highlights-list');
    highlightsList.innerHTML = '';
    if (data.highlights && data.highlights.length > 0) {
      data.highlights.forEach(h => {
        const li = document.createElement('li');
        li.innerHTML = `<span class="highlight-name">${h.name}</span><p class="highlight-desc">${h.description}</p>`;
        highlightsList.appendChild(li);
      });
    } else {
      highlightsList.innerHTML = '<li><p class="highlight-desc">No specific highlights found.</p></li>';
    }

    // Populate itinerary
    const itineraryContainer = document.getElementById('itinerary-container');
    itineraryContainer.innerHTML = '';
    if (data.itinerary && data.itinerary.length > 0) {
      data.itinerary.forEach(day => {
        const card = document.createElement('div');
        card.className = 'day-card';
        
        let activitiesHTML = '';
        if (day.activities && day.activities.length) {
          activitiesHTML = `<ul class="activity-list">${day.activities.map(a => `<li>${a}</li>`).join('')}</ul>`;
        }

        card.innerHTML = `
          <div class="day-header">
            <span class="day-label">${day.day || ''}</span>
          </div>
          <h4 class="day-title">${day.title || 'Explore'}</h4>
          ${activitiesHTML}
        `;
        itineraryContainer.appendChild(card);
      });
    } else {
      itineraryContainer.innerHTML = '<p class="helper-text">No detailed itinerary available.</p>';
    }
  }

  analyzeBtn.addEventListener('click', analyzePage);
  retryBtn.addEventListener('click', () => switchState(stateInitial));
});
