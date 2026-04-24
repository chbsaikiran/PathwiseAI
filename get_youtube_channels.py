import os
import math
import time
import re

from youtube_http import youtube_api_get

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


def get_top_youtube_channels(query, max_pages=2):
    api_key = os.getenv("YOUTUBE_API_KEY", "")
    if not api_key:
        raise RuntimeError("YOUTUBE_API_KEY not set. Add it to your .env file.")

    all_channel_ids = set()
    next_page_token = None

    for _ in range(max_pages):
        params = {
            "part": "snippet",
            "q": query,
            "type": "channel",
            "maxResults": 25,
            "key": api_key,
            "pageToken": next_page_token,
        }

        res = youtube_api_get(SEARCH_URL, params)
        _raise_if_youtube_error(res)

        for item in res.get("items", []):
            all_channel_ids.add(item["snippet"]["channelId"])

        next_page_token = res.get("nextPageToken")
        if not next_page_token:
            break

        time.sleep(0.25)

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

            score = (
                math.log(subs + 1) * 0.6
                + math.log(views + 1) * 0.3
                + math.log(videos + 1) * 0.1
            )

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
                    "score": round(score, 4),
                }
            )

    channels.sort(key=lambda x: x["score"], reverse=True)
    return channels[:5]
