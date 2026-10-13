"""Студенческая версия: расписание группы, преподавателя, аудитории; изменения; календарь;
сообщения об ошибках. Запуск: uvicorn public.app:app (из папки stand)."""
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Form, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from collector import read_status
from config import feedback_db_path, public_url, reports_per_hour, site_title
from feedback import store as feedback
from public import ics, week
from public.data import Store, search
from public.urls import group_url, room_url, teacher_url
from semester import monday, now, today

HERE = Path(__file__).parent
app = FastAPI(title="Расписание", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
store = Store()

KIND_TITLE = {"group": "Группа", "teacher": "Преподаватель", "room": "Аудитория"}
CHANGE_LABEL = {"added": "добавлено", "removed": "отменено", "changed": "изменено", "moved": "перенесено",
                "week_published": "новая неделя", "week_removed": "неделя снята", "major_update": "новое расписание"}


def _checked() -> str:
    st = read_status()
    ts = st.get("last_success_at") or st.get("checked_at")
    if not ts:
        return ""
    t = datetime.fromisoformat(ts)
    d = t.date()
    when = "сегодня" if d == today() else "вчера" if d == today() - timedelta(days=1) else f"{d:%d.%m.%Y}"
    return f"{when} в {t:%H:%M}"


def render(request: Request, name: str, status_code: int = 200, **ctx) -> HTMLResponse:
    ctx.update(site_title=site_title(), checked=_checked(), group_url=group_url, teacher_url=teacher_url,
               room_url=room_url, change_label=CHANGE_LABEL, feedback_kinds=feedback.KINDS)
    resp = templates.TemplateResponse(request, name, ctx, status_code=status_code)
    resp.headers["Cache-Control"] = "no-cache"
    return resp


def _no_data(request: Request) -> HTMLResponse:
    return render(request, "message.html", 503, title="Данные готовятся",
                  text="Расписание ещё не загружено с сайта вуза. Загляните через несколько минут.")


def _not_found(request: Request, what: str) -> HTMLResponse:
    return render(request, "message.html", 404, title="Не найдено",
                  text=f"{what} нет в актуальном расписании. Попробуйте поиск.")


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index(request: Request, q: str = ""):
    data = store.get()
    results = search(data.index, q, limit=30) if (data and q) else []
    return render(request, "index.html", q=q, results=results, ready=data is not None,
                  recent_changes=(data.changes.head(5) if data is not None else None))


@app.get("/api/search")
def api_search(q: str = ""):
    data = store.get()
    if data is None:
        return JSONResponse([])
    return JSONResponse([{k: e[k] for k in ("kind", "label", "url", "hint")} for e in search(data.index, q)],
                        headers={"Cache-Control": "max-age=60"})


def _parse_week(value: str) -> date | None:
    try:
        return monday(date.fromisoformat(value))
    except ValueError:
        return None


def _entity(request: Request, kind: str, key, title: str, subtitle: str, ics_path: str, week_param: str):
    data = store.get()
    if data is None:
        return _no_data(request)
    rows = week.select(data.items, kind, key)
    if rows.empty:
        return _not_found(request, f"{KIND_TITLE[kind]} «{title}»")
    m = _parse_week(week_param) or week.default_monday(rows, today())
    w = week.build(data.items, rows, m, data.changes)
    subgroups = sorted({int(s) for s in rows["subgroup"] if s})
    forms = sorted(set(rows["study_form"]))
    institutes = sorted(set(rows["institute"]))
    return render(request, "entity.html", kind=kind, title=title, subtitle=subtitle, week=w, ics_path=ics_path,
                  subgroups=subgroups, forms=forms, institutes=institutes, path=request.url.path,
                  snapshot_id=data.snapshot_id, key=key if kind != "room" else f"{key[0]}, {key[1]}",
                  current_monday=week.default_monday(rows, today()), public_url=public_url())


@app.get("/g/{name:path}.ics")
def group_ics(request: Request, name: str, sub: int | None = None):
    return _ics(request, "group", name, f"Расписание {name}" + (f" (подгр. {sub})" if sub else ""),
                f"g:{name}", group_url(name), sub)


@app.get("/t/{name:path}.ics")
def teacher_ics(request: Request, name: str):
    return _ics(request, "teacher", name, f"Расписание: {name}", f"t:{name}", teacher_url(name), None)


def _ics(request, kind, key, cal_name, scope, page, sub):
    data = store.get()
    if data is None:
        return Response("Данные готовятся", status_code=503)
    rows = week.select(data.items, kind, key)
    if rows.empty:
        return Response("Не найдено", status_code=404)
    base = public_url() or str(request.base_url).rstrip("/")
    body = ics.calendar(cal_name, data.items, rows, data.changes, base + page, scope, sub)
    return Response(body, media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(key)}.ics",
                             "Cache-Control": "max-age=900"})


@app.get("/g/{name:path}", response_class=HTMLResponse)
def group_page(request: Request, name: str, week: str = ""):
    data = store.get()
    sub = ""
    if data is not None:
        part = data.items[data.items["group_name"] == name]
        sub = " · ".join(sorted(set(part["study_form"])) + sorted(set(part["institute"])))
    return _entity(request, "group", name, name, sub, group_url(name) + ".ics", week)


@app.get("/t/{name:path}", response_class=HTMLResponse)
def teacher_page(request: Request, name: str, week: str = ""):
    return _entity(request, "teacher", name, name, "Преподаватель", teacher_url(name) + ".ics", week)


@app.get("/r/{building}/{room:path}", response_class=HTMLResponse)
def room_page(request: Request, building: str, room: str, week: str = ""):
    return _entity(request, "room", (building, room), f"{building}, ауд. {room}", "Аудитория", "", week)


@app.get("/changes", response_class=HTMLResponse)
def changes_page(request: Request, q: str = "", days: int = 14):
    data = store.get()
    if data is None:
        return _no_data(request)
    ch = data.all_changes
    if not ch.empty:
        since = (today() - timedelta(days=max(1, min(days, 120)))).isoformat()
        ch = ch[ch["day"] >= since]
        if q:
            from public.data import norm
            n = norm(q)
            mask = [n in norm(g) or n in norm(t) or n in norm(r) for g, t, r in
                    zip(ch["group_name"], ch["teachers"], ch["rooms"])]
            ch = ch[mask]
    return render(request, "changes.html", changes=ch.head(500), total=len(ch), q=q, days=days)


@app.post("/report")
def report(request: Request, kind: str = Form("other"), text: str = Form(""), page: str = Form("/"),
           group_name: str = Form(""), teacher: str = Form(""), room: str = Form(""), lesson: str = Form(""),
           lesson_date: str = Form(""), snapshot_id: str = Form(""), website: str = Form("")):
    back = page if page.startswith("/") and not page.startswith("//") else "/"
    if website:                                   # ловушка: поле скрыто, его заполняют только боты
        return RedirectResponse(f"{back}{'&' if '?' in back else '?'}reported=1", status_code=303)
    if not text.strip() and kind == "other":
        return render(request, "message.html", 400, title="Сообщение пустое",
                      text="Опишите, что не так, и отправьте ещё раз.", back=back)
    ip = request.headers.get("x-real-ip") or (request.client.host if request.client else "")
    conn = feedback.connect(feedback_db_path())
    try:
        rid = feedback.add_report(conn, {"kind": kind, "text": text, "page": back, "group_name": group_name,
                                         "teacher": teacher, "room": room, "lesson": lesson,
                                         "lesson_date": lesson_date, "snapshot_id": snapshot_id or None},
                                  ip, per_hour=reports_per_hour())
    finally:
        conn.close()
    if rid is None:
        return render(request, "message.html", 429, title="Слишком много сообщений",
                      text="С этого устройства уже отправлено несколько сообщений за последний час. "
                           "Попробуйте позже.", back=back)
    return RedirectResponse(f"{back}{'&' if '?' in back else '?'}reported=1", status_code=303)
