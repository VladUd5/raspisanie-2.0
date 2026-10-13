"""Справочник кафедр: разбор страниц сайта вуза (образцы — в разметке /sveden/ и страниц кафедр)."""
import json

import directory

STRUCT = """<table><tr itemprop="structOrgUprav"><td>1</td>
<td class="struct-contact" itemprop="name"> Ботаника и экология </td>
<td itemprop="fio"> Сергеева Ирина Вячеславовна </td><td itemprop="post"> заведующий кафедрой </td>
<td itemprop="addressStr"> 410012, г. Саратов, пр-кт им. Петра Столыпина зд. 4, стр. 3. </td>
<td itemprop="site"> <a href="http://www.sgau.ru/kafedry/botanika">https://site/kafedry/botanika</a><br> </td>
<td itemprop="email"> botanika@vavilovsar.ru </td><td itemprop="divisionClauseDocLink">Положение</td>
<td> 8 (8452) 60-72-05 </td></tr>
<tr itemprop="structOrgUprav"><td>2</td><td itemprop="name">Учебный отдел</td><td itemprop="fio">Иванов</td>
<td itemprop="post">начальник отдела</td><td itemprop="addressStr">-</td><td itemprop="email">x@y.ru</td><td>-</td></tr>
</table>"""

PPS = """<table><thead><tr><th>№</th><th>ФИО</th></tr></thead><tbody>
<tr><td>1</td><td>Мохонько Юлия Михайловна</td><td>Доцент</td><td>Ботаника</td><td>высшее</td>
<td>Кандидат сельскохозяйственных наук</td><td>доцент</td><td></td></tr>
<tr><td>2</td><td>Мохонько Юлия Михайловна</td><td>Преподаватель</td><td>Ботаника</td><td>высшее</td>
<td>канд. с.-х. наук</td><td>доцент</td><td></td></tr>
<tr><td>3</td><td>Иванова Анна Петровна</td><td>Ассистент</td><td></td><td>высшее</td><td>нет</td><td>нет</td><td></td></tr>
<tr><td>4</td><td>Иванова Анна Павловна</td><td>Ассистент</td><td></td><td>высшее</td><td>нет</td><td>нет</td><td></td></tr>
</tbody></table>"""

DEP_MAIN = """<a href="https://site/kafedry/botanika/professorsko-–-prepodavatelskii-sostav">ППС</a>
<a href="https://site/kafedry/botanika/10429-kontakty">Контакты</a>
<a href="https://site/kafedry/botanika/spisok-auditorii-zakreplennyx-za-kafedroi">Аудитории</a>
<a href="https://site/kafedry/other/kontakty">чужая</a>"""
DEP_STAFF = "<h1>Состав</h1><p>Сергеева Ирина Вячеславовна, заведующая;</p><p>Мохонько Юлия Михаловна, доцент</p><footer>"
DEP_CONTACTS = "<h1>Контакты</h1><p>Мохонько Ю.М. -</p><p>mohonkoum@sgau.ru</p><footer>"
DEP_ROOMS = "<h1>Аудитории</h1><p>Заведующая кафедрой – 340</p><p>Кафедра (комнаты преподавателей) – 325, 332</p><footer>"


def fake_get(url: str) -> str:
    pages = {"https://site/sveden/struct/": STRUCT, "https://site/sveden/employees/pps/index.html": PPS,
             "https://site/kafedry/botanika": DEP_MAIN,
             "https://site/kafedry/botanika/professorsko-–-prepodavatelskii-sostav": DEP_STAFF,
             "https://site/kafedry/botanika/10429-kontakty": DEP_CONTACTS,
             "https://site/kafedry/botanika/spisok-auditorii-zakreplennyx-za-kafedroi": DEP_ROOMS}
    return pages[url]


def test_parse_struct_keeps_only_departments():
    deps = directory.parse_struct(STRUCT)
    assert len(deps) == 1
    d = deps[0]
    assert d["name"] == "Ботаника и экология" and d["email"] == "botanika@vavilovsar.ru"
    assert d["phone"] == "8 (8452) 60-72-05" and d["site"] == "https://site/kafedry/botanika"


def test_fetch_merges_typos_duplicates_rooms_and_emails():
    data = directory.fetch(get=fake_get, base="https://site")
    d = directory.Directory(data)
    p = d.person("Мохонько Ю.М.")
    assert p["full_name"] == "Мохонько Юлия Михайловна"               # опечатка на странице кафедры не плодит двойника
    assert p["post"] == "Доцент" and p["subtitle"] == "Доцент, канд. с.-х. наук"   # из двух строк — старшая должность
    assert p["department"] == "Ботаника и экология" and p["email"] == "mohonkoum@sgau.ru"
    assert p["dept"]["teacher_rooms"] == ["325", "332"]
    assert d.person("Мохонько  Ю. М.")["full_name"] == "Мохонько Юлия Михайловна"   # пробелы в инициалах
    assert d.person("Мохонько")["full_name"] == "Мохонько Юлия Михайловна"          # одна фамилия — однозначно
    assert d.person("Иванова А.П.") is None and d.person("Иванова") is None          # двое — не угадываем
    assert d.person("Сергеева И.В.")["department"] == "Ботаника и экология"


def test_refresh_keeps_old_file_when_site_fails(tmp_path, monkeypatch):
    path = tmp_path / "directory.json"
    path.write_text(json.dumps({"fetched_at": "2000-01-01T00:00:00+04:00", "departments": [], "people": []}))
    def boom(*a, **k):
        raise OSError("нет сети")
    monkeypatch.setattr(directory, "fetch", boom)
    assert "не обновлён" in directory.refresh(24, path)
    assert json.loads(path.read_text())["fetched_at"].startswith("2000")
    fresh = {"fetched_at": directory.now().isoformat(), "departments": [],
             "people": [{"full_name": "Иванов Иван Иванович", "department": ""}]}
    monkeypatch.setattr(directory, "fetch", lambda: fresh)
    assert directory.refresh(24, path).startswith("Справочник кафедр обновлён")
    assert directory.refresh(24, path) == ""                                 # свежий — не трогаем


def test_short_degree_and_names():
    assert directory.short_degree("Доктор технических наук") == "д-р техн. наук"
    assert directory.short_degree("нет") == ""
    assert directory.norm_name("Ёлкин  А. Б.") == "Елкин А.Б."
    assert directory.parse_emails("Лялина Е.В. - \n lyalinaev@sgau.ru") == {"Лялина Е.В.": "lyalinaev@sgau.ru"}
