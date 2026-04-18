"""
YouTube channel discovery agent (Gemini + single tool).

Before running:
  pip install google-genai python-dotenv requests
  Create a .env file with:
    GEMINI_API_KEY=...
    YOUTUBE_API_KEY=...   (YouTube Data API v3 key)
    GEMINI_MODEL=gemini-3.1-flash-lite-preview   (optional)
"""
from google import genai
import json
import re
import os
import time
from dotenv import load_dotenv

from get_youtube_channels import get_top_youtube_channels

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
THROTTLE_SECONDS = 10

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY not set. Create a .env file with GEMINI_API_KEY=...")

client = genai.Client(api_key=GEMINI_API_KEY)


def call_llm(prompt: str) -> str:
    print(f"  [waiting {THROTTLE_SECONDS}s to respect rate limits...]", flush=True)
    time.sleep(THROTTLE_SECONDS)
    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    return response.text


system_prompt = """You are an assistant that finds top YouTube channels for a topic using one tool.

Tool: get_top_youtube_channels(query: str, max_pages: int = 2) -> str
  Searches YouTube for channels matching `query`, scores them, returns JSON with up to 5 channels.
  Each channel includes: title, channel_id, url (clickable channel link), subscribers, views, videos, score.
  Optional max_pages (default 2) controls how many search result pages to fetch (1–5 is reasonable).

You must respond with ONLY JSON — no markdown fences around the whole message, no extra text:

To call the tool:
{"tool_name": "get_top_youtube_channels", "tool_arguments": {"query": "<search phrase>", "max_pages": 2}}

For the final reply, use this exact JSON shape (answer is one string; use \\n for newlines inside it):
{"answer": "<formatted string>"}

Final answer formatting rules (inside the answer string):
- Start with one short intro sentence, then a blank line (\\n\\n).
- For each channel from the tool JSON, use a numbered list: "1. ", "2. ", etc.
- Each list item MUST use a markdown link with the exact url from the data: [Channel Title](url)
  Never invent or shorten URLs — copy url exactly from the tool result.
- On the next line(s) in the same list item, indent with two spaces and show: subscribers, total views, video count (human-readable, e.g. "1.2M subscribers").
- End with a blank line and a brief "Why these picks" line tied to score or relevance.
- If the tool returned an error object, explain it helpfully without fabricating channels.

Rules:
- Use get_top_youtube_channels whenever the user wants channels, creators, or YouTube discovery for a topic.
- After tool results, always include every channel returned with its link and stats in the formatted answer.
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


tools = {
    "get_top_youtube_channels": get_top_youtube_channels_tool,
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


def run_agent(user_query: str, max_iterations: int = 5, verbose: bool = True):
    if verbose:
        print(f"\n{'='*60}\n  User: {user_query}\n{'='*60}")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_query},
    ]

    for iteration in range(max_iterations):
        if verbose:
            print(f"\n--- Iteration {iteration + 1} ---")

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

        response_text = call_llm(prompt)
        if verbose:
            print(f"LLM: {response_text.strip()}")

        try:
            parsed = parse_llm_response(response_text)
        except (ValueError, json.JSONDecodeError) as e:
            if verbose:
                print(f"Parse error: {e}\nAsking LLM to retry...")
            messages.append({"role": "assistant", "content": response_text})
            messages.append(
                {
                    "role": "user",
                    "content": "Please respond with valid JSON only. No markdown, no extra text.",
                }
            )
            continue

        if "answer" in parsed:
            if verbose:
                print(f"\n{'='*60}\n  Agent Answer: {parsed['answer']}\n{'='*60}")
            return parsed["answer"]

        if "tool_name" in parsed:
            tool_name = parsed["tool_name"]
            tool_args = parsed.get("tool_arguments", {})
            if verbose:
                print(f"→ Calling tool: {tool_name}({tool_args})")

            if tool_name not in tools:
                error_msg = json.dumps(
                    {"error": f"Unknown tool: {tool_name}. Use: {list(tools.keys())}"}
                )
                if verbose:
                    print(f"→ Error: {error_msg}")
                messages.append({"role": "assistant", "content": response_text})
                messages.append({"role": "tool", "content": error_msg})
                continue

            tool_result = tools[tool_name](**tool_args)
            if verbose:
                print(f"→ Result: {tool_result[:500]}{'...' if len(tool_result) > 500 else ''}")
            messages.append({"role": "assistant", "content": response_text})
            messages.append({"role": "tool", "content": tool_result})

    print("\nMax iterations reached. Agent could not complete the task.")
    if verbose:
        print(f"\n{'='*60}\nFull conversation history:\n{'='*60}")
        for i, msg in enumerate(messages):
            print(f"[{i}] {msg['role']}: {msg['content'][:100]}...")
    return None


if __name__ == "__main__":
    print("\n" + "=" * 60 + "\n  YouTube channel agent\n" + "=" * 60)
    run_agent("Find top YouTube channels about old kishore kumar songs.")
