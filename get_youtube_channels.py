import os
import requests
import math
import time


def get_top_youtube_channels(query, max_pages=2):
    search_url = "https://www.googleapis.com/youtube/v3/search"
    channels_url = "https://www.googleapis.com/youtube/v3/channels"

    api_key = os.getenv("YOUTUBE_API_KEY", "")
    if not api_key:
        raise RuntimeError("YOUTUBE_API_KEY not set. Add it to your .env file.")

    all_channel_ids = set()
    next_page_token = None

    # Step 1: Search channels (pagination)
    for _ in range(max_pages):
        params = {
            "part": "snippet",
            "q": query,
            "type": "channel",
            "maxResults": 25,
            "key": api_key,
            "pageToken": next_page_token,
        }

        res = requests.get(search_url, params=params).json()

        for item in res.get("items", []):
            all_channel_ids.add(item["snippet"]["channelId"])

        next_page_token = res.get("nextPageToken")
        if not next_page_token:
            break

        time.sleep(0.2)

    # Step 2: Fetch stats
    channel_ids_list = list(all_channel_ids)
    channels = []

    for i in range(0, len(channel_ids_list), 50):
        params = {
            "part": "snippet,statistics",
            "id": ",".join(channel_ids_list[i : i + 50]),
            "key": api_key,
        }

        res = requests.get(channels_url, params=params).json()

        for item in res.get("items", []):
            stats = item["statistics"]
            snippet = item["snippet"]

            subs = int(stats.get("subscriberCount", 0))
            views = int(stats.get("viewCount", 0))
            videos = int(stats.get("videoCount", 0))

            # Filtering
            if subs < 1000 or videos < 10:
                continue

            # Scoring (log normalized)
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

    # Sort and return top 5
    channels.sort(key=lambda x: x["score"], reverse=True)
    return channels[:5]
