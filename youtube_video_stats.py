"""Fetch top N videos by view count for a YouTube channel, with actual view + like statistics."""

from __future__ import annotations

import os
import time

from youtube_http import youtube_api_get
from youtube_channel_comments import _resolve_channel

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


def _api_key() -> str:
    k = os.getenv("YOUTUBE_API_KEY", "")
    if not k:
        raise RuntimeError("YOUTUBE_API_KEY not set. Add it to your .env file.")
    return k


def _raise_if_error(data: dict) -> None:
    err = data.get("error")
    if err:
        raise RuntimeError(err.get("message", str(err)))


def get_top_videos_with_stats(channel_link: str, top_n: int = 5) -> list[dict]:
    """
    Resolve a YouTube channel and return the top_n videos ordered by view count.

    Each returned dict contains:
      video_id, title, url, view_count (int), like_count (int),
      channel_title, channel_url
    """
    api_key = _api_key()
    top_n = max(1, min(int(top_n), 10))

    channel_id, channel_title, channel_url = _resolve_channel(api_key, channel_link)
    time.sleep(0.2)

    # Step 1: search.list ordered by viewCount to get video IDs.
    search_res = youtube_api_get(
        SEARCH_URL,
        {
            "part": "snippet",
            "type": "video",
            "channelId": channel_id,
            "order": "viewCount",
            "maxResults": top_n,
            "key": api_key,
        },
    )
    _raise_if_error(search_res)

    items = search_res.get("items") or []
    video_ids: list[str] = []
    title_by_id: dict[str, str] = {}
    for it in items:
        vid = it.get("id", {}).get("videoId")
        if not vid:
            continue
        video_ids.append(vid)
        title_by_id[vid] = (it.get("snippet") or {}).get("title", "")

    if not video_ids:
        return []

    # Step 2: videos.list for actual statistics in a single batch call.
    time.sleep(0.2)
    stats_res = youtube_api_get(
        VIDEOS_URL,
        {
            "part": "statistics",
            "id": ",".join(video_ids),
            "key": api_key,
        },
    )
    _raise_if_error(stats_res)

    stats_by_id: dict[str, dict] = {}
    for it in stats_res.get("items") or []:
        vid = it["id"]
        s = it.get("statistics") or {}
        stats_by_id[vid] = {
            "view_count": int(s.get("viewCount") or 0),
            "like_count": int(s.get("likeCount") or 0),
        }

    # Merge in original search-rank order.
    out: list[dict] = []
    for vid in video_ids:
        stats = stats_by_id.get(vid, {"view_count": 0, "like_count": 0})
        out.append(
            {
                "video_id": vid,
                "title": title_by_id.get(vid, ""),
                "url": f"https://www.youtube.com/watch?v={vid}",
                "view_count": stats["view_count"],
                "like_count": stats["like_count"],
                "channel_title": channel_title,
                "channel_url": channel_url,
            }
        )
    return out
