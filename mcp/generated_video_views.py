from prefab_ui.app import PrefabApp
from prefab_ui.components import Card, CardContent, CardHeader, CardTitle, Column, Muted, Row, Text
from prefab_ui.components.charts import ChartSeries, ScatterChart

data = [
  {
    "video_id": "",
    "title": "I&#39;m still astounded this is true",
    "url": "https://www.youtube.com/watch?v=P11ykXwx4-k",
    "view_count": 63372673,
    "like_count": 2666281,
    "channel_title": "3Blue1Brown",
    "channel_url": "https://www.youtube.com/@3blue1brown"
  },
  {
    "video_id": "",
    "title": "But what is a neural network? | Deep learning chapter 1",
    "url": "https://www.youtube.com/watch?v=aircAruvnKk",
    "view_count": 23024964,
    "like_count": 540625,
    "channel_title": "3Blue1Brown",
    "channel_url": "https://www.youtube.com/@3blue1brown"
  },
  {
    "video_id": "",
    "title": "But what is a Fourier series?  From heat flow to drawing with circles | DE4",
    "url": "https://www.youtube.com/watch?v=r6sGWTCMz2k",
    "view_count": 18756554,
    "like_count": 189332,
    "channel_title": "3Blue1Brown",
    "channel_url": "https://www.youtube.com/@3blue1brown"
  },
  {
    "video_id": "",
    "title": "But how does bitcoin actually work?",
    "url": "https://www.youtube.com/watch?v=bBC-nXj3Ng4",
    "view_count": 17931760,
    "like_count": 400018,
    "channel_title": "3Blue1Brown",
    "channel_url": "https://www.youtube.com/@3blue1brown"
  },
  {
    "video_id": "",
    "title": "Don&#39;t let it fool you!",
    "url": "https://www.youtube.com/watch?v=VFbyGEZLMZw",
    "view_count": 17275539,
    "like_count": 807220,
    "channel_title": "3Blue1Brown",
    "channel_url": "https://www.youtube.com/@3blue1brown"
  }
]

colors = ["red-500", "blue-500", "green-500", "yellow-500", "purple-500"]
for i, d in enumerate(data):
    d["video_hover"] = f"{d['title']} ({d['url']})"
    d["fill"] = colors[i]

with PrefabApp(title="Top Videos — Views vs Likes") as app:
    with Card():
        with CardHeader():
            CardTitle("Top Videos — Views vs Likes")
        with CardContent():
            ScatterChart(
                data=data,
                x_axis="view_count",
                y_axis="like_count",
                fill="fill",
                series=[ChartSeries(data_key="video_hover", label="Video")]
            )
            for d in data:
                with Row():
                    Text("●", css_class=f'text-{d["fill"]} text-base')
                    Text(d["title"])