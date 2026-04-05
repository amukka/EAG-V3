(function () {
  const MARK_CLASS = "smart-ah-mark";
  const STORAGE_KEY = "articleHighlights";
  const PREFIX_LEN = 80;
  const SUFFIX_LEN = 80;

  function randomId() {
    return crypto.randomUUID
      ? crypto.randomUUID()
      : "ah-" + Date.now() + "-" + Math.random().toString(36).slice(2, 11);
  }

  function normalizeUrl() {
    try {
      const u = new URL(location.href);
      u.hash = "";
      return u.href;
    } catch {
      return location.href;
    }
  }

  function collectTextSegments(root) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        if (!node.nodeValue || node.nodeValue.length === 0) {
          return NodeFilter.FILTER_REJECT;
        }
        const el = node.parentElement;
        if (!el || el.closest("script, style, noscript, textarea")) {
          return NodeFilter.FILTER_REJECT;
        }
        return NodeFilter.FILTER_ACCEPT;
      },
    });
    const segments = [];
    while (walker.nextNode()) {
      const n = walker.currentNode;
      segments.push({ node: n, len: n.length });
    }
    return segments;
  }

  function flatTextFromSegments(segments) {
    return segments.map((s) => s.node.nodeValue).join("");
  }

  function rangeFromOffsets(segments, start, end) {
    let pos = 0;
    let startNode = null;
    let startOff = 0;
    let endNode = null;
    let endOff = 0;
    for (const { node, len } of segments) {
      const next = pos + len;
      if (startNode === null && start < next) {
        startNode = node;
        startOff = start - pos;
      }
      if (end <= next) {
        endNode = node;
        endOff = end - pos;
        break;
      }
      pos = next;
    }
    if (!startNode || !endNode) return null;
    const r = document.createRange();
    try {
      r.setStart(startNode, startOff);
      r.setEnd(endNode, endOff);
    } catch {
      return null;
    }
    return r;
  }

  function rangeInsideMark(range) {
    let n = range.commonAncestorContainer;
    if (n.nodeType === Node.TEXT_NODE) n = n.parentElement;
    return n && n.closest && n.closest("." + MARK_CLASS);
  }

  function offsetsFromRange(range) {
    const body = document.body;
    if (!body) return null;
    const preStart = document.createRange();
    preStart.selectNodeContents(body);
    preStart.setEnd(range.startContainer, range.startOffset);
    const start = preStart.toString().length;

    const preEnd = document.createRange();
    preEnd.selectNodeContents(body);
    preEnd.setEnd(range.endContainer, range.endOffset);
    const end = preEnd.toString().length;

    if (start < 0 || end <= start) return null;
    return { start, end };
  }

  function makeAnchor(range) {
    const segments = collectTextSegments(document.body);
    const flat = flatTextFromSegments(segments);
    const off = offsetsFromRange(range);
    if (!off) return null;
    let { start, end } = off;
    if (end > flat.length) end = flat.length;
    if (start >= flat.length) return null;

    const exact = flat.slice(start, end);
    if (exact.trim().length < 2) return null;

    const prefix = flat.slice(Math.max(0, start - PREFIX_LEN), start);
    const suffix = flat.slice(end, Math.min(flat.length, end + SUFFIX_LEN));

    return { exact, prefix, suffix };
  }

  function findRangeForAnchor(anchor) {
    const segments = collectTextSegments(document.body);
    const flat = flatTextFromSegments(segments);
    const { exact, prefix, suffix } = anchor;
    let from = 0;
    while (from < flat.length) {
      const i = flat.indexOf(exact, from);
      if (i === -1) break;
      const pSlice = flat.slice(Math.max(0, i - prefix.length), i);
      const sSlice = flat.slice(i + exact.length, i + exact.length + suffix.length);
      const pOk = !prefix || pSlice === prefix;
      const sOk = !suffix || sSlice === suffix;
      if (pOk && sOk) {
        const r = rangeFromOffsets(segments, i, i + exact.length);
        if (r && !rangeInsideMark(r)) return r;
      }
      from = i + 1;
    }
    return null;
  }

  function wrapRange(range, entry) {
    const span = document.createElement("mark");
    span.className = MARK_CLASS;
    span.style.backgroundColor = "rgba(255, 235, 59, 0.45)";
    span.style.textDecoration = "underline";
    span.style.textDecorationColor = "#f57f17";
    span.style.textUnderlineOffset = "2px";
    span.title = "Alt+click to remove this highlight";
    const id = entry && entry.id;
    if (id) span.dataset.ahId = id;
    try {
      range.surroundContents(span);
    } catch {
      const frag = range.extractContents();
      span.appendChild(frag);
      range.insertNode(span);
    }
  }

  function unwrapMark(mark) {
    const parent = mark.parentNode;
    if (!parent) return;
    while (mark.firstChild) {
      parent.insertBefore(mark.firstChild, mark);
    }
    parent.removeChild(mark);
    parent.normalize();
  }

  function removeHighlightId(id) {
    if (!id) return;
    const url = normalizeUrl();
    chrome.storage.local.get([STORAGE_KEY], (res) => {
      const all = res[STORAGE_KEY] || {};
      const list = all[url] || [];
      all[url] = list.filter((e) => e.id !== id);
      chrome.storage.local.set({ [STORAGE_KEY]: all });
    });
  }

  function loadHighlights(callback) {
    const url = normalizeUrl();
    chrome.storage.local.get([STORAGE_KEY], (res) => {
      const all = res[STORAGE_KEY] || {};
      callback(url, all[url] || []);
    });
  }

  function saveHighlightEntry(anchor, existingId) {
    const url = normalizeUrl();
    const { exact, prefix, suffix } = anchor;
    const id = existingId || randomId();
    chrome.storage.local.get([STORAGE_KEY], (res) => {
      const all = res[STORAGE_KEY] || {};
      const list = all[url] || [];
      list.push({ exact, prefix, suffix, id });
      all[url] = list;
      chrome.storage.local.set({ [STORAGE_KEY]: all });
    });
    return id;
  }

  function ensureEntryIds(url, list, done) {
    let changed = false;
    const next = list.map((e) => {
      if (e.id) return e;
      changed = true;
      return { exact: e.exact, prefix: e.prefix, suffix: e.suffix, id: randomId() };
    });
    if (!changed) {
      done(next);
      return;
    }
    chrome.storage.local.get([STORAGE_KEY], (res) => {
      const all = res[STORAGE_KEY] || {};
      all[url] = next;
      chrome.storage.local.set({ [STORAGE_KEY]: all }, () => done(next));
    });
  }

  function restoreAll() {
    loadHighlights((url, list) => {
      ensureEntryIds(url, list, (withIds) => {
        withIds.forEach((entry) => {
          const range = findRangeForAnchor(entry);
          if (range) wrapRange(range, entry);
        });
      });
    });
  }

  function runRestorePasses() {
    restoreAll();
    setTimeout(restoreAll, 1200);
    setTimeout(restoreAll, 3500);
  }

  let lastSelectionTime = 0;
  document.addEventListener("mouseup", () => {
    const now = Date.now();
    if (now - lastSelectionTime < 400) return;
    lastSelectionTime = now;

    const sel = window.getSelection();
    if (!sel || !sel.rangeCount) return;

    const range = sel.getRangeAt(0);
    if (range.collapsed) return;

    if (range.toString().trim().length < 2) return;

    if (rangeInsideMark(range)) return;

    const anchor = makeAnchor(range);
    if (!anchor) return;

    const clone = range.cloneRange();
    const id = randomId();
    wrapRange(clone, { id });
    saveHighlightEntry(anchor, id);
    sel.removeAllRanges();
  });

  document.addEventListener(
    "click",
    (e) => {
      if (!e.altKey) return;
      const mark = e.target.closest && e.target.closest("." + MARK_CLASS);
      if (!mark || !mark.dataset.ahId) return;
      e.preventDefault();
      e.stopPropagation();
      const hid = mark.dataset.ahId;
      unwrapMark(mark);
      removeHighlightId(hid);
    },
    true
  );

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", runRestorePasses);
  } else {
    runRestorePasses();
  }

  window.addEventListener("load", runRestorePasses);
})();
