data = [
    {
        "video_id": "",
        "title": "Lord Narasimha is Calling You | Narasimha Jayanti 2026#narasimhajayanti #narasimhaabhishekam",
        "url": "https://www.youtube.com/watch?v=iAJZxBnJJak",
        "view_count": 24183,
        "like_count": 1089,
        "channel_title": "Hare Krishna Golden Temple",
        "channel_url": "https://www.youtube.com/@harekrishnagoldentemplehyd"
    },
    {
        "video_id": "",
        "title": "Sri Narasimha Jayanti Mega Celebration | Sri Radha Govinda Darshan #narasimhajayanti #radhagovinda",
        "url": "https://www.youtube.com/watch?v=sZLJobAJOy8",
        "view_count": 22510,
        "like_count": 5709,
        "channel_title": "Hare Krishna Golden Temple",
        "channel_url": "https://www.youtube.com/@harekrishnagoldentemplehyd"
    },
    {
        "video_id": "",
        "title": "Lord Narasimha’s Blessings Are Here 🔥 Narasimha Jayanti  Homam 2026 #narasimhajayanti",
        "url": "https://www.youtube.com/watch?v=1gIVSt0UapU",
        "view_count": 21470,
        "like_count": 1056,
        "channel_title": "Hare Krishna Golden Temple",
        "channel_url": "https://www.youtube.com/@harekrishnagoldentemplehyd"
    },
    {
        "video_id": "",
        "title": "Narasimha Jayanti 2026 | Don’t Miss This Auspicious Festival ✨ #narasimhajayanti #narasimhaswamy",
        "url": "https://www.youtube.com/watch?v=M3F0afsD0P0",
        "view_count": 21223,
        "like_count": 927,
        "channel_title": "Hare Krishna Golden Temple",
        "channel_url": "https://www.youtube.com/@harekrishnagoldentemplehyd"
    },
    {
        "video_id": "",
        "title": "Sri Lakshmi Narasimha Swamy Maha Abhishekam 🙏 #harekrishnagoldentemple #narasimhajayanti",
        "url": "https://www.youtube.com/watch?v=LG0AVlnn_FQ",
        "view_count": 10957,
        "like_count": 1470,
        "channel_title": "Hare Krishna Golden Temple",
        "channel_url": "https://www.youtube.com/@harekrishnagoldentemplehyd"
    }
]

colors = ["#2563eb", "#16a34a", "#f59e0b", "#db2777", "#7c3aed", "#0891b2", "#dc2626"]
color_names = ["Blue", "Green", "Amber", "Pink", "Violet", "Cyan", "Red"]

for i, row in enumerate(data):
    row["_hover"] = f"{row['title']} | {row['url']}"
    row["fill"] = colors[i % len(colors)]
    row["color_name"] = color_names[i % len(color_names)]

from prefab_ui.app import PrefabApp
from prefab_ui.components import Card, CardContent, CardHeader, CardTitle, Column, Muted, Row, Text
from prefab_ui.components.charts import ChartSeries, ScatterChart

with PrefabApp(title="Video Analytics") as app:
    with Card():
        with CardHeader():
            CardTitle("Top Videos — Views vs Likes")
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
                    Text("●", css_class=f"text-[{d['fill']}] text-base")
                    Text(d["_hover"])