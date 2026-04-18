const DEFAULT_BASE = "http://127.0.0.1:8765";
const STORAGE_AGENT = "agentState";

function $(id) {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Missing #${id}`);
  return el;
}

function escapeHtml(s) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Very small markdown subset: [text](url), **bold**, newlines */
function formatAnswerMarkdown(text) {
  let html = escapeHtml(text);
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(
    /\[([^\]]+)\]\((https?:[^)\s]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
  );
  html = html.replace(/\n/g, "<br />");
  return html;
}

function formatHttpDetail(data) {
  let detail = data.detail ?? data.message ?? "Request failed";
  if (Array.isArray(detail)) {
    detail = detail
      .map((d) => (typeof d === "object" && d.msg ? d.msg : JSON.stringify(d)))
      .join("\n");
  }
  return typeof detail === "string" ? detail : JSON.stringify(detail, null, 2);
}

/** Wake MV3 service worker before sendMessage (avoids "Receiving end does not exist"). */
function wakeServiceWorker() {
  try {
    const port = chrome.runtime.connect({ name: "pathwise-wake" });
    port.onDisconnect.addListener(() => {});
  } catch {
    /* ignore */
  }
}

/**
 * Same network + storage logic as background.js, for when the service worker is not up.
 */
async function runAgentDirectFetch(baseUrl, prompt) {
  const base = (baseUrl || "").replace(/\/$/, "");
  const { [STORAGE_AGENT]: existing } = await chrome.storage.local.get(STORAGE_AGENT);
  if (existing?.status === "running") {
    return { ok: false, error: "A run is already in progress." };
  }

  await chrome.storage.local.set({
    [STORAGE_AGENT]: {
      status: "running",
      logs: "Connecting to server...\n",
      answer: "",
      error: "",
      prompt,
      updatedAt: Date.now(),
    },
  });

  try {
    const res = await fetch(`${base}/api/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      const logs = formatHttpDetail(data);
      await chrome.storage.local.set({
        [STORAGE_AGENT]: {
          status: "error",
          logs,
          answer: "",
          error: `Server error (${res.status})`,
          prompt,
          updatedAt: Date.now(),
        },
      });
      return { ok: true };
    }

    const logsText = Array.isArray(data.logs) ? data.logs.join("\n") : "";
    const ok = Boolean(data.ok);
    await chrome.storage.local.set({
      [STORAGE_AGENT]: {
        status: ok ? "done" : "error",
        logs: logsText || "(no log lines returned)",
        answer: data.answer || "",
        error: ok ? "" : data.error || "No answer.",
        prompt,
        updatedAt: Date.now(),
      },
    });
    return { ok: true };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    await chrome.storage.local.set({
      [STORAGE_AGENT]: {
        status: "error",
        logs:
          "Could not reach the server.\n\n" +
          "Start it from the project folder:\n" +
          "  uvicorn extension_server:app --host 127.0.0.1 --port 8765\n\n" +
          `Error: ${msg}`,
        answer: "",
        error: "Connection failed — is the server running?",
        prompt,
        updatedAt: Date.now(),
      },
    });
    return { ok: true };
  }
}

async function loadSavedUrl() {
  const { baseUrl } = await chrome.storage.local.get(["baseUrl"]);
  $("baseUrl").value = typeof baseUrl === "string" && baseUrl ? baseUrl : DEFAULT_BASE;
}

async function saveUrl() {
  const v = $("baseUrl").value.trim() || DEFAULT_BASE;
  await chrome.storage.local.set({ baseUrl: v });
}

function setStatus(msg, isError = false) {
  const el = $("status");
  el.textContent = msg;
  el.style.color = isError ? "#f38ba8" : "#f9e2af";
}

function setLogsText(text) {
  const el = $("logs");
  el.textContent = text;
  el.scrollTop = el.scrollHeight;
}

function setAnswerFromState(state) {
  const el = $("answer");
  if (state.answer) {
    el.innerHTML = formatAnswerMarkdown(state.answer);
  } else if (state.error) {
    el.textContent = state.error;
  } else {
    el.innerHTML = "";
  }
}

function applyAgentState(state) {
  if (!state) {
    setLogsText("");
    $("answer").innerHTML = "";
    setStatus("");
    $("runBtn").disabled = false;
    return;
  }

  setLogsText(state.logs || "");
  setAnswerFromState(state);

  if (state.status === "running") {
    setStatus("Running… You can close this popup; reopen anytime to see logs.");
    $("runBtn").disabled = true;
  } else if (state.status === "error") {
    setStatus(state.error || "Error.", true);
    $("runBtn").disabled = false;
  } else if (state.status === "done") {
    setStatus("Done.");
    $("runBtn").disabled = false;
  } else {
    $("runBtn").disabled = false;
  }

  if (state.prompt) {
    $("prompt").value = state.prompt;
  }
}

async function refreshFromStorage() {
  const { agentState } = await chrome.storage.local.get([STORAGE_AGENT]);
  applyAgentState(agentState);
}

function sendMessageAsync(message) {
  return new Promise((resolve) => {
    try {
      chrome.runtime.sendMessage(message, (response) => {
        const err = chrome.runtime.lastError;
        if (err) {
          resolve({ __error: err.message });
          return;
        }
        resolve(response);
      });
    } catch (e) {
      resolve({ __error: e instanceof Error ? e.message : String(e) });
    }
  });
}

async function runAgent() {
  const base = ($("baseUrl").value || DEFAULT_BASE).replace(/\/$/, "");
  const prompt = $("prompt").value.trim();
  if (!prompt) {
    setStatus("Enter a prompt.", true);
    return;
  }

  await saveUrl();
  wakeServiceWorker();

  $("runBtn").disabled = true;
  setStatus("Starting…");

  let response = await sendMessageAsync({ type: "RUN_AGENT", baseUrl: base, prompt });

  if (response && response.__error) {
    const m = response.__error;
    if (
      m.includes("Receiving end does not exist") ||
      m.includes("Extension context invalidated")
    ) {
      setStatus("Background not ready — running in this window (closing popup may cancel).");
      response = await runAgentDirectFetch(base, prompt);
      if (response && !response.ok && response.error) {
        setStatus(response.error, true);
      }
    } else {
      setStatus(m, true);
      $("runBtn").disabled = false;
      return;
    }
  }

  if (response && !response.ok && response.error) {
    setStatus(response.error, true);
  }

  await refreshFromStorage();
  $("runBtn").disabled = false;
}

async function clearAgent() {
  await chrome.storage.local.remove([STORAGE_AGENT]);
  setLogsText("");
  $("answer").innerHTML = "";
  setStatus("");
  $("runBtn").disabled = false;
}

document.addEventListener("DOMContentLoaded", () => {
  wakeServiceWorker();
  loadSavedUrl();
  refreshFromStorage();

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "local" || !changes[STORAGE_AGENT]) return;
    applyAgentState(changes[STORAGE_AGENT].newValue);
  });

  $("runBtn").addEventListener("click", runAgent);
  $("clearBtn").addEventListener("click", clearAgent);
});
