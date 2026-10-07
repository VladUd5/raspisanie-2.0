"""Человекочитаемые названия для slug-ов, которые отдаёт парсер."""
import re

INSTITUTES = {
    "institut-agrobiznesa": "Институт агробизнеса",
    "institut-genetiki-i-agronomii": "Институт генетики и агрономии",
    "institut-injenerii-i-robototexniki": "Институт инженерии и робототехники",
    "institut-biotexnologii": "Институт биотехнологии",
    "institut-veterinarnoi-mediciny-i-farmacii": "Институт ветеринарной медицины и фармации",
}
FORMS = {
    "ochnaya-forma-obucheniya": "Очная",
    "zaochnaya-forma-obucheniya": "Заочная",
    "ochno-zaochnaya-forma-obucheniya": "Очно-заочная",
}
WEEK_TYPES = {"both": "обе недели", "numerator": "числитель", "denominator": "знаменатель"}
DAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]


def building_label(slug: str) -> str:
    m = re.fullmatch(r"uk(\d+)", slug or "")
    return f"УК{m.group(1)}" if m else (slug or "—")


def institute_label(slug: str) -> str:
    return INSTITUTES.get(slug, slug or "—")


def form_label(slug: str) -> str:
    return FORMS.get(slug, slug or "—")
