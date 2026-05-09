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
from pydantic import BaseModel

load_dotenv()

MODEL = "gemini-3.1-flash-lite-preview"
MAX_ITERATIONS = 12
LLM_SLEEP_SECONDS = 5
LLM_TIMEOUT = 60

# ── Task selection ────────────────────────────────────────────────────────────
# Switch ACTIVE_TASK to choose which prompt the agent runs.

TASK_TOP_CHANNELS = (
    "Find top YouTube channels for the query 'Reinforcement Learning' "
    "(English, region IN). Dump the full results into sandbox file top_channels.txt "
    "(include each channel's link, subscribers, views, videos uploaded, and score). "
    "Fetch the top 5 videos by view count for the top most channel in the above "
    "Write the results to sandbox/top_videos.txt using the canonical format, "
    "read the file back to confirm, then call build_prefab_plot with "
    "input_path='top_videos.txt' to generate generated_plot.py, and finish with FINAL_ANSWER."
)

TASK_VIDEO_VIEWS = (
    "Fetch the top 5 videos by view count for the YouTube channel "
    "'https://www.youtube.com/@HareKrishnaGoldenTempleHyd'. "
    "Write the results to sandbox/top_videos.txt using the canonical format, "
    "read the file back to confirm, then call build_prefab_plot with "
    "input_path='top_videos.txt' to generate generated_plot.py. "
    "Finish with FINAL_ANSWER listing every video title, view count, and like count."
)

ACTIVE_TASK = TASK_TOP_CHANNELS  # ← change to TASK_VIDEO_VIEWS for the video chart
# ─────────────────────────────────────────────────────────────────────────────

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


class ChannelData(BaseModel):
    title: str = ""
    url: str = ""
    subscribers: int = 0
    views: int = 0
    videos: int = 0
    score: float = 0.0


class VideoData(BaseModel):
    title: str = ""
    url: str = ""
    view_count: int = 0
    like_count: int = 0
    channel_title: str = ""
    channel_url: str = ""


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


def extract_channels_from_payload(payload: str) -> list[ChannelData] | None:
    try:
        data = json.loads(payload)
        items = data.get("channels", []) if isinstance(data, dict) else []
        result = [ChannelData.model_validate(ch) for ch in items if isinstance(ch, dict)]
        return result or None
    except Exception:
        return None


def format_channels_dump(channels: list[ChannelData]) -> str:
    blocks = [
        f"{i}. {ch.title}\nURL: {ch.url}\nSubscribers: {ch.subscribers}\n"
        f"Views: {ch.views}\nVideos: {ch.videos}\nScore: {ch.score:.4f}"
        for i, ch in enumerate(channels, 1)
    ]
    return "\n\n".join(blocks)


def extract_videos_from_payload(payload: str) -> list[VideoData] | None:
    try:
        data = json.loads(payload)
        items = data.get("videos", []) if isinstance(data, dict) else []
        result = [VideoData.model_validate(v) for v in items if isinstance(v, dict)]
        return result or None
    except Exception:
        return None


def format_videos_dump(videos: list[VideoData]) -> str:
    blocks = [
        f"{i}. {v.title}\nURL: {v.url}\nViews: {v.view_count}\n"
        f"Likes: {v.like_count}\nChannel: {v.channel_title}\nChannelURL: {v.channel_url}"
        for i, v in enumerate(videos, 1)
    ]
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

            system_prompt = f"""You are an agent with YouTube discovery tools, sandbox file tools, and a Prefab chart generator.
Call ONE tool per response.

Available tools:
{tools_desc}

Response format — exactly one of:
  FUNCTION_CALL: {{"tool_name": "<name>", "tool_arguments": {{...}}}}
  FINAL_ANSWER: <summary>

Rules:
- After get_top_youtube_channels or get_top_video_stats, the sandbox file is written automatically.
  Call read_file to confirm, then build_prefab_plot to generate the chart, then FINAL_ANSWER.
- Sandbox paths are relative (e.g. "top_channels.txt") — no ".." or leading slash.
- FINAL_ANSWER must name the sandbox file and generated_plot.py, and list each result item.
- Only use tool outputs — never invent URLs or data.
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
                    # Stabilize LLM outputs: after channel/video discovery, write a canonical
                    # dump so downstream chart generation never depends on model formatting.
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
                    elif tool_name == "get_top_video_stats":
                        videos = extract_videos_from_payload(payload)
                        if videos:
                            canonical_text = format_videos_dump(videos)
                            write_res = await session.call_tool(
                                "write_file",
                                {"path": "top_videos.txt", "content": canonical_text},
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
