# PathwiseAI Schema

Last updated: 2026-04-25

This file is the canonical project context document for PathwiseAI. Keep it current as code evolves. The goal is to help new chat sessions quickly understand architecture, behavior, contracts, and constraints.

## 1) Project Identity

- Project name: `PathwiseAI`
- Core purpose: AI-assisted YouTube channel discovery + audience sentiment summarization
- Primary UX: Chrome extension popup (Manifest V3) backed by a local FastAPI server
- Execution model: Extension sends user prompt to localhost API; Python agent orchestrates Gemini + YouTube tools

## 2) Current Feature Set

- Discover top channels for a topic
  - Uses query-driven channel search and ranking
  - Applies description-based relevance filtering (channel description must match query text/terms)
  - Optional **locale bias** on YouTube `search.list`: `relevanceLanguage` (ISO 639-1) and `regionCode` (ISO 3166-1 alpha-2), from tool args and/or env defaults
- Analyze what viewers say about a specific channel
  - Resolves channel from URL/handle/channel ID
  - Fetches top videos (by view-count ordering from search), using the same locale parameters on video search
  - Samples top-level comments and synthesizes themes
- Extension UX behavior
  - Prompt input + run action
  - Logs and answer persisted in `chrome.storage.local`
  - Background service worker support with popup fallback
  - Data remains until user clicks clear

## 3) Agent Tooling (Current Truth)

The agent exposes exactly **two** tools:

1. `get_top_youtube_channels`
2. `analyze_channel_viewer_sentiment`

Optional tool arguments (snake_case in JSON `tool_arguments`):

- `relevance_language`: ISO 639-1 two-letter language code (e.g. `hi`, `en`, `te`)
- `region_code`: ISO 3166-1 alpha-2 region code (e.g. `IN`, `US`)

If omitted, values fall back to `YOUTUBE_RELEVANCE_LANGUAGE` / `YOUTUBE_REGION_CODE` in `.env` (may be unset).

Important: A previous combined tool (`discover_channels_and_top_audience`) was removed and should remain absent unless explicitly reintroduced.

## 4) High-Level Architecture

### Components

- `10_full_agent.py`
  - Agent loop
  - Gemini invocation
  - JSON-only tool-call protocol
  - Tool registry and wrappers
- `get_youtube_channels.py`
  - Channel search + stats retrieval + ranking
  - Description-match filter against user query
- `youtube_channel_comments.py`
  - Channel resolution (`/channel/UC...`, `/@handle`, or UC ID)
  - Top videos lookup
  - Comment extraction/sample collation
- `youtube_http.py`
  - Shared YouTube API GET helper with retry/backoff for transient/rate-limit failures
- `extension_server.py`
  - FastAPI endpoints for extension
  - Loads and calls `run_agent(...)`
- `chrome_extension/*`
  - MV3 extension: popup UI, service worker, local storage persistence

### Runtime data flow

1. User enters prompt in extension popup.
2. Extension posts to local API (`/api/run`).
3. FastAPI calls Python agent (`run_agent`).
4. Agent sends prompt to Gemini.
5. Gemini returns JSON tool call(s).
6. Tool wrapper invokes YouTube helper(s), returns JSON result.
7. Gemini returns final JSON answer.
8. API responds with answer + logs; extension persists and renders.

## 5) API Contracts

### FastAPI endpoints (`extension_server.py`)

- `GET /`
  - Human-readable info page
- `GET /favicon.ico`
  - Returns 204 to avoid browser 404 noise
- `GET /api/health`
  - Returns `{ "ok": true }`
- `POST /api/run`
  - Request body: `{ "prompt": "..." }`
  - Response shape:
    - success: `{ ok: true, answer: string, logs: string[], error: null }`
    - failure: `{ ok: false, answer: null|string, logs: string[], error: string }`

## 6) Environment & Configuration

Required environment variables (in `.env`):

- `GEMINI_API_KEY`
- `YOUTUBE_API_KEY`

Optional:

- `GEMINI_MODEL` (default currently `gemini-3.1-flash-lite-preview`)
- `GEMINI_THROTTLE_SECONDS` (default currently `12`)
- `YOUTUBE_RELEVANCE_LANGUAGE` (e.g. `hi`, `en`, `te`) — default language bias for YouTube `search.list` when tools omit `relevance_language`
- `YOUTUBE_REGION_CODE` (e.g. `IN`, `US`) — default region bias for YouTube `search.list` when tools omit `region_code`

Operational note:
- Increase `GEMINI_THROTTLE_SECONDS` when seeing Gemini 503/rate-limit bursts.
- Locale parameters **bias** search results; they do not strictly guarantee every channel’s primary language.

## 7) YouTube Retrieval & Ranking Logic

### Channel discovery (`get_youtube_channels.py`)

- Search endpoint: YouTube `search.list` with `type=channel`
- Search may include `relevanceLanguage` + `regionCode` when configured (tool args and/or env), via `youtube_locale.py`
- Fetch details: `channels.list` (`snippet,statistics`)
- Relevance filter:
  - Description must match either:
    - full query substring, or
    - any parsed query term
- Additional quality filters:
  - minimum subscribers threshold
  - minimum video count threshold
- Score (log-normalized weighted formula):
  - subscribers weight 0.6
  - views weight 0.3
  - videos weight 0.1
- Returns top 5 scored channels

### Viewer sentiment tool (`youtube_channel_comments.py`)

- Video discovery uses `search.list` with optional `relevanceLanguage` + `regionCode` (same mechanism as channel discovery)
- Channel resolution supports:
  - direct UC channel ID
  - `/channel/{UC...}` URL
  - `/@handle` URL
  - `channel_id` query parameter in URL
- Top videos source: `search.list` ordered by `viewCount`
- Comments source: `commentThreads.list`, top-level comments, relevance order
- Handles `commentsDisabled`/`forbidden` safely
- Returns structured payload:
  - channel metadata
  - `search_locale` echoing effective `relevance_language` / `region_code` used for video search
  - analyzed videos
  - sample comments per video
  - collated text summary input for LLM
  - caution note about sample bias

## 8) Reliability / Rate-Limit Strategy

- Gemini
  - fixed base throttle between calls
  - retry with exponential backoff for retryable failures (e.g., 429/503 patterns)
- YouTube
  - shared HTTP helper with retry/backoff and retryable error detection
  - bounded request volumes in tool defaults and limits

## 9) Extension Behavior (MV3)

- Popup UI fields:
  - server base URL
  - prompt
  - run / clear actions
- Storage keys:
  - base URL and agent state persisted in `chrome.storage.local`
- Service worker:
  - used for background execution when active
- Fallback:
  - popup can run direct fetch path if worker message receiver is unavailable
- UX expectation:
  - closing popup should not lose completed results
  - results persist until user clears logs

## 10) Important Project Constraints

- Keep secrets local; never expose API keys in extension bundle.
- Preserve JSON-only tool protocol in agent prompt/response parsing.
- Do not reintroduce removed tool names without deliberate migration.
- Keep README and this schema in sync when behavior changes.

## 11) Known Files (Core)

- `10_full_agent.py`
- `get_youtube_channels.py`
- `youtube_channel_comments.py`
- `youtube_locale.py`
- `youtube_http.py`
- `extension_server.py`
- `chrome_extension/manifest.json`
- `chrome_extension/background.js`
- `chrome_extension/popup.js`
- `chrome_extension/popup.html`
- `chrome_extension/popup.css`
- `requirements.txt`
- `README.md`
- `schema.md` (this file)

## 12) Update Checklist (When Project Changes)

When any feature/contract/flow changes, update this file with:

1. Tool list and tool contracts
2. API endpoints and request/response shape changes
3. Env vars and defaults
4. Retrieval/ranking/comment logic updates
5. Extension behavior changes (storage keys, background flow)
6. Reliability/backoff strategy changes
7. New files added / obsolete files removed

## 13) Quick Start (Reference)

1. Install deps:
   - `pip install -r requirements.txt`
2. Configure `.env` with Gemini + YouTube keys
3. Run local API:
   - `uvicorn extension_server:app --host 127.0.0.1 --port 8765`
4. Load extension folder in Chrome (`chrome://extensions` -> Load unpacked)
5. Use popup to run prompts

## 14) Notes for Future Sessions

- Treat this file as project memory.
- If behavior in code disagrees with this file, code is source of truth, then update this file immediately.
- Prefer additive updates with clear section edits rather than vague summaries.
