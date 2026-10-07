import streamlit as st


def mode() -> str:
    """Тема интерфейса Streamlit: от неё зависят цвета графиков."""
    try:
        return st.context.theme.type or "light"
    except Exception:  # noqa: BLE001 — старые версии / AppTest
        return "light"
