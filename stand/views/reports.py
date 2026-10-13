import streamlit as st

from config import feedback_db_path, public_url
from feedback import store as feedback

st.title("Сообщения пользователей")
st.caption("Сообщения об ошибках в расписании с сайта для студентов и преподавателей. Сообщения анонимные. "
           "Отметьте, что взяли в работу и чем закончилось — каждое действие сохраняется в журнале.")

conn = feedback.connect(feedback_db_path())
try:
    counts = feedback.counts(conn)
    shown = st.segmented_control("Показать", list(feedback.STATUSES), selection_mode="multi",
                                 default=["new", "in_progress"],
                                 format_func=lambda s: f"{feedback.STATUSES[s]} ({counts[s]})")
    reports = feedback.list_reports(conn, tuple(shown or ()))
    if not reports:
        st.info("Сообщений с такими статусами нет.")
    base = public_url()
    for r in reports:
        head = (f"№{r['id']} · {r['created_at'][:16].replace('T', ' ')} · {feedback.KINDS.get(r['kind'], r['kind'])}"
                f" · {r['group_name'] or r['teacher'] or r['room'] or ''} · {feedback.STATUSES[r['status']]}")
        with st.expander(head, expanded=r["status"] == "new"):
            st.markdown(f"**Сообщение:** {r['text'] or '—'}")
            st.caption(f"Занятие: {r['lesson_date'] or ''} {r['lesson'] or ''} · группа {r['group_name'] or '—'} · "
                       f"преподаватель {r['teacher'] or '—'} · аудитория {r['room'] or '—'}")
            if r["page"]:
                st.markdown(f"[Открыть страницу на сайте]({base}{r['page']})")
            c1, c2 = st.columns([1, 2])
            status = c1.selectbox("Статус", list(feedback.STATUSES), index=list(feedback.STATUSES).index(r["status"]),
                                  format_func=feedback.STATUSES.get, key=f"st_{r['id']}")
            note = c2.text_input("Заметка (видна только здесь)", r["staff_note"] or "", key=f"note_{r['id']}")
            if st.button("Сохранить", key=f"save_{r['id']}"):
                feedback.set_status(conn, r["id"], status, note)
                st.rerun()
            log = feedback.log(conn, r["id"])
            st.caption("Журнал: " + "; ".join(f"{x['at'][:16].replace('T', ' ')} {x['action']} {x['value']}".strip()
                                              for x in log))
finally:
    conn.close()
