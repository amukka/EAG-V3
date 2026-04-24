const queryInput = document.getElementById("query");
const runBtn = document.getElementById("runBtn");
const clearBtn = document.getElementById("clearBtn");
const analyzePageBtn = document.getElementById("analyzePageBtn");
const compareBtn = document.getElementById("compareBtn");
const traceEl = document.getElementById("trace");
const finalEl = document.getElementById("final");
const finalAnswerEl = document.getElementById("finalAnswer");
const reasoningChainEl = document.getElementById("reasoningChain");
const API_BASE = "http://localhost:5000";

function toPretty(value) {
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

function createIterationCard(iterationNumber) {
  const details = document.createElement("details");
  details.className = "iteration-card";
  details.open = true;

  const summary = document.createElement("summary");
  summary.textContent = `Iteration ${iterationNumber}`;
  details.appendChild(summary);

  const body = document.createElement("div");
  body.className = "iteration-body";
  details.appendChild(body);

  traceEl.appendChild(details);
  traceEl.scrollTop = traceEl.scrollHeight;
  return body;
}

function appendIterationRow(iterationBodyEl, title, payload, kind = "llm") {
  const row = document.createElement("div");
  row.className = "row";

  const safeKind = ["query", "llm", "tool", "reason", "result", "error"].includes(kind) ? kind : "llm";
  const header = document.createElement("div");
  header.className = "row-header";
  header.innerHTML = `<span class="badge badge-${safeKind}">${safeKind.toUpperCase()}</span><strong>${title}</strong>`;

  const content = document.createElement("div");
  content.textContent = toPretty(payload);

  row.appendChild(header);
  row.appendChild(content);
  iterationBodyEl.appendChild(row);
  traceEl.scrollTop = traceEl.scrollHeight;
}

function setFinalPanels(result) {
  finalAnswerEl.textContent = result?.answer || "No answer generated.";
  reasoningChainEl.innerHTML = "";
  if (Array.isArray(result?.reasoning_chain) && result.reasoning_chain.length > 0) {
    for (const step of result.reasoning_chain) {
      const li = document.createElement("li");
      li.textContent = step;
      reasoningChainEl.appendChild(li);
    }
  } else {
    const li = document.createElement("li");
    li.textContent = "No reasoning chain provided.";
    reasoningChainEl.appendChild(li);
  }
}

function mapTraceTypeToKind(type) {
  if (type === "query" || type === "user_query") return "query";
  if (type === "llm_response") return "llm";
  if (type === "tool_call" || type === "tool_result") return "tool";
  if (type === "reason") return "reason";
  if (type === "error") return "error";
  if (type === "result") return "result";
  return "llm";
}

async function runBackendAgenticLoop(userQuery) {
  const response = await fetch(`${API_BASE}/api/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query: userQuery })
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Backend error ${response.status}: ${text}`);
  }
  return response.json();
}

function renderTraceFromBackend(trace) {
  traceEl.innerHTML = "";
  let iteration = 0;
  let currentCard = null;

  for (const step of trace || []) {
    if (step.type === "query") {
      iteration += 1;
      currentCard = createIterationCard(iteration);
    }
    if (!currentCard) {
      currentCard = createIterationCard(iteration || 1);
    }
    appendIterationRow(currentCard, step.title || "Step", step.payload, mapTraceTypeToKind(step.type));
  }
}

runBtn.addEventListener("click", async () => {
  const query = queryInput.value.trim();

  if (!query) {
    finalAnswerEl.textContent = "Please enter a query.";
    reasoningChainEl.innerHTML = "";
    finalEl.textContent = "";
    return;
  }

  runBtn.disabled = true;
  traceEl.innerHTML = "";
  finalAnswerEl.textContent = "Running...";
  reasoningChainEl.innerHTML = "";
  finalEl.textContent = "";

  try {
    const payload = await runBackendAgenticLoop(query);
    renderTraceFromBackend(payload.trace);
    setFinalPanels(payload.result);
    finalEl.textContent = JSON.stringify(payload.result, null, 2);
  } catch (err) {
    finalAnswerEl.textContent = `Error: ${String(err)}`;
    reasoningChainEl.innerHTML = "";
    finalEl.textContent = "";
  } finally {
    runBtn.disabled = false;
  }
});

clearBtn.addEventListener("click", () => {
  traceEl.innerHTML = "";
  finalAnswerEl.textContent = "";
  reasoningChainEl.innerHTML = "";
  finalEl.textContent = "";
  queryInput.value = "";
});

analyzePageBtn.addEventListener("click", () => {
  finalAnswerEl.textContent = "Analyze Current Page is ready. It can be wired to tab content next.";
});

compareBtn.addEventListener("click", () => {
  queryInput.value = "Should I buy Samsung or iPhone?";
});
