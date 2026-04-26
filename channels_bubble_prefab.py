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
import re
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_INPUT = HERE / "sandbox" / "top_channels.txt"
GENERATED = HERE / "generated_channels_bubble.py"
LOG_PATH = HERE / "prefab_channels_bubble.log"

# Title: <url>, Subscribers: N, Views: N, Videos: N, Score: S
_LINE_RE = re.compile(
    r"^(?P<title>.+?):\s+(?P<url>https?://\S+)\s*,\s*"
    r"Subscribers:\s*(?P<subscribers>[\d,]+)\s*,\s*"
    r"Views:\s*(?P<views>[\d,]+)\s*,\s*"
    r"Videos:\s*(?P<videos>[\d,]+)\s*,\s*"
    r"Score:\s*(?P<score>[\d.]+)\s*$",
    re.IGNORECASE,
)


def _int_field(s: str) -> int:
    return int(str(s).replace(",", "").strip() or 0)


def parse_top_channels_file(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing input file: {path}")
    rows: list[dict] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _LINE_RE.match(line)
        if not m:
            raise ValueError(f"Could not parse line:\n{line!r}")
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
    return rows


def build_prefab_source(rows: list[dict]) -> str:
    """Return Python source for a Prefab app using ScatterChart as bubble plot."""
    data_literal = json.dumps(rows, ensure_ascii=False, indent=4)
    return f'''\
from prefab_ui.app import PrefabApp
from prefab_ui.components import Card, CardContent, CardHeader, CardTitle, Column, Muted
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
                    series=[ChartSeries(data_key="views", label="Top channels")],
                    x_axis="subscribers",
                    y_axis="views",
                    z_axis="videos",
                    height=480,
                    show_legend=True,
                    show_tooltip=True,
                    show_grid=True,
                )
                Muted("Hover points for channel name and URL (from tooltips).")
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
        self._proc = subprocess.Popen(
            ["prefab", "serve", str(self.target)],
            cwd=self.target.parent,
            stdout=self._log,
            stderr=subprocess.STDOUT,
        )

    def stop(self) -> None:
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait()
            self._proc = None
        if self._log is not None:
            self._log.close()
            self._log = None


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

    rows = parse_top_channels_file(args.input)
    if not rows:
        raise SystemExit("No channel rows parsed — nothing to plot.")

    source = build_prefab_source(rows)
    compile(source, str(GENERATED), "exec")
    GENERATED.write_text(source, encoding="utf-8")
    print(f"Wrote {GENERATED.name} ({len(rows)} channels)")

    if args.no_serve:
        print("Skipping prefab serve (--no-serve). Run: prefab serve generated_channels_bubble.py")
        return

    LOG_PATH.write_text("", encoding="utf-8")
    server = PrefabServer(GENERATED, LOG_PATH)
    print(f"Starting Prefab (logs → {LOG_PATH.name}) …")
    server.start()
    time.sleep(1.5)
    print("Open the URL printed by prefab (often http://127.0.0.1:5175 ) in your browser.")
    print("Press Ctrl+C here to stop the dev server.\n")
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
