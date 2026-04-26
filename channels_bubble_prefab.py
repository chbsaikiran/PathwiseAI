"""
Read sandbox/top_channels.txt (from the MCP dump) and render a Prefab bubble chart.

Axes (per your spec):
  X → Subscribers
  Y → Total views
  Bubble size → Video count (ScatterChart z_axis)

Pattern follows prompt_to_app.py: write a generated .py file and optionally run `prefab serve`.

Run:
  python channels_bubble_prefab.py
  python channels_bubble_prefab.py --no-serve   # only write generated file

Requires:
  pip install prefab-ui
  prefab CLI on PATH (comes with prefab-ui)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_INPUT = HERE / "sandbox" / "top_channels.txt"
GENERATED = HERE / "generated_channels_bubble.py"
LOG_PATH = HERE / "prefab_channels_bubble.log"

# Format A:
#   Title: <url>, Subscribers: N, Views: N, Videos: N, Score: S
_LINE_RE_COMMA = re.compile(
    r"^(?P<title>.+?):\s+(?P<url>https?://\S+)\s*,\s*"
    r"Subscribers:\s*(?P<subscribers>[\d,]+)\s*,\s*"
    r"Views:\s*(?P<views>[\d,]+)\s*,\s*"
    r"Videos:\s*(?P<videos>[\d,]+)\s*,\s*"
    r"Score:\s*(?P<score>[\d.]+)\s*$",
    re.IGNORECASE,
)

# Format B:
#   1. Channel Name | URL: <url> | Subscribers: N | Views: N | Videos: N | Score: S
_LINE_RE_PIPE = re.compile(
    r"^(?:\d+\.\s*)?(?P<title>[^|]+?)\s*\|\s*"
    r"URL:\s*(?P<url>https?://\S+)\s*\|\s*"
    r"Subscribers:\s*(?P<subscribers>[\d,]+)\s*\|\s*"
    r"Views:\s*(?P<views>[\d,]+)\s*\|\s*"
    r"Videos:\s*(?P<videos>[\d,]+)\s*\|\s*"
    r"Score:\s*(?P<score>[\d.]+)\s*$",
    re.IGNORECASE,
)

# Format C:
#   1. Channel Name: <url> | Subscribers: N | Views: N | Videos: N | Score: S
_LINE_RE_PIPE_COLON_URL = re.compile(
    r"^(?:\d+\.\s*)?(?P<title>.+?)\s*:\s*(?P<url>https?://\S+)\s*\|\s*"
    r"Subscribers:\s*(?P<subscribers>[\d,]+)\s*\|\s*"
    r"Views:\s*(?P<views>[\d,]+)\s*\|\s*"
    r"Videos:\s*(?P<videos>[\d,]+)\s*\|\s*"
    r"Score:\s*(?P<score>[\d.]+)\s*$",
    re.IGNORECASE,
)


def _int_field(s: str) -> int:
    return int(str(s).replace(",", "").strip() or 0)


def parse_top_channels_file(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing input file: {path}")
    rows: list[dict] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    # First pass: one-line formats (comma / pipe).
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        m = _LINE_RE_COMMA.match(line) or _LINE_RE_PIPE.match(line) or _LINE_RE_PIPE_COLON_URL.match(line)
        if m:
            title = m.group("title").strip()
            rows.append(
                {
                    "channel": title,
                    "url": m.group("url").strip(),
                    "subscribers": _int_field(m.group("subscribers")),
                    "views": _int_field(m.group("views")),
                    "videos": _int_field(m.group("videos")),
                    "score": float(m.group("score")),
                }
            )
    if rows:
        return rows

    # Second pass: multi-line block format.
    # Example:
    # 1. Channel Name
    # URL: ...
    # Subscribers: ...
    # Views: ...
    # Videos: ...
    # Score: ...
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        title_match = re.match(r"^(?:\d+\.\s*)?(?P<title>.+)$", line)
        if not title_match:
            raise ValueError(f"Could not parse line:\n{line!r}")
        title = title_match.group("title").strip()

        block: dict[str, str] = {}
        i += 1
        while i < n:
            nxt = lines[i].strip()
            if not nxt:
                i += 1
                break
            if re.match(r"^(?:\d+\.\s*)?.+$", nxt) and ":" not in nxt:
                # Next title line without blank separator.
                break
            if ":" not in nxt:
                raise ValueError(f"Could not parse line:\n{nxt!r}")
            key, val = nxt.split(":", 1)
            block[key.strip().lower()] = val.strip()
            i += 1

        required = ("url", "subscribers", "views", "videos", "score")
        missing = [k for k in required if k not in block]
        if missing:
            raise ValueError(f"Missing fields for channel {title!r}: {', '.join(missing)}")

        rows.append(
            {
                "channel": title,
                "url": block["url"],
                "subscribers": _int_field(block["subscribers"]),
                "views": _int_field(block["views"]),
                "videos": _int_field(block["videos"]),
                "score": float(block["score"]),
            }
        )

    if not rows:
        raise ValueError(f"No channel rows found in {path}")
    return rows


def build_prefab_source(rows: list[dict]) -> str:
    """Return Python source for a Prefab app using ScatterChart as bubble plot."""
    palette = ["#2563eb", "#16a34a", "#f59e0b", "#db2777", "#7c3aed", "#0891b2", "#dc2626"]
    color_names = ["Blue", "Green", "Amber", "Pink", "Violet", "Cyan", "Red"]
    chart_rows: list[dict] = []
    for idx, r in enumerate(rows, start=1):
        row = dict(r)
        color = palette[(idx - 1) % len(palette)]
        color_name = color_names[(idx - 1) % len(color_names)]
        row["channel_hover"] = f'{r["channel"]} ({r["url"]})'
        # Attempt per-point color; Recharts scatter can consume `fill` in point payload.
        row["fill"] = color
        row["bubble_color"] = color
        row["bubble_color_name"] = color_name
        chart_rows.append(row)

    data_literal = json.dumps(chart_rows, ensure_ascii=False, indent=4)
    return f'''\
from prefab_ui.app import PrefabApp
from prefab_ui.components import Card, CardContent, CardHeader, CardTitle, Column, Muted, Row, Text
from prefab_ui.components.charts import ChartSeries, ScatterChart

# Parsed from sandbox/top_channels.txt — do not edit by hand; regenerate via channels_bubble_prefab.py
data = {data_literal}

with PrefabApp(css_class="max-w-5xl mx-auto p-6") as app:
    with Card():
        with CardHeader():
            CardTitle("Top channels — bubble chart")
        with CardContent():
            with Column(gap=3):
                Muted("X-axis: subscribers · Y-axis: total views · Bubble size: number of videos")
                ScatterChart(
                    data=data,
                    # Single series prevents overplotting; per-point `fill` field controls dot color.
                    series=[ChartSeries(data_key="channel_hover", label="Channel")],
                    x_axis="subscribers",
                    y_axis="views",
                    z_axis="videos",
                    height=480,
                    show_legend=True,
                    show_tooltip=True,
                    show_grid=True,
                )
                Muted("Channel → bubble color mapping:")
                with Column(gap=1):
                    for d in data:
                        with Row(gap=2, align="center"):
                            Text("●", css_class=f'text-[{{d["bubble_color"]}}] text-base')
                            Text(f'{{d["channel"]}} ({{d["bubble_color_name"]}})')
                Muted("Hover a bubble to view channel details.")
'''


class PrefabServer:
    """Minimal subprocess wrapper (same idea as prompt_to_app.PrefabServer)."""

    def __init__(self, target: Path, log_path: Path):
        self.target = target
        self.log_path = log_path
        self._proc: subprocess.Popen | None = None
        self._log = None

    def start(self) -> None:
        self._log = open(self.log_path, "a", encoding="utf-8")
        self._log.write("\n===== channels bubble restart =====\n")
        self._log.flush()
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        self._proc = subprocess.Popen(
            ["prefab", "serve", str(self.target)],
            cwd=self.target.parent,
            stdout=self._log,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )

    def stop(self) -> None:
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(self._proc.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                    self._proc.wait(timeout=5)
                else:
                    self._proc.kill()
                    self._proc.wait()
            self._proc = None
        if self._log is not None:
            self._log.close()
            self._log = None


def generate_app_from_input(input_path: Path) -> int:
    """Parse input dump and rewrite generated app. Returns row count."""
    rows = parse_top_channels_file(input_path)
    if not rows:
        raise SystemExit("No channel rows parsed — nothing to plot.")
    source = build_prefab_source(rows)
    compile(source, str(GENERATED), "exec")
    GENERATED.write_text(source, encoding="utf-8")
    return len(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate Prefab bubble chart from top_channels.txt")
    ap.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Path to top_channels dump (default: sandbox/top_channels.txt)",
    )
    ap.add_argument("--no-serve", action="store_true", help="Only write generated_channels_bubble.py")
    args = ap.parse_args()

    row_count = generate_app_from_input(args.input)
    print(f"Wrote {GENERATED.name} ({row_count} channels)")

    if args.no_serve:
        print("Skipping prefab serve (--no-serve). Run: prefab serve generated_channels_bubble.py")
        print("If Ctrl+C does not stop `prefab serve` on Windows, run via this script without --no-serve.")
        return

    LOG_PATH.write_text("", encoding="utf-8")
    server = PrefabServer(GENERATED, LOG_PATH)
    print(f"Starting Prefab (logs → {LOG_PATH.name}) …")
    server.start()
    time.sleep(1.5)
    print("Open the URL printed by prefab (often http://127.0.0.1:5175 ) in your browser.")
    print("Press Ctrl+C here to stop the dev server.\n")
    last_mtime = args.input.stat().st_mtime if args.input.exists() else None
    try:
        while True:
            time.sleep(1)
            if server._proc and server._proc.poll() is not None:
                print("Prefab process exited.")
                break
            # Auto-refresh chart source when top_channels.txt changes.
            if args.input.exists():
                current_mtime = args.input.stat().st_mtime
                if last_mtime is None or current_mtime > last_mtime:
                    updated_rows = generate_app_from_input(args.input)
                    last_mtime = current_mtime
                    print(
                        f"Detected update in {args.input.name}; regenerated {GENERATED.name} "
                        f"({updated_rows} channels)."
                    )
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()


if __name__ == "__main__":
    main()
