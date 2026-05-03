"""
Generate a Prefab scatter chart for top videos: X = view count, Y = like count.

Run standalone:
  python video_views_prefab.py --channel https://www.youtube.com/@3blue1brown
  python video_views_prefab.py --channel https://www.youtube.com/@3blue1brown --no-serve
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from channels_bubble_prefab import PrefabServer
from plot_prefab import build_prefab_plot as _build_prefab_plot

HERE = Path(__file__).resolve().parent
DEFAULT_INPUT = HERE / "sandbox" / "top_videos.txt"
GENERATED = HERE / "generated_plot.py"
LOG_PATH = HERE / "prefab_video_views.log"


def build_video_chart_source(videos: list[dict]) -> str:
    """Delegate to the unified plot generator (LLM picks chart type from field count)."""
    return _build_prefab_plot(videos, "Top Videos — Views vs Likes")


def _int_field(s: str) -> int:
    return int(str(s).replace(",", "").strip() or 0)


def parse_top_videos_file(path: Path) -> list[dict]:
    """Parse sandbox/top_videos.txt into a list of video dicts.

    Expected multi-line block format (one blank line between entries):
      1. <title>
      URL: <url>
      Views: <int>
      Likes: <int>
      Channel: <channel_title>
      ChannelURL: <channel_url>
    """
    if not path.is_file():
        raise FileNotFoundError(f"Missing input file: {path}")
    rows: list[dict] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    i, n = 0, len(lines)
    while i < n:
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        title_m = re.match(r"^(?:\d+\.\s*)?(?P<title>.+)$", line)
        if not title_m:
            i += 1
            continue
        title = title_m.group("title").strip()
        block: dict[str, str] = {}
        i += 1
        while i < n:
            nxt = lines[i].strip()
            if not nxt:
                i += 1
                break
            if ":" not in nxt:
                break
            key, val = nxt.split(":", 1)
            block[key.strip().lower()] = val.strip()
            i += 1
        if "url" not in block:
            continue
        rows.append(
            {
                "video_id": "",
                "title": title,
                "url": block.get("url", ""),
                "view_count": _int_field(block.get("views", "0")),
                "like_count": _int_field(block.get("likes", "0")),
                "channel_title": block.get("channel", ""),
                "channel_url": block.get("channelurl", ""),
            }
        )
    if not rows:
        raise ValueError(f"No video rows found in {path}")
    return rows


def generate_app_from_file(input_path: Path) -> int:
    """Parse a top_videos.txt dump and write the generated Prefab app. Returns row count."""
    rows = parse_top_videos_file(input_path)
    if not rows:
        raise SystemExit("No video rows parsed — nothing to plot.")
    source = build_video_chart_source(rows)
    compile(source, str(GENERATED), "exec")
    GENERATED.write_text(source, encoding="utf-8")
    return len(rows)


def generate_app_from_videos(videos: list[dict]) -> None:
    """Write the generated Prefab app to GENERATED."""
    source = build_video_chart_source(videos)
    compile(source, str(GENERATED), "exec")
    GENERATED.write_text(source, encoding="utf-8")


def main() -> None:
    import time

    ap = argparse.ArgumentParser(description="Generate Prefab views-vs-likes chart for a YouTube channel")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--channel", help="YouTube channel URL or UC... id (fetches live data)")
    group.add_argument("--input", type=Path, default=None, help="Read from an existing top_videos.txt dump")
    ap.add_argument("--top-n", type=int, default=5, help="Number of top videos when using --channel (default 5)")
    ap.add_argument("--no-serve", action="store_true", help="Only write generated file, don't serve")
    args = ap.parse_args()

    if args.input:
        print(f"Reading from {args.input} …")
        row_count = generate_app_from_file(args.input)
    else:
        from youtube_video_stats import get_top_videos_with_stats
        print(f"Fetching top {args.top_n} videos for {args.channel} …")
        videos = get_top_videos_with_stats(args.channel, top_n=args.top_n)
        if not videos:
            raise SystemExit("No videos found.")
        print(f"Got {len(videos)} videos. Generating Prefab app …")
        generate_app_from_videos(videos)
        row_count = len(videos)

    print(f"Wrote {GENERATED.name} ({row_count} videos)")

    if args.no_serve:
        print("Skipping prefab serve (--no-serve). Run: prefab serve generated_video_views.py")
        return

    LOG_PATH.write_text("", encoding="utf-8")
    server = PrefabServer(GENERATED, LOG_PATH)
    print(f"Starting Prefab (logs → {LOG_PATH.name}) …")
    server.start()
    time.sleep(1.5)
    print("Open the URL printed by prefab (often http://127.0.0.1:5175) in your browser.")
    print("Press Ctrl+C to stop.\n")
    try:
        while True:
            time.sleep(1)
            if server._proc and server._proc.poll() is not None:
                print("Prefab process exited.")
                break
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()


if __name__ == "__main__":
    main()
