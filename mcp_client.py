"""
Agentic loop over example_mcp_server.py using Gemini.

The model picks tools from the MCP server and we execute them, feeding results
back into the prompt until it emits FINAL_ANSWER. A 5s sleep is inserted before
each LLM call so students can watch the loop unfold.

Task chosen on purpose so the model needs ~3 tools:
  1. write_file  — create a file in the sandbox
  2. read_file   — verify what was written
  3. edit_file   — replace a word inside that file

Run:
  # from NewCode/
  uv run AgenticMCPUse.py
  # or: python AgenticMCPUse.py

Env:
  GEMINI_API_KEY in a .env file (same as before)
"""

import asyncio
import json
import os
from concurrent.futures import TimeoutError

from dotenv import load_dotenv
from google import genai
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

MODEL = "gemini-3.1-flash-lite-preview"   # per your instruction; swap if the name differs
MAX_ITERATIONS = 6
LLM_SLEEP_SECONDS = 5
LLM_TIMEOUT = 15

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

async def main():
    server_params = StdioServerParameters(
        command="python",
        args=["mcp_server.py"],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("Connected to mcp_server")

            tools = (await session.list_tools()).tools
            #tools_desc = describe_tools(tools)
            print(f"Loaded {len(tools)} tools\n")

            system_prompt = f"""You are a YouTube channel discovery and audience sentiment analysis agent.
You solve tasks by calling tools ONE AT A TIME and observing their results.
You have two tools:
1. get_top_youtube_channels: Get the top 5 youtube channels for a given query
2. analyze_channel_viewer_sentiment: Analyze the audience sentiment of a given youtube channel
You must respond with EXACTLY ONE line, in one of these two formats:
  FUNCTION_CALL: {{"tool_name": "<get_top_youtube_channels|analyze_channel_viewer_sentiment>", "tool_arguments": {{...}}}}
  FINAL_ANSWER: <short natural-language summary of what you did>

Available tools:
{tools}

Rules:
- Provide args in the exact order of the tool's parameters.
- Do not invent tools that are not listed above.
- After each FUNCTION_CALL you'll receive the result; use it to decide the next step.
- Prefer the simplest 2–3 tool sequence that solves the task.
- When the task is complete, emit FINAL_ANSWER.
- If the task asks for top channels, FINAL_ANSWER MUST include all channels returned by the tool.
- For each channel include: clickable URL, subscribers, views, videos uploaded, and score.
- Use this exact per-channel template inside FINAL_ANSWER:
  [Channel Name](URL) | Subscribers: <n> | Views: <n> | Videos: <n> | Score: <n>
"""

            task = (
                "Get the top 5 youtube channels in english for the query 'Transformers and LLMs Attention Mechanism' and in final answer include links, subscribers, views, videos uploaded, and score for each channel."
            )

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
                except Exception as e:
                    payload = f"ERROR: {e}"

                print(f"← {payload}")
                history.append(
                    f"Iteration {iteration}: called {llm_text} → {payload}"
                )
            else:
                print("\nReached MAX_ITERATIONS without FINAL_ANSWER.")


if __name__ == "__main__":
    asyncio.run(main())
