"""
YouTube channel discovery + viewer-sentiment agent (Gemini + tools).

Before running:
  pip install -r requirements.txt
  Create a .env file with:
    GEMINI_API_KEY=...
    YOUTUBE_API_KEY=...   (YouTube Data API v3 key)
    GEMINI_MODEL=gemini-3.1-flash-lite-preview   (optional)
    GEMINI_THROTTLE_SECONDS=12   (optional; seconds between Gemini calls, reduces 503 bursts)
    YOUTUBE_RELEVANCE_LANGUAGE=hi   (optional; ISO 639-1, e.g. en, hi, te)
    YOUTUBE_REGION_CODE=IN          (optional; ISO 3166-1 alpha-2, e.g. IN, US)

Chrome extension: load chrome_extension/ in Chrome; start the local API with:
  uvicorn extension_server:app --host 127.0.0.1 --port 8765
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collections.abc import Callable
from google import genai
import json
import re
import os
import time
from dotenv import load_dotenv

from get_youtube_channels import get_top_youtube_channels
from youtube_channel_comments import analyze_channel_viewer_comments
from youtube_locale import effective_search_locale

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
# Slightly higher default + env override reduces Gemini 503 "too many requests" bursts.
THROTTLE_SECONDS = float(os.getenv("GEMINI_THROTTLE_SECONDS", "12"))

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY not set. Create a .env file with GEMINI_API_KEY=...")

client = genai.Client(api_key=GEMINI_API_KEY)


def _gemini_retryable(exc: BaseException) -> bool:
    text = (repr(exc) + " " + str(exc)).lower()
    return any(
        k in text
        for k in (
            "503",
            "429",
            "resource exhausted",
            "unavailable",
            "overloaded",
            "deadline exceeded",
            "500",
            "internal error",
            "too many requests",
        )
    )


def call_llm(prompt: str, emit: Callable[[str], None] | None = None) -> str:
    _emit = emit or print
    max_attempts = 6
    last_exc: BaseException | None = None
    for attempt in range(max_attempts):
        if attempt == 0:
            _emit(f"  [waiting {THROTTLE_SECONDS}s to respect rate limits...]")
            time.sleep(THROTTLE_SECONDS)
        else:
            backoff = min(6.0 * (2 ** (attempt - 1)), 120.0)
            _emit(f"  [Gemini busy or rate-limited; waiting {backoff:.0f}s (retry {attempt + 1}/{max_attempts})...]")
            time.sleep(backoff)
        try:
            response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
            return response.text
        except BaseException as e:
            last_exc = e
            if attempt < max_attempts - 1 and _gemini_retryable(e):
                continue
            raise
    assert last_exc is not None
    raise last_exc


system_prompt = """You are an assistant for YouTube discovery and audience tone. You have two tools.

Tool 1 — get_top_youtube_channels(query: str, max_pages: int = 2, relevance_language: optional, region_code: optional) -> str
  Searches YouTube for channels matching `query`, scores them, returns JSON with up to 5 channels.
  Each channel: title, channel_id, url, subscribers, views, videos, score.
  max_pages (default 2) is how many search pages to pull (1–10 reasonable).
  relevance_language: ISO 639-1 two letters (e.g. "hi", "en", "te") — passed to YouTube search as relevanceLanguage.
  region_code: ISO 3166-1 alpha-2 (e.g. "IN", "US") — passed as regionCode.
  If omitted, values come from env YOUTUBE_RELEVANCE_LANGUAGE and YOUTUBE_REGION_CODE (can be unset for global results).
  When the user asks for channels in a specific language/region, pass these arguments.

Tool 2 — analyze_channel_viewer_sentiment(channel_link: str, top_videos: int = 4, comments_per_video: int = 12, relevance_language: optional, region_code: optional) -> str
  Takes a channel URL (e.g. https://www.youtube.com/@handle or /channel/UC…) or a UC… id.
  Fetches top videos by view count (search order), collects top-level comments per video.
  Uses the same relevance_language / region_code rules as tool 1 for the video search step.
  Returns JSON: channel_title, channel_url, search_locale, videos_analyzed (title, url, sample_comments),
  collated_comment_text, note. Summarize viewer themes only from that JSON.

You must respond with ONLY JSON — no markdown fences around the whole message, no extra text:

To call a tool:
{"tool_name": "<get_top_youtube_channels|analyze_channel_viewer_sentiment>", "tool_arguments": {...}}

For the final reply:
{"answer": "<formatted string; use \\n for newlines>"}

Final answer formatting:
- Discovery only (tool 1): intro, blank line, numbered [Title](url) with exact urls, stats lines, "Why these picks".
- Sentiment only (tool 2): intro, **What viewers say** section (2–5 sentences + optional bullets from samples only).
- Combined discovery + top-channel audience: use tool 1 first, then tool 2 on the top-ranked channel URL.
  In the final answer, list ALL channels first, then add **What viewers say about [top channel title]**.
- If any tool returned {"error": ...}, explain it without fabricating data.

Rules:
- For "find channels … and what people say about the top one": use tool 1, then tool 2 on rank #1 channel URL.
- Use tool 1 alone when the user only wants a channel list. Use tool 2 alone when they already give a link/handle.
- Never invent channel URLs or comment quotes; only use strings present in tool JSON.
"""


def get_top_youtube_channels_tool(
    query: str,
    max_pages: int = 2,
    relevance_language: str | None = None,
    region_code: str | None = None,
) -> str:
    try:
        max_pages = int(max_pages)
        max_pages = max(1, min(max_pages, 10))
    except (TypeError, ValueError):
        max_pages = 2
    try:
        lang_eff, reg_eff = effective_search_locale(relevance_language, region_code)
        rows = get_top_youtube_channels(
            query,
            max_pages=max_pages,
            relevance_language=relevance_language,
            region_code=region_code,
        )
        return json.dumps(
            {
                "channels": rows,
                "search_locale": {"relevance_language": lang_eff, "region_code": reg_eff},
            }
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


def analyze_channel_viewer_sentiment_tool(
    channel_link: str,
    top_videos: int = 4,
    comments_per_video: int = 12,
    relevance_language: str | None = None,
    region_code: str | None = None,
) -> str:
    try:
        top_videos = int(top_videos)
        top_videos = max(1, min(top_videos, 10))
    except (TypeError, ValueError):
        top_videos = 4
    try:
        comments_per_video = int(comments_per_video)
        comments_per_video = max(1, min(comments_per_video, 50))
    except (TypeError, ValueError):
        comments_per_video = 12
    try:
        payload = analyze_channel_viewer_comments(
            channel_link,
            top_videos=top_videos,
            comments_per_video=comments_per_video,
            relevance_language=relevance_language,
            region_code=region_code,
        )
        return json.dumps(payload)
    except Exception as e:
        return json.dumps({"error": str(e)})


tools = {
    "get_top_youtube_channels": get_top_youtube_channels_tool,
    "analyze_channel_viewer_sentiment": analyze_channel_viewer_sentiment_tool,
}


def parse_llm_response(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Could not parse LLM response: {text[:200]}")


def run_agent(
    user_query: str,
    max_iterations: int = 8,
    verbose: bool = True,
    logs: list[str] | None = None,
) -> str | None:
    def emit(msg: str) -> None:
        if logs is not None:
            logs.append(msg)
        elif verbose:
            print(msg)

    emit(f"\n{'='*60}\n  User: {user_query}\n{'='*60}")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_query},
    ]

    for iteration in range(max_iterations):
        emit(f"\n--- Iteration {iteration + 1} ---")

        prompt = ""
        for msg in messages:
            if msg["role"] == "system":
                prompt += msg["content"] + "\n\n"
            elif msg["role"] == "user":
                prompt += f"User: {msg['content']}\n\n"
            elif msg["role"] == "assistant":
                prompt += f"Assistant: {msg['content']}\n\n"
            elif msg["role"] == "tool":
                prompt += f"Tool Result: {msg['content']}\n\n"

        response_text = call_llm(prompt, emit=emit)
        emit(f"LLM: {response_text.strip()}")

        try:
            parsed = parse_llm_response(response_text)
        except (ValueError, json.JSONDecodeError) as e:
            emit(f"Parse error: {e}\nAsking LLM to retry...")
            messages.append({"role": "assistant", "content": response_text})
            messages.append(
                {
                    "role": "user",
                    "content": "Please respond with valid JSON only. No markdown, no extra text.",
                }
            )
            continue

        if "answer" in parsed:
            emit(f"\n{'='*60}\n  Agent Answer: {parsed['answer']}\n{'='*60}")
            return parsed["answer"]

        if "tool_name" in parsed:
            tool_name = parsed["tool_name"]
            tool_args = parsed.get("tool_arguments", {})
            emit(f"→ Calling tool: {tool_name}({tool_args})")

            if tool_name not in tools:
                error_msg = json.dumps(
                    {"error": f"Unknown tool: {tool_name}. Use: {list(tools.keys())}"}
                )
                emit(f"→ Error: {error_msg}")
                messages.append({"role": "assistant", "content": response_text})
                messages.append({"role": "tool", "content": error_msg})
                continue

            tool_result = tools[tool_name](**tool_args)
            preview = tool_result[:500] + ("..." if len(tool_result) > 500 else "")
            emit(f"→ Result: {preview}")
            messages.append({"role": "assistant", "content": response_text})
            messages.append({"role": "tool", "content": tool_result})

    emit("\nMax iterations reached. Agent could not complete the task.")
    emit(f"\n{'='*60}\nFull conversation history:\n{'='*60}")
    for i, msg in enumerate(messages):
        emit(f"[{i}] {msg['role']}: {msg['content'][:100]}...")
    return None


if __name__ == "__main__":
    print("\n" + "=" * 60 + "\n  YouTube channel agent\n" + "=" * 60)
    run_agent("Find top YouTube channels about old kishore kumar songs.")
