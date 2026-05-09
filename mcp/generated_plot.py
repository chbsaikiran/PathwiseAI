from prefab_ui.app import PrefabApp
from prefab_ui.components import Card, CardContent, CardHeader, CardTitle, Column, Muted, Row, Text
from prefab_ui.components.charts import ChartSeries, ScatterChart

data = [
  {
    "video_id": "",
    "title": "How is Agentic AI different from GenAI?",
    "url": "https://www.youtube.com/watch?v=rAAysWLV8nk",
    "view_count": 1048310,
    "like_count": 4703,
    "channel_title": "Agentic AI with Varun",
    "channel_url": "https://www.youtube.com/@agentic-ai-with-varun"
  },
  {
    "video_id": "",
    "title": "Small Language Models will power the future of Agentic AI",
    "url": "https://www.youtube.com/watch?v=ALaLNRwhCMo",
    "view_count": 132055,
    "like_count": 2225,
    "channel_title": "Agentic AI with Varun",
    "channel_url": "https://www.youtube.com/@agentic-ai-with-varun"
  },
  {
    "video_id": "",
    "title": "Build Your First Agent with OpenAI Agent Builder",
    "url": "https://www.youtube.com/watch?v=EH9vRBmKJTs",
    "view_count": 62903,
    "like_count": 73,
    "channel_title": "Agentic AI with Varun",
    "channel_url": "https://www.youtube.com/@agentic-ai-with-varun"
  },
  {
    "video_id": "",
    "title": "2026 #ai prediction 🔮",
    "url": "https://www.youtube.com/watch?v=FAcpRJ25-Ek",
    "view_count": 51262,
    "like_count": 96,
    "channel_title": "Agentic AI with Varun",
    "channel_url": "https://www.youtube.com/@agentic-ai-with-varun"
  },
  {
    "video_id": "",
    "title": "I Built an AI Research Agent in 60 Seconds",
    "url": "https://www.youtube.com/watch?v=NKy64luWTJI",
    "view_count": 34736,
    "like_count": 14,
    "channel_title": "Agentic AI with Varun",
    "channel_url": "https://www.youtube.com/@agentic-ai-with-varun"
  }
]

colors = ["#2563eb", "#16a34a", "#f59e0b", "#db2777", "#7c3aed", "#0891b2", "#dc2626"]
color_names = ["Blue", "Green", "Amber", "Pink", "Violet", "Cyan", "Red"]

for i, row in enumerate(data):
    row["_hover"] = f"{row['title']} | {row['url']}"
    row["fill"] = colors[i % len(colors)]
    row["color_name"] = color_names[i % len(color_names)]

with PrefabApp(title="Top Videos by View Count: Agentic AI with Varun") as app:
    with Card():
        with CardHeader():
            CardTitle("Top Videos by View Count: Agentic AI with Varun")
            Muted("X: view_count · Y: like_count")
        with CardContent():
            ScatterChart(
                data=data,
                series=[ChartSeries(data_key="_hover", label="title")],
                x_axis="view_count",
                y_axis="like_count",
                height=480,
                show_legend=True,
                show_tooltip=True,
                show_grid=True,
            )
            for d in data:
                with Row():
                    Text("●", css_class=f'text-[{d["fill"]}] text-base')
                    Text(d["_hover"])