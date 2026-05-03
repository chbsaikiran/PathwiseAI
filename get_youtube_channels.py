import os
import time
import re

from youtube_http import youtube_api_get
from youtube_locale import apply_search_locale

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"


def _raise_if_youtube_error(data: dict) -> None:
    err = data.get("error")
    if err:
        raise RuntimeError(err.get("message", str(err)))


def _query_terms(query: str) -> list[str]:
    # Keep meaningful alphanumeric tokens from query.
    terms = re.findall(r"[a-zA-Z0-9]+", (query or "").lower())
    return [t for t in terms if len(t) >= 2]


def _description_matches_query(description: str, query: str) -> bool:
    desc = (description or "").lower()
    q = (query or "").strip().lower()
    if not q:
        return True
    if q in desc:
        return True
    terms = _query_terms(q)
    if not terms:
        return False
    return any(t in desc for t in terms)


def get_top_youtube_channels(
    query,
    max_pages=2,
    relevance_language: str | None = None,
    region_code: str | None = None,
):
    api_key = os.getenv("YOUTUBE_API_KEY", "")
    if not api_key:
        raise RuntimeError("YOUTUBE_API_KEY not set. Add it to your .env file.")

    all_channel_ids = set()

    # Primary pass: multiple pages ordered by viewCount (best proxy for subscriber count).
    next_page_token = None
    for _ in range(max_pages):
        params = {
            "part": "snippet",
            "q": query,
            "type": "channel",
            "order": "viewCount",
            "maxResults": 25,
            "key": api_key,
            "pageToken": next_page_token,
        }
        apply_search_locale(params, relevance_language, region_code)
        res = youtube_api_get(SEARCH_URL, params)
        _raise_if_youtube_error(res)
        for item in res.get("items", []):
            all_channel_ids.add(item["snippet"]["channelId"])
        next_page_token = res.get("nextPageToken")
        if not next_page_token:
            break
        time.sleep(0.25)

    # Supplemental pass: one page ordered by relevance to capture highly relevant
    # channels that may not rank high by total view count.
    time.sleep(0.25)
    params = {
        "part": "snippet",
        "q": query,
        "type": "channel",
        "order": "relevance",
        "maxResults": 25,
        "key": api_key,
    }
    apply_search_locale(params, relevance_language, region_code)
    res = youtube_api_get(SEARCH_URL, params)
    _raise_if_youtube_error(res)
    for item in res.get("items", []):
        all_channel_ids.add(item["snippet"]["channelId"])

    channel_ids_list = list(all_channel_ids)
    channels = []

    for i in range(0, len(channel_ids_list), 50):
        params = {
            "part": "snippet,statistics",
            "id": ",".join(channel_ids_list[i : i + 50]),
            "key": api_key,
        }

        res = youtube_api_get(CHANNELS_URL, params)
        _raise_if_youtube_error(res)

        for item in res.get("items", []):
            stats = item["statistics"]
            snippet = item["snippet"]
            description = snippet.get("description", "")

            # Hard filter: keep channels whose description matches user query.
            if not _description_matches_query(description, query):
                continue

            subs = int(stats.get("subscriberCount", 0))
            views = int(stats.get("viewCount", 0))
            videos = int(stats.get("videoCount", 0))

            if subs < 1000 or videos < 10:
                continue

            cid = item["id"]
            custom = (snippet.get("customUrl") or "").strip().lstrip("@")
            if custom:
                url = f"https://www.youtube.com/@{custom}"
            else:
                url = f"https://www.youtube.com/channel/{cid}"

            channels.append(
                {
                    "title": snippet["title"],
                    "channel_id": cid,
                    "url": url,
                    "subscribers": subs,
                    "views": views,
                    "videos": videos,
                }
            )

    if not channels:
        return []

    # Min-max normalize each metric independently to [0, 1] so that subscribers
    # (thousands), views (millions), and video count (hundreds) all contribute
    # equally to the final score regardless of their raw magnitude.
    for key in ("subscribers", "views"):
        vals = [ch[key] for ch in channels]
        lo, hi = min(vals), max(vals)
        span = hi - lo or 1  # avoid divide-by-zero when all values are identical
        for ch in channels:
            ch[f"_{key}_norm"] = (ch[key] - lo) / span

    for ch in channels:
        ch["score"] = round(
            (ch.pop("_subscribers_norm") + ch.pop("_views_norm")) / 2,
            4,
        )

    channels.sort(key=lambda x: x["score"], reverse=True)
    return channels[:5]
