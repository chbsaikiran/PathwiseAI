/**
 * Runs /api/run in the service worker so closing the popup does not cancel the request.
 * Results are written to chrome.storage.local until the user clears them.
 */

const STORAGE_AGENT = "agentState";

/** Wake the service worker as soon as something connects (popup opens a port first). */
chrome.runtime.onConnect.addListener((port) => {
  port.onDisconnect.addListener(() => {});
});

function formatHttpDetail(data) {
  let detail = data.detail ?? data.message ?? "Request failed";
  if (Array.isArray(detail)) {
    detail = detail
      .map((d) => (typeof d === "object" && d.msg ? d.msg : JSON.stringify(d)))
      .join("\n");
  }
  return typeof detail === "string" ? detail : JSON.stringify(detail, null, 2);
}

async function handleRun(baseUrl, prompt) {
  const base = (baseUrl || "").replace(/\/$/, "");
  const { [STORAGE_AGENT]: existing } = await chrome.storage.local.get(STORAGE_AGENT);
  if (existing?.status === "running") {
    return;
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
      return;
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
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "RUN_AGENT") {
    const baseUrl = msg.baseUrl;
    const prompt = (msg.prompt || "").trim();
    if (!prompt) {
      sendResponse({ ok: false, error: "Empty prompt" });
      return false;
    }

    (async () => {
      try {
        const { [STORAGE_AGENT]: existing } = await chrome.storage.local.get(STORAGE_AGENT);
        if (existing?.status === "running") {
          sendResponse({ ok: false, error: "A run is already in progress." });
          return;
        }
        await handleRun(baseUrl, prompt);
        sendResponse({ ok: true });
      } catch (e) {
        sendResponse({ ok: false, error: e instanceof Error ? e.message : String(e) });
      }
    })();

    return true;
  }

  if (msg.type === "CLEAR_AGENT") {
    chrome.storage.local.remove([STORAGE_AGENT], () => {
      if (chrome.runtime.lastError) {
        sendResponse({ ok: false, error: chrome.runtime.lastError.message });
        return;
      }
      sendResponse({ ok: true });
    });
    return true;
  }

  return false;
});
