# PathwiseAI

PathwiseAI is a learning project that combines a Gemini agent, YouTube Data API tools, a local FastAPI server, and a Chrome extension UI. The extension sends prompts to your local server so API keys remain on your machine.

## Current capabilities

- Discover top YouTube channels for a topic with scoring and channel links (optional **language/region** via `relevanceLanguage` + `regionCode` on YouTube search).
- Filter discovered channels by checking whether the channel description matches user query text/terms.
- Analyze audience tone for a channel by reading comments from top videos and summarizing common themes.
- Show agent logs and final answers in the extension popup, with data persisted until you clear it.

## Project files

- `10_full_agent.py`: agent loop, Gemini calls, tool dispatch, and prompt rules.
- `get_youtube_channels.py`: `get_top_youtube_channels(query, max_pages, ...)` for discovery and ranking.
- `youtube_channel_comments.py`: `analyze_channel_viewer_comments(channel_link, ...)` for comment sampling.
- `youtube_locale.py`: validates and merges `relevance_language` / `region_code` with env defaults for `search.list`.
- `youtube_http.py`: shared YouTube HTTP client with retry/backoff for 429/500/503-like failures.
- `extension_server.py`: FastAPI server used by the extension (`/api/run`, `/api/health`, `/`).
- `chrome_extension/`: Manifest V3 extension popup + background service worker.
- `requirements.txt`: Python dependencies.

## Agent tools (latest)

The agent currently exposes exactly two tools:

1. `get_top_youtube_channels` — optional `relevance_language` (ISO 639-1, e.g. `hi`) and `region_code` (ISO 3166-1 alpha-2, e.g. `IN`), or set defaults in `.env`.
2. `analyze_channel_viewer_sentiment` — same locale args apply to the **video search** step used to pick top videos.

There is no combined third tool now. For requests like "top channels and what people say about the top one", the agent should call tool 1 first, then tool 2 on the top channel URL.

## Environment variables

Create a `.env` file in this directory:

```env
GEMINI_API_KEY=your-gemini-key
YOUTUBE_API_KEY=your-youtube-data-api-key
# Optional:
# GEMINI_MODEL=gemini-3.1-flash-lite-preview
# GEMINI_THROTTLE_SECONDS=12
# YOUTUBE_RELEVANCE_LANGUAGE=hi
# YOUTUBE_REGION_CODE=IN
```

Notes:
- Increase `GEMINI_THROTTLE_SECONDS` (for example 15-20) if Gemini returns 503/rate-limit errors.
- Ensure YouTube Data API v3 is enabled for the project owning `YOUTUBE_API_KEY`.
- Locale env vars map to YouTube `search.list` parameters `relevanceLanguage` and `regionCode`. They bias results toward a language/region; they are not a hard guarantee every channel is monolingual.

## Installation

```bash
pip install -r requirements.txt
```

Optional virtual environment:

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
pip install -r requirements.txt
```

macOS/Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

## Run from terminal

```bash
python 10_full_agent.py
```

Edit the sample prompt at the bottom of `10_full_agent.py` if needed.

## Run with Chrome extension

### 1) Start local API server

```bash
uvicorn extension_server:app --host 127.0.0.1 --port 8765
```

### 2) Load extension

1. Open `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked** and select `chrome_extension`
4. Click **Reload** after extension code/manifest changes

### 3) Use popup

- Keep base URL as `http://127.0.0.1:8765` (unless you changed server host/port).
- Enter prompt and click **Run agent**.
- Logs and answer persist in `chrome.storage.local` until **Clear logs**.
- Background worker handles runs when available; popup has fallback behavior if worker is not ready.

If you use a different host/port, update `host_permissions` in `chrome_extension/manifest.json`.

## Troubleshooting

- `GEMINI_API_KEY not set`: put it in `.env` or export in shell.
- `YOUTUBE_API_KEY not set`: same; the tools will fail without it.
- Extension cannot reach server: verify uvicorn is running and base URL matches.
- "Receiving end does not exist": reload extension on `chrome://extensions`.
- YouTube quota/rate spikes: retry logic is built in; reduce prompt frequency or lower tool load (`top_videos`, `comments_per_video`) if needed.

## License

Use and modify for learning. Add a license file before redistribution.
