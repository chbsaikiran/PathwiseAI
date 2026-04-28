"""
Local API for the PathwiseAI Chrome extension.

Run from this folder (with .env configured):
  pip install -r requirements.txt
  uvicorn extension_server:app --host 127.0.0.1 --port 8765

Then load the chrome_extension folder in Chrome (Developer mode → Load unpacked).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

_ROOT = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("agent_module", _ROOT / "10_full_agent.py")
if _spec is None or _spec.loader is None:
    raise RuntimeError("Cannot load 10_full_agent.py")
_agent_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_agent_mod)
run_agent = _agent_mod.run_agent

app = FastAPI(title="PathwiseAI Extension API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000)


class RunResponse(BaseModel):
    ok: bool
    answer: str | None = None
    logs: list[str] = []
    error: str | None = None


@app.get("/", response_class=HTMLResponse)
def root():
    return """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>PathwiseAI API</title></head>
<body style="font-family:system-ui,sans-serif;max-width:42rem;margin:2rem auto;padding:0 1rem;">
  <h1>PathwiseAI extension API</h1>
  <p>This server powers the Chrome extension. There is no web app here.</p>
  <ul>
    <li><code>GET /api/health</code> — health check</li>
    <li><code>POST /api/run</code> — body <code>{"prompt":"..."}</code></li>
  </ul>
  <p>Run the extension popup and keep the default base URL <code>http://127.0.0.1:8765</code>.</p>
</body></html>"""


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/run", response_model=RunResponse)
def run(body: RunRequest):
    logs: list[str] = []
    try:
        answer = run_agent(body.prompt.strip(), verbose=False, logs=logs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    if answer is None:
        return RunResponse(ok=False, answer=None, logs=logs, error="Agent did not produce a final answer.")
    return RunResponse(ok=True, answer=answer, logs=logs, error=None)
