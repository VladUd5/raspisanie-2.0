"""Нормализация: ключи сравнения, склейка дисциплин и преподавателей."""
_EDGE_PUNCT = " .,;:/-\u00a0"


def disc_key(name: str) -> str:
    """Ключ сравнения дисциплин: регистр, ё/е, пробелы и пунктуация по краям не важны."""
    s = name.casefold().replace("ё", "е")
    s = " ".join(s.split())
    return s.strip(_EDGE_PUNCT)
