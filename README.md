# PathwiseAI

A small **YouTube channel discovery agent** built for learning: it uses **Google Gemini** with tools that call the **YouTube Data API v3** (channel search, comment sampling, and a **combined** “top channels + audience read on #1” path to reduce API bursts). You can run it as a **CLI script**, or through a **Chrome extension** that talks to a **local FastAPI server** (so API keys stay on your machine).

## What is in this folder

| Item | Role |
|------|------|
| `10_full_agent.py` | Agent loop, Gemini calls, tool wiring, optional CLI demo |
| `get_youtube_channels.py` | `get_top_youtube_channels(query, max_pages)` — search + stats + scoring |
| `youtube_channel_comments.py` | Comment samples for a channel’s top videos (by views) |
| `youtube_http.py` | Shared YouTube GET with retry/backoff for 429/503 |
| `extension_server.py` | Local HTTP API for the Chrome extension (`/api/run`, `/api/health`) |
| `chrome_extension/` | Manifest V3 extension (popup UI, background service worker) |
| `requirements.txt` | Python dependencies |

## Prerequisites

- **Python 3.10+** (recommended)
- A **Gemini API key** and a **YouTube Data API v3** key

## Environment variables

Create a **`.env`** file in this directory (same level as `10_full_agent.py`). Do not commit `.env`; it is listed in `.gitignore`.

```env
GEMINI_API_KEY=your-gemini-key
YOUTUBE_API_KEY=your-youtube-data-api-key
# Optional:
# GEMINI_MODEL=gemini-3.1-flash-lite-preview
# GEMINI_THROTTLE_SECONDS=12
```

If Gemini often returns **503 / rate limit**, raise `GEMINI_THROTTLE_SECONDS` (for example `15` or `20`).

Enable the **YouTube Data API v3** for the Google Cloud project that owns `YOUTUBE_API_KEY`.

## Install Python dependencies

From this directory:

```bash
pip install -r requirements.txt
```

Using a virtual environment is recommended:

```bash
python -m venv .venv
```

On Windows:

```bash
.venv\Scripts\activate
pip install -r requirements.txt
```

On macOS or Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

## Run the agent from the terminal

This runs the sample prompt at the bottom of `10_full_agent.py` (you can edit that file to change the query):

```bash
python 10_full_agent.py
```

The script waits between Gemini calls (`THROTTLE_SECONDS`) to reduce rate-limit issues on free tiers.

## Run the Chrome extension workflow

The extension does **not** embed API keys. It sends prompts to **your computer** via a small local server that runs the same Python agent.

### 1. Start the API server

From this directory, with `.env` configured and dependencies installed:

```bash
uvicorn extension_server:app --host 127.0.0.1 --port 8765
```

Leave this terminal open while you use the extension. Opening `http://127.0.0.1:8765/` in a browser shows a short help page; the extension uses `POST /api/run` with a JSON body `{"prompt":"..."}`.

### 2. Load the extension in Chrome

1. Open Chrome and go to `chrome://extensions`.
2. Turn on **Developer mode**.
3. Click **Load unpacked** and choose the **`chrome_extension`** folder inside this project (not the parent folder).
4. After you change extension files or `manifest.json`, click **Reload** on the extension card.

### 3. Use the popup

1. Click the extension icon to open the popup.
2. Keep **Server base URL** as `http://127.0.0.1:8765` unless you changed the uvicorn port.
3. Enter a **prompt** and click **Run agent**.
4. **Logs** and the **answer** are stored in extension storage until you click **Clear logs**. A **service worker** runs the request in the background so closing the popup does not cancel an in-flight run (if the worker is active; the popup can fall back if needed).

If you use another host or port, add matching URLs under **`host_permissions`** in `chrome_extension/manifest.json`.

## Troubleshooting

- **`GEMINI_API_KEY not set`**: Add it to `.env` in the project root, or export it in the shell before running.
- **`YOUTUBE_API_KEY not set`**: Same for YouTube; the tool raises if the key is missing when the API is called.
- **Extension cannot reach the server**: Confirm uvicorn is running, the URL matches, and Windows or firewall software is not blocking localhost.
- **`Could not establish connection. Receiving end does not exist`**: Reload the extension on `chrome://extensions`. The popup tries to wake the service worker and can fall back to calling the API directly if the background script is not ready.

## License

Use and modify for your own learning; add a license file if you redistribute the project.
