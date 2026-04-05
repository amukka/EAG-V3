const SHORTS_KEY = "youtubeShortsStats";

function formatDuration(totalSeconds) {
  const s = Math.max(0, Math.floor(totalSeconds || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  if (h > 0) return `${h}h ${m}m ${r}s`;
  if (m > 0) return `${m}m ${r}s`;
  return `${r}s`;
}

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function render() {
  chrome.storage.local.get([SHORTS_KEY], (res) => {
    const stats = res[SHORTS_KEY] || { totalSeconds: 0, byDay: {} };
    const total = stats.totalSeconds || 0;
    const day = todayISO();
    const today = (stats.byDay && stats.byDay[day]) || 0;

    document.getElementById("totalShorts").textContent = formatDuration(total);
    document.getElementById("todayShorts").textContent = `Today (${day}): ${formatDuration(today)}`;
  });
}

document.getElementById("resetShorts").addEventListener("click", () => {
  if (!confirm("Reset all YouTube watch time (Shorts + regular videos) for this browser?")) return;
  chrome.storage.local.set({
    [SHORTS_KEY]: { totalSeconds: 0, byDay: {}, lastUpdated: Date.now() },
  }, render);
});

render();
setInterval(render, 1000);
