"""
YouTube channel discovery + viewer-sentiment agent (Gemini + tools).

Before running:
  pip install -r requirements.txt
  Create a .env file with:
    GEMINI_API_KEY=...
    YOUTUBE_API_KEY=...   (YouTube Data API v3 key)
    GEMINI_MODEL=gemini-3.1-flash-lite-preview   (optional)

Chrome extension: load chrome_extension/ in Chrome; start the local API with:
  uvicorn extension_server:app --host 127.0.0.1 --port 8765
"""
from __future__ import annotations

from collections.abc import Callable
from google import genai
import json
import re
import os
import time
from dotenv import load_dotenv

from get_youtube_channels import get_top_youtube_channels
from youtube_channel_comments import analyze_channel_viewer_comments

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
THROTTLE_SECONDS = 10

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY not set. Create a .env file with GEMINI_API_KEY=...")

client = genai.Client(api_key=GEMINI_API_KEY)


def call_llm(prompt: str, emit: Callable[[str], None] | None = None) -> str:
    _emit = emit or print
    _emit(f"  [waiting {THROTTLE_SECONDS}s to respect rate limits...]")
    time.sleep(THROTTLE_SECONDS)
    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    return response.text


system_prompt = """You are an assistant for YouTube discovery and audience tone. You have two tools.

Tool 1 — get_top_youtube_channels(query: str, max_pages: int = 2) -> str
  Searches YouTube for channels matching `query`, scores them, returns JSON with up to 5 channels.
  Each channel: title, channel_id, url, subscribers, views, videos, score.
  max_pages (default 2) is how many search pages to pull (1–10 reasonable).

Tool 2 — analyze_channel_viewer_sentiment(channel_link: str, top_videos: int = 5, comments_per_video: int = 20) -> str
  Takes a channel URL (e.g. https://www.youtube.com/@handle or /channel/UC…) or a UC… id.
  Fetches the channel's top videos by view count (up to top_videos), collects top-level comments
  (up to comments_per_video per video), returns JSON: channel_title, channel_url, videos_analyzed
  (each with title, url, sample_comments), collated_comment_text, and a note about bias.
  Your job after this tool: write a clear "what viewers seem to say" summary from those comments only
  (themes, praise, complaints, memes, requests — no inventing beyond the samples).

You must respond with ONLY JSON — no markdown fences around the whole message, no extra text:

To call a tool:
{"tool_name": "<get_top_youtube_channels|analyze_channel_viewer_sentiment>", "tool_arguments": {...}}

For the final reply:
{"answer": "<formatted string; use \\n for newlines>"}

Final answer formatting:
- If the user only asked for channel discovery (tool 1): intro sentence, blank line, numbered list with
  [Channel Title](url) using exact urls from JSON, stats on indented lines, then "Why these picks".
- If the user only asked about sentiment / what people say (tool 2): intro, blank line, section
  **What viewers say** with 2–5 sentences synthesizing comment samples; optional short bullets; mention
  videos you drew from (titles or links from JSON only). If comments were empty/disabled, say so honestly.
- If you used both tools: include both sections in one answer in a sensible order.
- If any tool returned {"error": ...}, explain it without fabricating data.

Rules:
- Use tool 1 for "find channels about …", discovery, comparisons of channels by topic.
- Use tool 2 when the user gives a channel link/id or asks what viewers think, audience reception, vibe, etc.
- You may call tools in sequence (e.g. find channels then analyze one link from the results).
- Never invent channel URLs or comment quotes; only use strings present in tool JSON.
"""


def get_top_youtube_channels_tool(query: str, max_pages: int = 2) -> str:
    try:
        max_pages = int(max_pages)
        max_pages = max(1, min(max_pages, 10))
    except (TypeError, ValueError):
        max_pages = 2
    try:
        rows = get_top_youtube_channels(query, max_pages=max_pages)
        return json.dumps({"channels": rows})
    except Exception as e:
        return json.dumps({"error": str(e)})


def analyze_channel_viewer_sentiment_tool(
    channel_link: str,
    top_videos: int = 5,
    comments_per_video: int = 20,
) -> str:
    try:
        top_videos = int(top_videos)
        top_videos = max(1, min(top_videos, 10))
    except (TypeError, ValueError):
        top_videos = 5
    try:
        comments_per_video = int(comments_per_video)
        comments_per_video = max(1, min(comments_per_video, 50))
    except (TypeError, ValueError):
        comments_per_video = 20
    try:
        payload = analyze_channel_viewer_comments(
            channel_link,
            top_videos=top_videos,
            comments_per_video=comments_per_video,
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
