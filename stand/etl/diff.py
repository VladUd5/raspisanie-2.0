"""Сравнение двух версий расписания: что добавили, отменили, изменили, перенесли.

Слот — (институт, форма, группа, дата, день, время, верхняя/нижняя неделя, подгруппа).
Содержимое слота — множество занятий «тип · дисциплина · преподаватели · аудитории» после
очистки и склейки написаний, поэтому разное написание одного и того же изменением не считается.

Заочники (занятия с датами): неделя сессии, которой раньше не было, — публикация
(week_published), а не поштучные добавления; пропавшая будущая неделя — week_removed.
Внутри недели сравниваются только даты не раньше дня сбора: прошедшее — история.
"""
from datetime import date

import pandas as pd

from labels import SHORT_DAYS

GROUP = ["institute", "study_form", "group_name"]
KEY = GROUP + ["date", "day_idx", "time_from", "week_type", "subgroup"]
COLUMNS = ["kind", *KEY, "session_week", "before", "after", "teachers", "rooms"]
WEEK_MARK = {"numerator": " [верх.]", "denominator": " [нижн.]", "both": ""}
SLOT_KINDS = {"added", "removed", "changed", "moved"}


def _slots(lessons: pd.DataFrame, teachers: pd.DataFrame, rooms: pd.DataFrame) -> pd.DataFrame:
    """Одна строка на слот: content — кортеж описаний занятий, teachers/rooms — для фильтров."""
    if lessons.empty:
        return pd.DataFrame(columns=KEY + ["session_week", "content", "teachers", "rooms"])
    tt = teachers.groupby("lesson_id")["teacher"].apply(lambda s: ", ".join(sorted(set(s)))).rename("t")
    rr = rooms.assign(label=rooms["room_building"] + " " + rooms["room"]).groupby("lesson_id")["label"] \
        .apply(lambda s: ", ".join(sorted(set(s)))).rename("r")
    df = lessons.merge(tt, on="lesson_id", how="left").merge(rr, on="lesson_id", how="left")
    df["t"], df["r"] = df["t"].fillna(""), df["r"].fillna("")
    df["subgroup"] = pd.to_numeric(df["subgroup"], errors="coerce").fillna(0).astype(int)
    df["desc"] = [" · ".join(x for x in (f"{lt} {d}", t, r) if x.strip())
                  for lt, d, t, r in zip(df["lesson_type"], df["discipline"], df["t"], df["r"])]
    out = df.groupby(KEY, dropna=False).agg(
        session_week=("session_week", "first"),
        content=("desc", lambda s: tuple(sorted(set(s)))),
        teachers=("t", lambda s: ", ".join(sorted({x for v in s for x in v.split(", ") if x}))),
        rooms=("r", lambda s: ", ".join(sorted({x for v in s for x in v.split(", ") if x}))),
    ).reset_index()
    return out


def slot_title(r) -> str:
    """«пн 12.10 10:10 [верх.]» — где и когда, без группы."""
    day = SHORT_DAYS[r.day_idx] if 0 <= r.day_idx < len(SHORT_DAYS) else "?"
    when = f"{day} {r.date[8:10]}.{r.date[5:7]}" if r.date else day
    sub = f" (подгр. {r.subgroup})" if r.subgroup else ""
    return f"{when} {r.time_from}{WEEK_MARK.get(r.week_type, '')}{sub}"


def _text(r, content) -> str:
    return f"{slot_title(r)}: {' ║ '.join(content)}" if content else ""


def compare(old: pd.DataFrame, new: pd.DataFrame, today: date, major_ratio: float = 0.3) -> pd.DataFrame:
    """old/new — результат slots() двух версий. → строки изменений (колонки COLUMNS)."""
    rows: list[dict] = []
    t = today.isoformat()

    def weeks(s: pd.DataFrame) -> set[tuple]:
        d = s[s["session_week"] != ""]
        return set(map(tuple, d[GROUP + ["session_week"]].drop_duplicates().values.tolist()))

    w_old, w_new = weeks(old), weeks(new)
    for key in sorted(w_new - w_old):
        part = new[(new[GROUP + ["session_week"]].apply(tuple, axis=1) == key)]
        rows.append(dict(zip(GROUP + ["session_week"], key), kind="week_published", date="",
                         after=f"опубликовано расписание недели с {_ddmm(key[3])}: {len(part)} занятий",
                         teachers=", ".join(sorted({x for v in part["teachers"] for x in v.split(", ") if x})),
                         rooms=""))
    for key in sorted(w_old - w_new):
        part = old[(old[GROUP + ["session_week"]].apply(tuple, axis=1) == key)]
        if (part["date"] >= t).any():
            rows.append(dict(zip(GROUP + ["session_week"], key), kind="week_removed", date="",
                             before=f"неделя с {_ddmm(key[3])} снята с сайта вуза; показываем последнюю версию",
                             teachers="", rooms=""))

    def comparable(s: pd.DataFrame) -> pd.DataFrame:
        dated = s["session_week"] != ""
        both = s[GROUP + ["session_week"]].apply(tuple, axis=1).isin(w_old & w_new) if dated.any() else dated
        return s[~dated | (both & (s["date"] >= t))]

    a, b = comparable(old), comparable(new)
    a, b = _drop_week_splits(a, b)
    m = a.merge(b, on=KEY, how="outer", suffixes=("_o", "_n"), indicator=True)
    removed = m[m["_merge"] == "left_only"]
    added = m[m["_merge"] == "right_only"]
    both = m[(m["_merge"] == "both") & (m["content_o"] != m["content_n"])]

    # перенос: пропавшее и появившееся с тем же содержимым у той же группы (у заочки — в той же неделе)
    used_added = set()
    moved_removed = set()
    for i, r in removed.iterrows():
        cand = added[(added["institute"] == r.institute) & (added["study_form"] == r.study_form)
                     & (added["group_name"] == r.group_name)
                     & (added["session_week_n"] == r.session_week_o)
                     & (added["content_n"] == r.content_o)]
        cand = cand[~cand.index.isin(used_added)]
        if len(cand):
            j = cand.index[0]
            n = cand.loc[j]
            used_added.add(j)
            moved_removed.add(i)
            rows.append(_row("moved", r, r.session_week_o, _text(r, r.content_o), _text(n, n.content_n),
                             r.teachers_o, r.rooms_o + (", " + n.rooms_n if n.rooms_n != r.rooms_o else "")))
    for i, r in removed.iterrows():
        if i not in moved_removed:
            rows.append(_row("removed", r, r.session_week_o, _text(r, r.content_o), "", r.teachers_o, r.rooms_o))
    for j, r in added.iterrows():
        if j not in used_added:
            rows.append(_row("added", r, r.session_week_n, "", _text(r, r.content_n), r.teachers_n, r.rooms_n))
    for _, r in both.iterrows():
        rows.append(_row("changed", r, r.session_week_n, _text(r, r.content_o), _text(r, r.content_n),
                         _union(r.teachers_o, r.teachers_n), _union(r.rooms_o, r.rooms_n)))

    out = pd.DataFrame(rows, columns=COLUMNS)
    if out.empty:
        return out
    out = out.fillna({"before": "", "after": "", "date": "", "session_week": "", "teachers": "", "rooms": ""})
    # крупное обновление (новый семестр): поштучные строки формы заменяются одной
    base = a.groupby("study_form").size()
    counts = out[out["kind"].isin(SLOT_KINDS)].groupby("study_form").size()
    major = [(form, n, base.get(form, 0)) for form, n in counts.items()
             if base.get(form, 0) and n > major_ratio * base.get(form, 0)]
    if major:
        forms = [form for form, _, _ in major]
        out = out[~(out["kind"].isin(SLOT_KINDS) & out["study_form"].isin(forms))]
        out = pd.concat([out, pd.DataFrame([{
            "kind": "major_update", "study_form": form, "institute": "", "group_name": "", "date": "",
            "session_week": "", "before": "", "teachers": "", "rooms": "",
            "after": f"расписание формы «{form}» обновлено целиком: {n} изменений из {total} занятий"}
            for form, n, total in major])], ignore_index=True)
    return out.reset_index(drop=True)


def _drop_week_splits(a: pd.DataFrame, b: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Пара «каждую неделю» с несколькими вариантами («A ║ B») стала отдельными занятиями верхней
    и нижней недели из тех же вариантов — это уточнение разбора, а не изменение расписания.
    Такие слоты убираются из сравнения с обеих сторон."""
    k = GROUP + ["date", "day_idx", "time_from", "subgroup"]
    ao, bo = a[a["date"] == ""], b[b["date"] == ""]
    old_both = {tuple(r[k]): (i, set(r["content"])) for i, r in ao[ao["week_type"] == "both"].iterrows()}
    old_split = set(map(tuple, ao.loc[ao["week_type"] != "both", k].values.tolist()))
    new_both = set(map(tuple, bo.loc[bo["week_type"] == "both", k].values.tolist()))
    drop_a, drop_b = [], []
    for key, part in bo[bo["week_type"] != "both"].groupby(k):
        key = key if isinstance(key, tuple) else (key,)
        if key not in old_both or key in new_both or key in old_split:
            continue
        i, alts = old_both[key]
        if all(set(c) <= alts for c in part["content"]):
            drop_a.append(i)
            drop_b.extend(part.index)
    return a.drop(index=drop_a), b.drop(index=drop_b)


def _row(kind, r, session_week, before, after, teachers, rooms) -> dict:
    return {"kind": kind, **{k: getattr(r, k) for k in KEY}, "session_week": session_week or "",
            "before": before, "after": after, "teachers": teachers or "", "rooms": rooms or ""}


def _union(a: str, b: str) -> str:
    return ", ".join(sorted({x for v in (a, b) for x in (v or "").split(", ") if x}))


def _ddmm(iso: str) -> str:
    return f"{iso[8:10]}.{iso[5:7]}" if len(iso) == 10 else iso


slots = _slots
