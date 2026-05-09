from prefab_ui.app import PrefabApp
from prefab_ui.components import Card, CardContent, CardHeader, CardTitle, Column, Muted, Row, Text
from prefab_ui.components.charts import ChartSeries, ScatterChart

data = [
  {
    "video_id": "",
    "title": "StatQuest: Principal Component Analysis (PCA), Step-by-Step",
    "url": "https://www.youtube.com/watch?v=FgakZw6K1QQ",
    "view_count": 3591869,
    "like_count": 71418,
    "channel_title": "StatQuest with Josh Starmer",
    "channel_url": "https://www.youtube.com/@statquest"
  },
  {
    "video_id": "",
    "title": "StatQuest: Logistic Regression",
    "url": "https://www.youtube.com/watch?v=yIYKR4sgzI8",
    "view_count": 2718288,
    "like_count": 46511,
    "channel_title": "StatQuest with Josh Starmer",
    "channel_url": "https://www.youtube.com/@statquest"
  },
  {
    "video_id": "",
    "title": "StatQuest: K-means clustering",
    "url": "https://www.youtube.com/watch?v=4b5d3muPQmA",
    "view_count": 2155421,
    "like_count": 41044,
    "channel_title": "StatQuest with Josh Starmer",
    "channel_url": "https://www.youtube.com/@statquest"
  },
  {
    "video_id": "",
    "title": "The Normal Distribution, Clearly Explained!!!",
    "url": "https://www.youtube.com/watch?v=rzFX5NWojp0",
    "view_count": 2002879,
    "like_count": 34907,
    "channel_title": "StatQuest with Josh Starmer",
    "channel_url": "https://www.youtube.com/@statquest"
  },
  {
    "video_id": "",
    "title": "ROC and AUC, Clearly Explained!",
    "url": "https://www.youtube.com/watch?v=4jRBRDbJemM",
    "view_count": 1913764,
    "like_count": 44948,
    "channel_title": "StatQuest with Josh Starmer",
    "channel_url": "https://www.youtube.com/@statquest"
  }
]

colors = ["#2563eb", "#16a34a", "#f59e0b", "#db2777", "#7c3aed", "#0891b2", "#dc2626"]
color_names = ["Blue", "Green", "Amber", "Pink", "Violet", "Cyan", "Red"]

for i, row in enumerate(data):
    row["_hover"] = f"{row['title']} - {row['url']}"
    row["fill"] = colors[i % len(colors)]
    row["color_name"] = color_names[i % len(color_names)]

with PrefabApp(title="Top Videos for StatQuest") as app:
    with Card():
        with CardHeader():
            CardTitle("Top Videos for StatQuest")
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