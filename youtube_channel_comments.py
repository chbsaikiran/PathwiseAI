"""
Fetch comment samples from a channel's top videos (by view count) via YouTube Data API v3.
Used by the agent tool analyze_channel_viewer_sentiment.
"""

from __future__ import annotations

import os
import re
import time
from urllib.parse import parse_qs, urlparse

import requests

CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
COMMENTS_URL = "https://www.googleapis.com/youtube/v3/commentThreads"


def _api_key() -> str:
    k = os.getenv("YOUTUBE_API_KEY", "")
    if not k:
        raise RuntimeError("YOUTUBE_API_KEY not set. Add it to your .env file.")
    return k


def _channels_list(api_key: str, **params: str) -> dict:
    merged = {**params, "key": api_key}
    return requests.get(CHANNELS_URL, params=merged, timeout=30).json()


def _resolve_channel(api_key: str, channel_input: str) -> tuple[str, str]:
    """Return (channel_id, channel_title) or raise ValueError."""
    raw = channel_input.strip()
    if not raw:
        raise ValueError("Empty channel link.")

    # Bare channel ID
    if re.fullmatch(r"UC[\w-]{22}", raw):
        cid = raw
        data = _channels_list(api_key, part="snippet", id=cid)
        items = data.get("items") or []
        if not items:
            raise ValueError(f"No channel found for id {cid}.")
        return cid, items[0]["snippet"]["title"]

    # URL or path-like string
    if not raw.startswith("http"):
        raw = "https://" + raw.lstrip("/")

    parsed = urlparse(raw)
    host = (parsed.netloc or "").lower()
    if "youtube.com" not in host and "youtu.be" not in host:
        raise ValueError("Expected a youtube.com channel URL (or a UC… channel id).")

    path = parsed.path or ""

    m = re.search(r"/channel/(UC[\w-]{22})", path)
    if m:
        cid = m.group(1)
        data = _channels_list(api_key, part="snippet", id=cid)
        items = data.get("items") or []
        if not items:
            raise ValueError(f"No channel found for id {cid}.")
        return cid, items[0]["snippet"]["title"]

    m = re.search(r"/@([\w.-]+)", path)
    if m:
        handle = m.group(1)
        data = _channels_list(api_key, part="snippet", forHandle=handle)
        items = data.get("items") or []
        if not items:
            raise ValueError(f"No channel found for handle @{handle}.")
        cid = items[0]["id"]
        return cid, items[0]["snippet"]["title"]

    qs = parse_qs(parsed.query)
    if "channel_id" in qs and qs["channel_id"]:
        cid = qs["channel_id"][0].strip()
        if re.fullmatch(r"UC[\w-]{22}", cid):
            data = _channels_list(api_key, part="snippet", id=cid)
            items = data.get("items") or []
            if not items:
                raise ValueError(f"No channel found for id {cid}.")
            return cid, items[0]["snippet"]["title"]

    raise ValueError(
        "Could not parse channel URL. Use /channel/UC… or /@handle (or paste the 24-char channel id)."
    )


def _top_videos_by_views(api_key: str, channel_id: str, max_videos: int) -> list[dict]:
    """Most-viewed videos on the channel (search order=viewCount)."""
    params = {
        "part": "snippet",
        "type": "video",
        "channelId": channel_id,
        "order": "viewCount",
        "maxResults": min(max_videos, 50),
        "key": api_key,
    }
    res = requests.get(SEARCH_URL, params=params, timeout=30).json()
    items = res.get("items") or []
    if not items:
        return []

    ids = [it["id"]["videoId"] for it in items if it.get("id", {}).get("videoId")]
    if not ids:
        return []

    time.sleep(0.15)
    vparams = {
        "part": "snippet,statistics",
        "id": ",".join(ids),
        "key": api_key,
    }
    vres = requests.get(VIDEOS_URL, params=vparams, timeout=30).json()
    out = []
    for it in vres.get("items") or []:
        vid = it["id"]
        sn = it["snippet"]
        stats = it.get("statistics") or {}
        views = int(stats.get("viewCount", 0))
        out.append(
            {
                "video_id": vid,
                "title": sn.get("title", ""),
                "url": f"https://www.youtube.com/watch?v={vid}",
                "view_count": views,
            }
        )
    out.sort(key=lambda x: x["view_count"], reverse=True)
    return out[:max_videos]


def _fetch_top_comments(api_key: str, video_id: str, max_comments: int) -> list[str]:
    params = {
        "part": "snippet",
        "videoId": video_id,
        "maxResults": min(max_comments, 100),
        "order": "relevance",
        "textFormat": "plainText",
        "key": api_key,
    }
    res = requests.get(COMMENTS_URL, params=params, timeout=30).json()
    if res.get("error"):
        err = res["error"]
        reason = (err.get("errors") or [{}])[0].get("reason", "")
        if reason in ("commentsDisabled", "forbidden"):
            return []
        raise RuntimeError(err.get("message", str(err)))

    texts: list[str] = []
    for it in res.get("items") or []:
        top = it.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
        text = (top.get("textDisplay") or top.get("textOriginal") or "").strip()
        if not text:
            continue
        if len(text) > 500:
            text = text[:497] + "..."
        texts.append(text)
    return texts


def analyze_channel_viewer_comments(
    channel_link: str,
    top_videos: int = 5,
    comments_per_video: int = 20,
) -> dict:
    """
    Resolve channel, take top `top_videos` by view count, pull up to `comments_per_video`
    top-level comments per video, return structured data for the LLM to summarize.
    """
    api_key = _api_key()
    top_videos = max(1, min(int(top_videos), 10))
    comments_per_video = max(1, min(int(comments_per_video), 50))

    channel_id, channel_title = _resolve_channel(api_key, channel_link)
    time.sleep(0.15)

    videos = _top_videos_by_views(api_key, channel_id, top_videos)
    if not videos:
        return {
            "channel_id": channel_id,
            "channel_title": channel_title,
            "channel_url": f"https://www.youtube.com/channel/{channel_id}",
            "videos_analyzed": [],
            "collated_comment_text": "",
            "note": "No public videos found for this channel (or search returned empty).",
        }

    custom = ""
    ch = _channels_list(api_key, part="snippet", id=channel_id)
    if ch.get("items"):
        cu = (ch["items"][0]["snippet"].get("customUrl") or "").strip().lstrip("@")
        if cu:
            custom = cu
    channel_url = (
        f"https://www.youtube.com/@{custom}" if custom else f"https://www.youtube.com/channel/{channel_id}"
    )

    analyzed: list[dict] = []
    collated_parts: list[str] = []

    for v in videos:
        time.sleep(0.15)
        try:
            comments = _fetch_top_comments(api_key, v["video_id"], comments_per_video)
        except Exception as e:
            analyzed.append(
                {
                    "title": v["title"],
                    "video_id": v["video_id"],
                    "url": v["url"],
                    "view_count": v["view_count"],
                    "comments_fetched": 0,
                    "sample_comments": [],
                    "fetch_note": str(e),
                }
            )
            continue

        analyzed.append(
            {
                "title": v["title"],
                "video_id": v["video_id"],
                "url": v["url"],
                "view_count": v["view_count"],
                "comments_fetched": len(comments),
                "sample_comments": comments,
            }
        )
        collated_parts.append(f"## Video: {v['title']}\n" + "\n".join(f"- {c}" for c in comments))

    collated = "\n\n".join(collated_parts)
    max_chars = 14000
    if len(collated) > max_chars:
        collated = collated[: max_chars - 3] + "..."

    return {
        "channel_id": channel_id,
        "channel_title": channel_title,
        "channel_url": channel_url,
        "videos_analyzed": analyzed,
        "collated_comment_text": collated,
        "note": (
            "Synthesize what viewers seem to value, criticize, or joke about across these samples. "
            "Comments are a biased sample (engaged viewers, not everyone)."
        ),
    }
