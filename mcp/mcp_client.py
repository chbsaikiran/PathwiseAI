"""
Agentic loop: Gemini + MCP stdio server (`mcp_server.py`).

The model calls MCP tools one at a time until it emits FINAL_ANSWER.

Run:
  python mcp_client.py

Env:
  GEMINI_API_KEY in `.env`
"""

from __future__ import annotations

import asyncio
import json
import os
from concurrent.futures import TimeoutError
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

MODEL = "gemini-3.1-flash-lite-preview"
MAX_ITERATIONS = 12
LLM_SLEEP_SECONDS = 5
LLM_TIMEOUT = 60

# ── Task selection ────────────────────────────────────────────────────────────
# Switch ACTIVE_TASK to choose which prompt the agent runs.

TASK_TOP_CHANNELS = (
    "Find top YouTube channels for the query 'CBSE Class 10 Maths' "
    "(English, region IN). Dump the full results into sandbox file top_channels.txt "
    "(include each channel's link, subscribers, views, videos uploaded, and score). "
    "Then read the file back to confirm, call build_prefab_source to generate "
    "generated_channels_bubble.py, and finish with FINAL_ANSWER."
)

TASK_VIDEO_VIEWS = (
    "Plot the top 5 videos by view count for the YouTube channel "
    "'https://www.youtube.com/@3blue1brown'. "
    "Call plot_channel_top_videos with that channel link, then give a FINAL_ANSWER "
    "that mentions generated_video_views.py and lists every video with its view and like counts."
)

ACTIVE_TASK = TASK_TOP_CHANNELS  # ← change to TASK_VIDEO_VIEWS for the video chart
# ─────────────────────────────────────────────────────────────────────────────

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


async def generate_with_timeout(prompt: str, timeout: int = LLM_TIMEOUT):
    """Run the blocking Gemini call in a thread with a timeout."""
    loop = asyncio.get_event_loop()
    return await asyncio.wait_for(
        loop.run_in_executor(
            None,
            lambda: client.models.generate_content(model=MODEL, contents=prompt),
        ),
        timeout=timeout,
    )


def describe_tools(tools) -> str:
    lines = []
    for i, t in enumerate(tools, 1):
        props = (t.inputSchema or {}).get("properties", {})
        params = ", ".join(f"{n}: {p.get('type', '?')}" for n, p in props.items()) or "no params"
        lines.append(f"{i}. {t.name}({params}) — {t.description or ''}")
    return "\n".join(lines)


def extract_channels_from_payload(payload: str) -> list[dict] | None:
    """Best-effort parse of get_top_youtube_channels tool text payload."""
    try:
        data = json.loads(payload)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    channels = data.get("channels")
    if not isinstance(channels, list):
        return None
    normalized: list[dict] = []
    for ch in channels:
        if not isinstance(ch, dict):
            continue
        normalized.append(
            {
                "title": str(ch.get("title", "")).strip(),
                "url": str(ch.get("url", "")).strip(),
                "subscribers": int(ch.get("subscribers", 0) or 0),
                "views": int(ch.get("views", 0) or 0),
                "videos": int(ch.get("videos", 0) or 0),
                "score": float(ch.get("score", 0.0) or 0.0),
            }
        )
    return normalized or None


def format_channels_dump(channels: list[dict]) -> str:
    """Canonical dump format consumed by channels_bubble_prefab.py parser."""
    blocks: list[str] = []
    for i, ch in enumerate(channels, start=1):
        blocks.append(
            "\n".join(
                [
                    f"{i}. {ch['title']}",
                    f"URL: {ch['url']}",
                    f"Subscribers: {ch['subscribers']}",
                    f"Views: {ch['views']}",
                    f"Videos: {ch['videos']}",
                    f"Score: {ch['score']:.4f}",
                ]
            )
        )
    return "\n\n".join(blocks)


async def main():
    server_params = StdioServerParameters(
        command="python",
        args=[str(Path(__file__).resolve().parent / "mcp_server.py")],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("Connected to mcp_server")

            tools = (await session.list_tools()).tools
            tools_desc = describe_tools(tools)
            print(f"Loaded {len(tools)} tools\n")

            system_prompt = f"""You are an agent with YouTube discovery tools, sandbox file tools, and a Prefab generation tool.

You solve tasks by calling tools ONE AT A TIME and observing their results.

Available tools (names and parameters):
{tools_desc}

You must respond with EXACTLY ONE line, in one of these two formats:
  FUNCTION_CALL: {{"tool_name": "<name>", "tool_arguments": {{...}}}}
  FINAL_ANSWER: <summary of what you did>

Rules:
- Use JSON for FUNCTION_CALL exactly as shown (double quotes).
- Paths for write_file/read_file/edit_file are relative to the server sandbox folder only
  (e.g. "top_channels.txt") — no leading slash, no "..".
- When asked to dump top channels to a file:
  1) Call get_top_youtube_channels with the user's query (and locale args if given).
  2) Call write_file using EXACT canonical format below (do not invent other formats):
     1. <title>
     URL: <url>
     Subscribers: <int>
     Views: <int>
     Videos: <int>
     Score: <float>
     (blank line between channels)
  3) Call read_file to verify the written content.
  4) Call build_prefab_source with input_path="top_channels.txt" and
     output_filename="generated_channels_bubble.py".
  5) FINAL_ANSWER must mention both files:
     sandbox/top_channels.txt and generated_channels_bubble.py
- When the task is only listing channels (no file), FINAL_ANSWER must still list each channel as:
  [Title](url) | Subscribers: <n> | Views: <n> | Videos: <n> | Score: <n>
- When asked to plot top videos for a YouTube channel:
  1) Call plot_channel_top_videos with the channel_link (and optional top_n).
  2) FINAL_ANSWER must mention generated_video_views.py and list every video with
     its title, view count, and like count.
- Do not invent tools or URLs; only use tool outputs.
"""

            task = ACTIVE_TASK

            history: list[str] = []
            for iteration in range(1, MAX_ITERATIONS + 1):
                print(f"\n--- Iteration {iteration} ---")

                context = "\n".join(history) if history else "(no prior steps)"
                prompt = (
                    f"{system_prompt}\n"
                    f"Task: {task}\n\n"
                    f"Previous steps:\n{context}\n\n"
                    f"What is your next single action?"
                )

                print(f"Sleeping {LLM_SLEEP_SECONDS}s before LLM call...")
                await asyncio.sleep(LLM_SLEEP_SECONDS)

                try:
                    response = await generate_with_timeout(prompt)
                except (TimeoutError, asyncio.TimeoutError):
                    print("LLM timed out — stopping.")
                    break
                except Exception as e:
                    print(f"LLM error: {e}")
                    break

                llm_text = (response.text or "").strip()
                print(f"LLM: {llm_text}")

                if llm_text.startswith("FINAL_ANSWER:"):
                    print("\n=== Agent done ===")
                    print(llm_text)
                    break

                try:
                    if not llm_text.startswith("FUNCTION_CALL:"):
                        raise ValueError(f"Unexpected model output: {llm_text[:200]}")
                    call_json = llm_text.split("FUNCTION_CALL:", 1)[1].strip()
                    call = json.loads(call_json)
                    tool_name = call["tool_name"]
                    tool_args = call.get("tool_arguments", {})
                    result = await session.call_tool(tool_name, tool_args)
                    payload = (
                        result.content[0].text
                        if result.content and hasattr(result.content[0], "text")
                        else str(result)
                    )
                    # Stabilize LLM outputs: after channel discovery, write a canonical dump format
                    # so downstream plotting never depends on model formatting variability.
                    if tool_name == "get_top_youtube_channels":
                        channels = extract_channels_from_payload(payload)
                        if channels:
                            canonical_text = format_channels_dump(channels)
                            write_res = await session.call_tool(
                                "write_file",
                                {"path": "top_channels.txt", "content": canonical_text},
                            )
                            write_payload = (
                                write_res.content[0].text
                                if write_res.content and hasattr(write_res.content[0], "text")
                                else str(write_res)
                            )
                            payload = f"{payload}\nAUTO_WRITE_FILE: {write_payload}"
                except Exception as e:
                    payload = f"ERROR: {e}"

                print(f"← {payload}")
                history.append(f"Iteration {iteration}: called {llm_text} → {payload}")
            else:
                print("\nReached MAX_ITERATIONS without FINAL_ANSWER.")


if __name__ == "__main__":
    asyncio.run(main())
