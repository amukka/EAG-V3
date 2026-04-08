/* global chrome */
(function () {
  const STORAGE_KEY = "youtubeShortsStats";
  const ext = globalThis.chrome;

  if (!ext || !ext.storage || !ext.storage.local) {
    return;
  }

  function todayKey() {
    return new Date().toISOString().slice(0, 10);
  }

  /** YouTube uses many URL shapes; count real watch surfaces only. */
  function isTrackedVideoPath() {
    const host = (location.hostname || "").replace(/^www\./, "").toLowerCase();
    const p = (location.pathname || "").replace(/\/$/, "") || "/";

    if (host === "youtu.be") {
      const id = p.replace(/^\//, "").split("/")[0];
      return id.length >= 6;
    }

    if (p === "/shorts" || p.startsWith("/shorts/")) return true;

    if (p === "/live" || p.startsWith("/live/")) {
      const seg = p.replace(/^\/live\/?/, "").split("/")[0];
      return Boolean(seg && seg.length >= 6);
    }

    if (p === "/watch" || p.startsWith("/watch")) {
      try {
        const u = new URL(location.href);
        const v = u.searchParams.get("v");
        if (v && v.length > 0) return true;

        if (p.startsWith("/watch/")) {
          const rest = p.slice("/watch/".length).split("/")[0];
          if (rest && rest.length >= 6) return true;
        }

        const hash = u.hash || "";
        const m = hash.match(/[?&]v=([^&]+)/);
        if (m && m[1] && String(m[1]).length > 0) return true;

        return false;
      } catch {
        return false;
      }
    }

    return false;
  }

  let storageChain = Promise.resolve();

  function enqueuePersist(mutator) {
    storageChain = storageChain.then(
      () =>
        new Promise((resolve) => {
          ext.storage.local.get([STORAGE_KEY], (res) => {
            if (ext.runtime && ext.runtime.lastError) {
              resolve();
              return;
            }
            const stats = res[STORAGE_KEY] || {
              totalSeconds: 0,
              byDay: {},
            };
            mutator(stats);
            stats.lastUpdated = Date.now();
            ext.storage.local.set({ [STORAGE_KEY]: stats }, () => {
              resolve();
            });
          });
        })
    );
  }

  function addOneSecond() {
    if (document.visibilityState !== "visible") return;
    if (!isTrackedVideoPath()) return;

    const day = todayKey();
    enqueuePersist((stats) => {
      stats.totalSeconds = (stats.totalSeconds || 0) + 1;
      stats.byDay = stats.byDay || {};
      stats.byDay[day] = (stats.byDay[day] || 0) + 1;
    });
  }

  let tick = null;

  function syncTimer() {
    const onVideo = isTrackedVideoPath();
    if (onVideo && document.visibilityState === "visible") {
      if (!tick) tick = setInterval(addOneSecond, 1000);
    } else {
      if (tick) {
        clearInterval(tick);
        tick = null;
      }
    }
  }

  document.addEventListener("visibilitychange", syncTimer);
  window.addEventListener("popstate", syncTimer);

  window.addEventListener("yt-navigate-finish", syncTimer);
  document.addEventListener("yt-navigate-finish", syncTimer);

  let lastHref = location.href;
  setInterval(() => {
    if (location.href !== lastHref) {
      lastHref = location.href;
      syncTimer();
    }
  }, 500);

  syncTimer();
})();
