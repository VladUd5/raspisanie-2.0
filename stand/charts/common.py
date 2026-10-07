"""Построители графиков Plotly. Палитра проверена на различимость, в том числе для дальтоников
(категориальные слоты 1–7, светлая и тёмная темы), последовательная шкала — синяя.
В светлой теме три цвета ниже 3:1 к фону, поэтому у каждого графика на
странице есть таблица с теми же данными."""
import pandas as pd
import plotly.graph_objects as go

SERIES = {
    "light": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7"],
    "dark": ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9"],
}
NEUTRAL = "#898781"
SURFACE = {"light": "#ffffff", "dark": "#0e1117"}          # фон Streamlit
SEQUENTIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
LESSON_TYPES = ["лекция", "практика", "лабораторная", "семинар", "консультация", "зачёт", "экзамен", "не определён"]
FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"


def type_colors(mode: str) -> dict[str, str]:
    """Цвет закреплён за типом занятия, а не за его местом в выборке."""
    return {**dict(zip(LESSON_TYPES[:7], SERIES[mode])), "не определён": NEUTRAL}


def _finish(fig: go.Figure, title: str, height: int) -> go.Figure:
    fig.update_layout(title=dict(text=title, x=0, xanchor="left"), height=height,
                      margin=dict(l=8, r=8, t=48, b=8), font=dict(family=FONT),
                      barcornerradius=4, hoverlabel=dict(font=dict(family=FONT)))
    fig.update_xaxes(showgrid=True, gridwidth=1, zeroline=False)
    fig.update_yaxes(showgrid=False, zeroline=False)
    return fig


def bar_h(df: pd.DataFrame, label: str, value: str, title: str, value_title: str,
          mode: str = "light", top: int = 20) -> go.Figure:
    """Горизонтальный рейтинг: одна серия — один цвет (слот 1), без легенды."""
    d = df.head(top).iloc[::-1]
    fig = go.Figure(go.Bar(
        x=d[value], y=d[label].astype(str), orientation="h", marker_color=SERIES[mode][0],
        hovertemplate=f"%{{y}}<br>{value_title}: %{{x:.2f}}<extra></extra>"))
    fig.update_layout(bargap=0.35)
    fig.update_xaxes(title=value_title)
    return _finish(fig, title, max(240, 26 * len(d) + 90))


def bar_by_type(df: pd.DataFrame, type_col: str, value: str, title: str, value_title: str,
                mode: str = "light") -> go.Figure:
    """Столбики по типам занятий в цветах типов (те же цвета на всех страницах)."""
    colors = type_colors(mode)
    d = df.sort_values(value)
    fig = go.Figure(go.Bar(
        x=d[value], y=d[type_col], orientation="h", marker_color=[colors.get(t, NEUTRAL) for t in d[type_col]],
        hovertemplate=f"%{{y}}<br>{value_title}: %{{x:.2f}}<extra></extra>"))
    fig.update_layout(bargap=0.35)
    fig.update_xaxes(title=value_title)
    return _finish(fig, title, max(200, 30 * len(d) + 90))


def stacked_by_type(df: pd.DataFrame, label: str, value: str, title: str, value_title: str,
                    mode: str = "light") -> go.Figure:
    """Стек по типам занятий: порядок и цвета типов фиксированы, легенда всегда есть."""
    colors = type_colors(mode)
    order = df.groupby(label)[value].sum().sort_values().index.tolist()
    fig = go.Figure()
    for t in LESSON_TYPES:
        part = df[df["lesson_type"] == t].set_index(label).reindex(order)
        if part[value].fillna(0).sum() == 0:
            continue
        fig.add_bar(x=part[value].fillna(0), y=order, orientation="h", name=t,
                    marker=dict(color=colors[t], line=dict(color=SURFACE[mode], width=1)),
                    hovertemplate=f"%{{y}}<br>{t}: %{{x:.2f}} {value_title}<extra></extra>")
    fig.update_xaxes(title=value_title)
    fig = _finish(fig, title, max(260, 26 * len(order) + 160))
    # легенда — над областью графика, под заголовком: снизу она перекрывала подписи оси
    fig.update_layout(barmode="stack", bargap=0.35, margin=dict(t=84),
                      title=dict(y=0.98, yanchor="top"),
                      legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0,
                                  traceorder="normal"))
    return fig


def heatmap(pivot: pd.DataFrame, title: str, value_title: str, mode: str = "light") -> go.Figure:
    """Последовательная одноцветная шкала: светлее — меньше (в тёмной теме наоборот)."""
    scale = SEQUENTIAL if mode == "light" else SEQUENTIAL[::-1]
    fig = go.Figure(go.Heatmap(
        z=pivot.values, x=[str(c) for c in pivot.columns], y=[str(i) for i in pivot.index],
        colorscale=[[i / (len(scale) - 1), c] for i, c in enumerate(scale)], xgap=2, ygap=2,
        colorbar=dict(title=value_title, thickness=12),
        hovertemplate=f"%{{y}} · %{{x}}<br>{value_title}: %{{z:.2f}}<extra></extra>"))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(showgrid=False, type="category")
    return _finish(fig, title, max(260, 34 * len(pivot.index) + 120))
