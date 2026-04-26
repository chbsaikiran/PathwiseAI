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
- `mcp_server.py`: MCP (FastMCP) stdio server — YouTube tools, sandbox file tools, and `build_prefab_source` for Prefab app generation.
- `mcp_client.py`: asyncio agent loop — Gemini chooses one `FUNCTION_CALL:` per turn until `FINAL_ANSWER:`.
- `channels_bubble_prefab.py`: parses `sandbox/top_channels.txt`, calls Gemini to draft a Prefab app (or uses a local fallback), writes `generated_channels_bubble.py`, optional `prefab serve` + file watch.

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

## MCP workflow (server + client + sandbox)

The repo includes an **MCP stdio** stack: `mcp_server.py` registers tools with FastMCP; `mcp_client.py` connects over stdio, lists tools, and runs a **Gemini** loop where each model reply is exactly one line: either `FUNCTION_CALL: {"tool_name": "...", "tool_arguments": {...}}` or `FINAL_ANSWER: ...`.

### `mcp_server.py` (tools)

All file paths for `write_file` / `read_file` / `edit_file` are **sandbox-relative** (under `sandbox/`), with `..` and absolute paths rejected.

| Tool | Role |
|------|------|
| `get_top_youtube_channels` | YouTube discovery; returns JSON with `channels` (title, url, subscribers, views, videos, score) and `search_locale`. |
| `analyze_channel_viewer_sentiment` | Comment sampling + structured payload for a channel URL or id. |
| `write_file` / `read_file` / `edit_file` | Sandbox text I/O and replace. |
| `build_prefab_source` | Reads a sandbox dump (default `top_channels.txt`), parses rows via `channels_bubble_prefab.parse_top_channels_file`, runs `build_prefab_source()` from that module, compiles the result, and writes a **project-root** Python file (default `generated_channels_bubble.py`). |

Run the server (stdio):

```bash
python mcp_server.py
```

Or with the MCP CLI: `mcp run mcp_server.py` (see `requirements.txt` for `mcp[cli]`).

### `mcp_client.py` (agent)

- Starts `python mcp_server.py` as a subprocess and opens a `ClientSession`.
- Injects a **system prompt** that describes the current tool list and rules (canonical channel dump format, `read_file` verification, then `build_prefab_source` with `input_path` / `output_filename`, and `FINAL_ANSWER` mentioning `sandbox/top_channels.txt` and the generated `.py`).
- **Stability hook:** after `get_top_youtube_channels`, the client parses the tool JSON, formats a **canonical** multi-block text dump (`format_channels_dump`), and calls `write_file` for `top_channels.txt` so downstream steps do not depend on the model’s free-form file layout.
- **Configurable task:** edit the `task = (...)` string at the bottom of `mcp_client.py` (query, locale, whether you want a chart, etc.).

```bash
python mcp_client.py
```

Env: `GEMINI_API_KEY` (and `YOUTUBE_API_KEY` on the server for YouTube tools). Optional tuning: `MODEL`, `MAX_ITERATIONS`, `LLM_SLEEP_SECONDS`, `LLM_TIMEOUT` in `mcp_client.py`.

## Prefab charts from `top_channels.txt` (`channels_bubble_prefab.py`)

This script is both a **CLI** and the **library** used by the MCP `build_prefab_source` tool.

### Parsing

`parse_top_channels_file` accepts several dump shapes: single-line comma or pipe formats, and a **multi-line block** per channel (`1. Title`, then `URL:`, `Subscribers:`, `Views:`, `Videos:`, `Score:`). That matches the canonical text produced by `mcp_client.py` after `get_top_youtube_channels`.

### Generation

- **`build_prefab_source(rows)`** — If `GEMINI_API_KEY` is set and `google.genai` is available, asks Gemini for a full Prefab app source string; otherwise uses **`_build_prefab_source_fallback`**. Output is syntax-checked with `compile()`; invalid LLM patterns (e.g. `@app.page`) are rejected and the fallback is used.
- **`generate_app_from_input`** — Parses the file, builds source, applies a final validator pass, writes **`generated_channels_bubble.py`** at the repo root.

### CLI behavior

```bash
python channels_bubble_prefab.py --no-serve   # write generated_channels_bubble.py only
python channels_bubble_prefab.py               # generate + run `prefab serve` (logs in prefab_channels_bubble.log)
```

With serve mode, the script watches **`sandbox/top_channels.txt`** mtime and regenerates when it changes. On Windows, stopping the child `prefab` process uses a process-group + `taskkill` fallback so **Ctrl+C** is more reliable than running `prefab serve` alone.

### Viewing the chart

```bash
prefab serve generated_channels_bubble.py
```

Windows: if `prefab` crashes on Rich Unicode output, use UTF-8 in the console (`chcp 65001` or `PYTHONUTF8=1`) or rely on `python channels_bubble_prefab.py`, which logs to a file.

The generated bubble chart is intended to plot **subscribers** (x), **views** (y), and **videos** as bubble size (`ScatterChart` `z_axis`), with a short legend under the card when the template includes it.
