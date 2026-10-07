import pandas as pd

from ui.cards import card_html, diff_html


def test_diff_html_escapes_and_marks():
    html = diff_html("<Тороппова & Ко>", "<Торопова & Ко>")
    assert "&lt;" in html and "&amp;" in html and "<Тор" not in html
    assert "line-through" in html            # лишняя «п»


def test_card_html_has_every_spelling_and_note_escaped():
    rows = pd.DataFrame([{"shown": "Торопова", "target": "Торопова В.В.", "error_kinds": "нет инициалов",
                          "uses": 6, "source": "словарь?", "note": 'одна "в" институте'}])
    html = card_html("Торопова В.В.", rows)
    assert "Торопова В.В." in html and "нет инициалов" in html and "&quot;в&quot;" in html
    assert "?" in html
