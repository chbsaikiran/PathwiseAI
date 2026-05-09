"""
MCP server exposing PathwiseAI YouTube tools.

Run with MCP CLI (after installing mcp[cli]):
  mcp run mcp_server.py

Or directly:
  python mcp_server.py
"""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from channels_bubble_prefab import parse_top_channels_file as _parse_top_channels_file
from video_views_prefab import parse_top_videos_file as _parse_top_videos_file
from plot_prefab import build_prefab_plot as _build_prefab_plot
from get_youtube_channels import get_top_youtube_channels as _get_top_youtube_channels
from youtube_channel_comments import analyze_channel_viewer_comments as _analyze_channel_viewer_comments
from youtube_locale import effective_search_locale
from youtube_video_stats import get_top_videos_with_stats as _get_top_videos_with_stats

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


@mcp.tool(name="build_prefab_plot")
def build_prefab_plot_tool(
    input_path: str,
    title: str = "",
) -> dict:
    """
    Parse a sandbox data file and generate a Prefab chart as generated_plot.py.

    The LLM inspects the field names and sample values, then picks the most
    suitable chart type automatically:
      - 3+ numeric fields  →  bubble chart (ScatterChart with z_axis)
      - 2 numeric fields   →  scatter chart (ScatterChart, x vs y)

    Accepts both top_channels.txt and top_videos.txt formats (auto-detected).

    Args:
      input_path: Sandbox-relative path to the data file
                  (e.g. "top_channels.txt" or "top_videos.txt").
      title: Chart title shown in the UI. Auto-derived from the file name if empty.

    Returns:
      {"ok": bool, "input_path": str, "detected_format": str,
       "output_path": str, "rows": int, "bytes": int}
    """
    input_file = _sandbox_rel_path(input_path)
    if not input_file.is_file():
        return {"ok": False, "error": f"Input file not found: {input_path}"}

    # Auto-detect format: try channels first, then videos.
    rows = None
    detected = "unknown"
    try:
        rows = _parse_top_channels_file(input_file)
        detected = "channels"
    except Exception:
        pass
    if not rows:
        try:
            rows = _parse_top_videos_file(input_file)
            detected = "videos"
        except Exception:
            pass
    if not rows:
        return {"ok": False, "error": f"Could not parse {input_path} as channels or videos format."}

    chart_title = title or ("Top YouTube Channels" if detected == "channels" else "Top Videos — Views vs Likes")
    source = _build_prefab_plot(rows, chart_title)

    out = PROJECT_ROOT / "generated_plot.py"
    compile(source, str(out), "exec")
    out.write_text(source, encoding="utf-8")
    return {
        "ok": True,
        "input_path": str(input_file.relative_to(SANDBOX_ROOT.resolve())),
        "detected_format": detected,
        "output_path": str(out.relative_to(PROJECT_ROOT)),
        "rows": len(rows),
        "bytes": len(source.encode("utf-8")),
    }

class ChannelOut(BaseModel):
    title: str = ""
    channel_id: str = ""
    url: str = ""
    subscribers: int = 0
    views: int = 0
    videos: int = 0
    score: float = 0.0


def _normalize_channels(channels: list[dict]) -> list[dict]:
    return [ChannelOut.model_validate(ch).model_dump() for ch in channels]


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


@mcp.tool()
def get_top_video_stats(channel_link: str, top_n: int = 5) -> dict:
    """
    Fetch the top N videos by view count for a YouTube channel with actual view and like counts.

    Args:
      channel_link: YouTube channel URL (/@handle or /channel/UC...) or UC... channel id.
      top_n: Number of top videos to fetch (1–10, default 5).

    Returns:
      {
        "ok": bool,
        "channel_link": str,
        "videos": [{"title", "url", "view_count", "like_count", "channel_title", "channel_url"}]
      }
    """
    top_n = max(1, min(int(top_n), 10))
    try:
        videos = _get_top_videos_with_stats(channel_link, top_n=top_n)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    if not videos:
        return {"ok": False, "error": "No videos found for this channel."}

    return {"ok": True, "channel_link": channel_link, "videos": videos}



if __name__ == "__main__":
    mcp.run()
