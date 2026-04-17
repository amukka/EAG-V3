# 🌍 Travel Planner AI Chrome Extension

Welcome to **Travel Planner AI**, a beautiful, completely local Google Chrome extension that instantly turns any travel blog or article into a structured, day-by-day travel itinerary!

Powered by Google's massive **Gemini 3.1 Flash Lite Preview** model, this extension invisibly reads the travel blog you are currently viewing and generates actionable insights with a single click.

## Video Walk Through Link
- https://youtu.be/6ZvE-8d5JOY

## ✨ Features

- **Instant Insights**: Extracts the destination and the best time to visit directly from the text.
- **Holistic Budget Estimates**: Uses Gemini's vast general knowledge to estimate the total cost of the trip, rather than just pulling isolated ticket prices.
- **Top Highlights**: A clean, readable list of the best places, foods, and experiences mentioned in the article.
- **Beautiful Itineraries**: Generates a structured, day-by-day travel plan.
- **Premium UI**: Crafted with modern glassmorphism, Google Fonts ("Outfit"), and smooth animations.
- **100% Local Privacy**: The extension runs entirely in your browser and reads your API key locally. No backend servers required!

## 🚀 Setup & Installation

Because this extension securely reads your Gemini API Key from a local configuration file, we will load it directly into Chrome using Developer Mode.

### 1. Configure your API Key
1. In the root directory of this project, you will find a `.env` file (or create one if it doesn't exist).
2. Open the `.env` file and add your Gemini API Key like this:
   ```env
   GEMINI_API_KEY=AIzaSyYourKeyHere...
   ```

### 2. Load the Extension into Chrome
1. Open Google Chrome.
2. In the URL bar, type: `chrome://extensions/` and hit **Enter**.
3. Turn on **Developer mode** using the toggle switch in the top right corner.
4. Click the **Load unpacked** button in the top left corner.
5. Select the folder containing this code (e.g., `travel_planner_itinary`).
6. Success! The **Travel Planner AI** extension will appear in your list. 

### 3. Pin & Use!
1. Click the puzzle icon 🧩 in your Chrome toolbar and **Pin 📌** the extension for easy access.
2. Navigate to your favorite travel blog (e.g., a guide on Munnar, Kerala).
3. Click the extension icon and hit **✨ Analyze Travel Blog**.
4. Enjoy your beautifully crafted travel plan!

## 🛠️ Built With
- HTML / Vanilla CSS / Vanilla JS
- Chrome Extensions API (Manifest V3)
- Google Gemini API (`gemini-3.1-flash-lite-preview`)
