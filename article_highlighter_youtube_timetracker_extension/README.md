# Article Highlighter & YouTube Watch Timer

A **Chrome / Edge** extension (Manifest V3) that:

1. **Saves article highlights** — Select text on web pages; it is underlined and tinted. When you return to the same page, highlights are restored. **Alt+click** a highlight to remove it permanently for that page.
2. **Tracks YouTube watch time** — Counts seconds while a **Shorts** or **regular video** tab is open and **visible** (not when the tab is in the background).

Data is stored **locally** in the browser (`chrome.storage.local`). Nothing is sent to a server by this extension.

---

## Requirements

- **Google Chrome** or **Microsoft Edge** (desktop)
- **Developer mode** enabled to load an unpacked extension

This extension is **not** supported in mobile Chrome the same way as on desktop.

---

## Install (load unpacked)

1. Open **Extensions**:
   - Chrome: `chrome://extensions`
   - Edge: `edge://extensions`
2. Turn **Developer mode** **ON**.
3. Click **Load unpacked**.
4. Select **this folder** (the one that contains `manifest.json`).

Pin the extension if you want quick access to the popup.

---

## How to use

### Highlights

- On any **http** or **https** page, **select text** with the mouse and release.
- Text is wrapped with a yellow tint and underline. Hover the highlight for the hint: **Alt+click** removes it from the page and from saved storage (it will not come back on reload).
- Highlights are keyed by page URL (the hash `#...` part of the URL is ignored).
- Older saved highlights without an internal id are assigned ids automatically the next time the page loads, so Alt+click works for them too.
- Some sites load content late; the extension retries restore shortly after load.

### YouTube timer

Time increases when **all** of the following are true:

- The tab is on **YouTube** (`youtube.com`, `m.youtube.com`) or a short link **`youtu.be/...`**.
- The URL looks like a **watch surface**, for example:
  - **Shorts:** `/shorts` or `/shorts/...`
  - **Regular video:** `/watch` with `v=` in the query, `/watch/VIDEO_ID`, or `v=` inside the hash (older clients)
  - **Live:** `/live/...`
- The tab is **visible** (you are looking at that tab).

**Note:** This measures **time on the video page**, not whether the video is playing or paused. The home page, search, and subscriptions are **not** counted.

### Popup

Click the extension icon to see **total** and **today’s** YouTube watch time. The popup **refreshes every second** while it is open. Use **Reset YouTube watch stats** to clear stored totals for this browser profile.

---

## Project files

| File | Role |
|------|------|
| `manifest.json` | Extension config, permissions, content scripts |
| `content.js` | Article highlight save/restore |
| `shorts-content.js` | YouTube Shorts + `/watch?v=` timer |
| `popup.html` / `popup.js` | Toolbar popup UI |

---

## After you change the code

On the extensions page, click **Reload** on this extension’s card so changes apply.

---

## Permissions

- **`storage`** — Save highlights and watch-time statistics locally.

---

## Version

See `manifest.json` → `version` (currently **1.0.3**).

# Youtube link
https://youtu.be/pdhgawLSON4 