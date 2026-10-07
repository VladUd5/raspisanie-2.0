import pandas as pd

from charts.common import LESSON_TYPES, SERIES, bar_by_type, bar_h, heatmap, stacked_by_type, type_colors


def test_type_colors_are_fixed_per_type():
    assert type_colors("light")["лекция"] == SERIES["light"][0]
    assert type_colors("dark")["практика"] == SERIES["dark"][1]
    assert set(type_colors("light")) == set(LESSON_TYPES)


def test_bar_h_single_series_no_legend():
    df = pd.DataFrame({"teacher": ["А", "Б", "В"], "hours": [3.0, 2.0, 1.0]})
    fig = bar_h(df, "teacher", "hours", "Топ", "часов", top=2)
    assert len(fig.data) == 1 and list(fig.data[0].y) == ["Б", "А"]   # топ-2, крупнейший сверху
    assert fig.layout.showlegend in (None, False)


def test_stacked_keeps_type_order_and_skips_empty():
    df = pd.DataFrame({"discipline": ["X", "X", "Y"], "lesson_type": ["практика", "лекция", "лекция"],
                       "hours": [1.0, 2.0, 1.5]})
    fig = stacked_by_type(df, "discipline", "hours", "t", "ч")
    assert [t.name for t in fig.data] == ["лекция", "практика"]


def test_heatmap_and_bar_by_type_build():
    p = pd.DataFrame([[1.5, 0.0]], index=["понедельник"], columns=["08:30", "10:10"])
    assert heatmap(p, "t", "ч", mode="dark").data[0].z.shape == (1, 2)
    df = pd.DataFrame({"lesson_type": ["лекция", "не определён"], "hours": [1.0, 2.0]})
    assert bar_by_type(df, "lesson_type", "hours", "t", "ч").data[0].marker.color[0] == type_colors("light")["лекция"]


def test_stacked_legend_does_not_cover_axis():
    # легенда под графиком перекрывала подписи оси X — она должна стоять над областью графика
    df = pd.DataFrame({"discipline": ["X", "X"], "lesson_type": ["практика", "лекция"], "hours": [1.0, 2.0]})
    fig = stacked_by_type(df, "discipline", "hours", "t", "ч")
    assert fig.layout.legend.yanchor == "bottom" and fig.layout.legend.y >= 1
    assert fig.layout.margin.t >= 80          # место и для заголовка, и для легенды
