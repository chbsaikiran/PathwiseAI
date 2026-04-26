"""
MCP server exposing PathwiseAI YouTube tools.

Run with MCP CLI (after installing mcp[cli]):
  mcp run mcp_server.py

Or directly:
  python mcp_server.py
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from channels_bubble_prefab import (
    build_prefab_source as _build_prefab_source_template,
    parse_top_channels_file as _parse_top_channels_file,
)
from get_youtube_channels import get_top_youtube_channels as _get_top_youtube_channels
from youtube_channel_comments import analyze_channel_viewer_comments as _analyze_channel_viewer_comments
from youtube_locale import effective_search_locale

load_dotenv()

mcp = FastMCP("pathwiseai-youtube-tools")

# All file tools operate only under this directory (relative paths only).
SANDBOX_ROOT = Path(__file__).resolve().parent / "sandbox"
SANDBOX_ROOT.mkdir(parents=True, exist_ok=True)
PROJECT_ROOT = Path(__file__).resolve().parent


def _sandbox_rel_path(rel: str) -> Path:
    """Resolve a sandbox-relative path; reject escapes and absolute paths."""
    raw = (rel or "").strip().replace("\\", "/").lstrip("/")
    if not raw:
        raise ValueError("path must be a non-empty relative path inside sandbox/")
    if ".." in Path(raw).parts:
        raise ValueError("path must not contain '..'")
    root = SANDBOX_ROOT.resolve()
    target = (root / raw).resolve()
    if not target.is_relative_to(root):
        raise ValueError("path escapes sandbox")
    return target


@mcp.tool()
def write_file(path: str, content: str) -> dict:
    """
    Write text to a file inside the project sandbox/ folder.

    Args:
      path: Relative path only (e.g. "top_channels.txt"). No leading slash, no '..'.
      content: Full file contents as UTF-8 text.
    """
    p = _sandbox_rel_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return {"ok": True, "path": str(p.relative_to(SANDBOX_ROOT.resolve())), "bytes": len(content.encode("utf-8"))}


@mcp.tool()
def read_file(path: str) -> dict:
    """
    Read a UTF-8 text file from the sandbox/ folder.

    Args:
      path: Relative path inside sandbox (e.g. "top_channels.txt").
    """
    p = _sandbox_rel_path(path)
    if not p.is_file():
        return {"ok": False, "error": f"Not a file: {path}"}
    text = p.read_text(encoding="utf-8", errors="replace")
    return {
        "ok": True,
        "path": str(p.relative_to(SANDBOX_ROOT.resolve())),
        "content": text,
        "length": len(text),
    }


@mcp.tool()
def edit_file(path: str, old: str, new: str, replace_all: bool = True) -> dict:
    """
    Replace occurrences of `old` with `new` in a sandbox text file.

    Args:
      path: Relative path inside sandbox.
      old: Substring to find.
      new: Replacement text.
      replace_all: If true, replace all occurrences; if false, replace only the first.
    """
    p = _sandbox_rel_path(path)
    if not p.is_file():
        return {"ok": False, "error": f"Not a file: {path}"}
    if old == "":
        return {"ok": False, "error": "old must be a non-empty substring"}
    text = p.read_text(encoding="utf-8", errors="replace")
    if old not in text:
        return {"ok": False, "error": "old substring not found", "path": str(p.relative_to(SANDBOX_ROOT.resolve()))}
    if replace_all:
        updated = text.replace(old, new)
        n = text.count(old)
    else:
        updated = text.replace(old, new, 1)
        n = 1 if old in text else 0
    p.write_text(updated, encoding="utf-8")
    return {
        "ok": True,
        "path": str(p.relative_to(SANDBOX_ROOT.resolve())),
        "replacements": n,
        "length": len(updated),
    }


@mcp.tool(name="build_prefab_source")
def build_prefab_source_tool(
    input_path: str = "top_channels.txt",
    output_filename: str = "generated_channels_bubble.py",
) -> dict:
    """
    Generate a Prefab plot app from sandbox top-channels text using build_prefab_source().

    Args:
      input_path: Sandbox-relative input file (default "top_channels.txt").
      output_filename: Output Python file in project root (default "generated_channels_bubble.py").
    """
    input_file = _sandbox_rel_path(input_path)
    if not input_file.is_file():
        return {"ok": False, "error": f"Input file not found: {input_path}"}

    rows = _parse_top_channels_file(input_file)
    source = _build_prefab_source_template(rows)
    compile(source, str(PROJECT_ROOT / output_filename), "exec")

    out = PROJECT_ROOT / output_filename
    out.write_text(source, encoding="utf-8")
    return {
        "ok": True,
        "input_path": str(input_file.relative_to(SANDBOX_ROOT.resolve())),
        "output_path": str(out.relative_to(PROJECT_ROOT)),
        "channels": len(rows),
        "bytes": len(source.encode("utf-8")),
    }

def _normalize_channels(channels: list[dict]) -> list[dict]:
    """Return stable channel schema for MCP clients."""
    normalized: list[dict] = []
    for ch in channels:
        normalized.append(
            {
                "title": ch.get("title", ""),
                "channel_id": ch.get("channel_id", ""),
                "url": ch.get("url", ""),
                "subscribers": int(ch.get("subscribers", 0) or 0),
                "views": int(ch.get("views", 0) or 0),
                "videos": int(ch.get("videos", 0) or 0),
                "score": float(ch.get("score", 0.0) or 0.0),
            }
        )
    return normalized


@mcp.tool()
def get_top_youtube_channels(
    query: str,
    max_pages: int = 2,
    relevance_language: str | None = None,
    region_code: str | None = None,
) -> dict:
    """
    Discover top YouTube channels for a topic.

    Args:
      query: Topic or keywords (e.g. "machine learning").
      max_pages: Search pages to fetch (1-10).
      relevance_language: Optional ISO 639-1 (e.g. "en", "hi", "te").
      region_code: Optional ISO 3166-1 alpha-2 (e.g. "US", "IN").

    Returns:
      {
        "channels": [
          {
            "title": str,
            "channel_id": str,
            "url": str,
            "subscribers": int,
            "views": int,
            "videos": int,
            "score": float
          }
        ],
        "search_locale": {"relevance_language": ".."|null, "region_code": ".."|null}
      }
    """
    max_pages = max(1, min(int(max_pages), 10))
    lang_eff, reg_eff = effective_search_locale(relevance_language, region_code)
    channels = _get_top_youtube_channels(
        query,
        max_pages=max_pages,
        relevance_language=relevance_language,
        region_code=region_code,
    )
    return {
        "channels": _normalize_channels(channels),
        "search_locale": {"relevance_language": lang_eff, "region_code": reg_eff},
    }


@mcp.tool()
def analyze_channel_viewer_sentiment(
    channel_link: str,
    top_videos: int = 4,
    comments_per_video: int = 12,
    relevance_language: str | None = None,
    region_code: str | None = None,
) -> dict:
    """
    Analyze what viewers say about a channel using sampled comments.

    Args:
      channel_link: YouTube channel URL (/@handle or /channel/UC...) or UC... channel id.
      top_videos: Number of top videos to inspect (1-10).
      comments_per_video: Number of comments per video to sample (1-50).
      relevance_language: Optional ISO 639-1 for video search bias.
      region_code: Optional ISO 3166-1 alpha-2 for video search bias.

    Returns:
      Structured JSON including channel info, sampled comments, and collation text.
    """
    top_videos = max(1, min(int(top_videos), 10))
    comments_per_video = max(1, min(int(comments_per_video), 50))
    payload = _analyze_channel_viewer_comments(
        channel_link,
        top_videos=top_videos,
        comments_per_video=comments_per_video,
        relevance_language=relevance_language,
        region_code=region_code,
    )
    return payload


if __name__ == "__main__":
    mcp.run()
