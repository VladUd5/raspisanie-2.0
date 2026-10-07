"""HTML карточек «канон → написания» для страницы «Словарь написаний».

Разница показана полупрозрачной подложкой цвета палитры и начертанием, текст
остаётся обычного цвета (цвет — не единственный признак): лишнее зачёркнуто,
недостающее подчёркнуто в скобках, заменённое — жирным. Пробелы в разнице
показаны знаком «␣»."""
import html

import pandas as pd

from charts.common import NEUTRAL, SERIES
from etl.variants import diff_spans

MARK = {"словарь": "", "словарь?": "?", "правило": "не проверено", "как есть": "не проверено", "разбор": ""}
_STYLE = {"лишнее": "text-decoration:line-through", "недостаёт": "text-decoration:underline",
          "замена": "font-weight:700"}


def _tints(mode: str) -> dict[str, str]:
    s = SERIES[mode]
    return {"лишнее": s[1] + "40", "замена": s[3] + "40", "недостаёт": s[2] + "40"}   # 25% непрозрачности


def diff_html(spelling: str, canonical: str, mode: str = "light") -> str:
    tints, out = _tints(mode), []
    for op, text in diff_spans(spelling, canonical):
        if op == "равно":
            out.append(html.escape(text))
            continue
        t = html.escape(text).replace(" ", "␣")
        shown = f"[{t}]" if op == "недостаёт" else t
        out.append(f'<span style="background:{tints[op]};{_STYLE[op]};border-radius:2px" title="{op}">{shown}</span>')
    return "".join(out)


def legend_html(mode: str = "light") -> str:
    tints = _tints(mode)
    items = [("лишнее", "лишнее"), ("недостаёт", "[недостаёт]"), ("замена", "заменено")]
    spans = " · ".join(f'<span style="background:{tints[op]};{_STYLE[op]};border-radius:2px">{label}</span>'
                       for op, label in items)
    return f"Подсветка разницы: {spans} · ␣ — пробел"


def card_html(canonical: str, rows: pd.DataFrame, mode: str = "light") -> str:
    total = int(rows["uses"].sum())
    head = (f'<div style="font-weight:600;margin-bottom:4px">{html.escape(canonical)}'
            f'<span style="color:{NEUTRAL};font-weight:400"> · {len(rows)} напис. · {total} занятий</span></div>')
    body = []
    for r in rows.itertuples():
        is_canon = r.shown == r.target
        spelling = html.escape(r.shown) if is_canon else diff_html(r.shown, r.target, mode)
        kinds = "канон" if is_canon else html.escape(r.error_kinds or "")
        note = html.escape(r.note or "", quote=True)
        body.append(f'<tr title="{note}"><td style="font-family:monospace;padding:1px 16px 1px 0;border:none">{spelling}</td>'
                    f'<td style="color:{NEUTRAL};padding-right:16px;border:none">{kinds}</td>'
                    f'<td style="text-align:right;padding-right:16px;border:none">{int(r.uses)}</td>'
                    f'<td style="color:{NEUTRAL};border:none">{html.escape(MARK.get(r.source, ""))}</td></tr>')
    return head + '<table style="border-collapse:collapse;border:none">' + "".join(body) + "</table>"
