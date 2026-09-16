from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from historical_bloodlines.application.services import GenealogyAssembler, GenealogyRowParser
from historical_bloodlines.config.render import load_render_config
from historical_bloodlines.infrastructure.excel import ExcelGenealogyReader
from historical_bloodlines.infrastructure.graph import GraphvizGenealogyRenderer


HEADERS = [
    "№",
    "Имя",
    "Титул",
    "Начало правления",
    "Конец правления",
    "Дети",
    "Брак",
    "Поколение",
    "Порядок в поколении",
]


VALOIS_PART1 = [
    [1, "Филипп III Смелый", "(1270-1285)", None, None, "1) Филипп IV Красивый; 2) Карл Валуа; 3) Людовик д’Эврё", "1) Изабелла Арагонская; 2) Мария Брабантская", 1, 20],
    [2, "Изабелла Арагонская", None, None, None, "1) Филипп IV Красивый; 2) Карл Валуа", "Филипп III Смелый", 1, 10],
    [3, "Мария Брабантская", None, None, None, "Людовик д’Эврё", "Филипп III Смелый", 1, 30],
    [4, "Людовик,", "граф д’Эврё", None, None, "Филипп III д’Эврё", None, 2, 40],
    [5, "Карл II Злой,", "король Наварры", None, None, None, None, 5, None],
    [6, "Филипп IV Красивый,", "король Франции и Наварры (1285-1314)", None, None, "Людовик X; Филипп V; Карл IV; Изабелла Французская", "Жанна I Наваррская", 2, 10],
    [7, "Карл Валуа", None, None, None, "Филипп VI Валуа ", None, 2, 30],
    [8, "Жанна I Наваррская", None, None, None, "Людовик X; Филипп V; Карл IV; Изабелла Французская", "Филипп IV Красивый", 2, 20],
    [9, "Людовик X,", "король Франции и Наварры (1314-1316)", None, None, "Иоанн I; Жанна II Наваррская", None, 3, 30],
    [10, "Филипп III,", "граф д’Эврё", None, None, "Карл II Злой", "Жанна II Наваррская", 4, None],
    [11, "Жанна II Наваррская", None, None, None, "Карл II Злой", "Филипп III д’Эврё", 4, None],
    [12, "Иоанн I,", "король Франции и Наварры (1316)", None, None, None, None, 4, None],
    [13, "Филипп V,", "король Франции и Наварры (1316-1322)", None, None, None, None, 3, 40],
    [14, "Карл IV,", "король Франции и Наварры (1322-1328)", None, None, None, None, 3, 50],
    [15, "Изабелла Французская", None, None, None, "Эдуард III", "Эдуард II ", 3, 60],
    [16, "Эдуард II,", "король Англии", None, None, "Эдуард III", "Изабелла Французская", 3, 70],
    [17, "Эдуард III,", "король Англии", None, None, None, None, 4, None],
    [18, "Филипп VI Валуа", "(1328-1350)", None, None, "Иоанн II Добрый", None, 3, None],
    [19, "Иоанн II Добрый", "(1350-1364)", None, None, None, "Бонна Люксембургская ", 4, None],
    [20, "Иоанн (Ян),", "король Чехии", None, None, "Бонна Люксембургская", None, 3, None],
    [21, "Бонна Люксембургская ", None, None, None, None, "Иоанн II Добрый", 4, None],
]


VALOIS_PART2 = [
    [19, "Иоанн II Добрый", "(1350-1364)", None, None, "Карл V Мудрый; Людовик; Жан; Филипп", "Бонна Люксембургская ", 1, 20],
    [21, "Бонна Люксембургская ", None, None, None, None, "Иоанн II Добрый", 1, 10],
    [22, "Карл V Мудрый,", "(1364-1380)", None, None, "Карл VI Безумный; Людoвик", None, 2, 10],
    [23, "Людовик,", "граф, затем герцог Анжуйский", None, None, "Вторая Анжуйская династия", None, 2, 30],
    [24, "Жан,", "герцог Беррийский и Овернский", None, None, None, None, 2, 20],
    [25, "Филипп II Смелый,", "герцог Турени (1360-1364), герцог Бургундский (1363-1404), граф Фландрии, Артуа, Невера, Ретеля и Свободного графства Бургундского (с 1384)", None, None, "Жан Бесстрашный", "Маргарита ", 2, 40],
    [26, "Маргарита,", "графиня Фландрская", None, None, "Жан Бесстрашный", "Филипп,", 2, 50],
    [27, "Карл VI Безумный,", "(1380-1422)", None, None, "Карл VII; Екатерина", "Изабелла Баварская", 3, 10],
    [28, "Людoвик,", "герцог Орлеанский", None, None, "герцоги Орлеанские", None, 3, 30],
    [29, "Изабелла Баварская", None, None, None, None, "Карл VI Безумный", 3, 20],
    [30, "Карл VII,", "(1422-1461)", None, None, "Людовик XI", "Мария Анжуйская", 4, None],
    [31, "Мария Анжуйская", None, None, None, "Людовик XI", "Карл VII", 4, None],
    [32, "Екатерина", None, None, None, "Генрих VI", "Генрих V", 4, None],
    [33, "Генрих V,", "король Англии", None, None, "Генрих VI", "Екатерина", 4, None],
    [34, "Генрих VI,", "король Англии", None, None, None, None, 5, None],
    [35, "Людовик XI", "(1461-1483)", None, None, "Карл VIII", None, 5, None],
    [36, "Карл VIII", "(1483-1498)", None, None, None, "Анна Бретонская", 6, None],
    [37, "Анна Бретонская", None, None, None, None, "Карл VIII", 6, None],
    [38, "Жан Бесстрашный,", "герцог Бургундский (1404-1419)", None, None, "Филипп III Добрый", None, 4, None],
    [39, "Филипп III Добрый,", "герцог Бургундский (1419-1467)", None, None, "Карл Смелый", None, 5, None],
    [40, "Карл Смелый,", "герцог Бургундский (1467-1477)", None, None, "Мария Бургундская", None, 6, None],
    [41, "Мария Бургундская,", "герцогиня Бургундская (1477-1482)", None, None, None, "Максимилиан I Габсбург", 7, None],
    [42, "Максимилиан I Габсбург,", "эрцгерцог Австрийский", None, None, None, "Мария Бургундская", 7, None],
]


LUXEMBOURG = [
    [1, "Генрих VI,", "граф Люксембургский", None, None, "Генрих VII; Балдуин", None, 1, None],
    [2, "Генрих VII,", "король Германии (1308-1313), император с 1312", None, None, "Иоанн (Ян)", None, 2, None],
    [3, "Балдуин,", "архиепископ Трирский", None, None, None, None, 2, None],
    [4, "Вацлав II,", "король Чехии и Польши", None, None, "Елизавета Чешская", None, 2, None],
    [5, "Иоанн (Ян),", "король Чехии (1310-1346)", None, None, "Карл (Карел) IV; Венцель", "Елизавета Чешская", 3, None],
    [6, "Елизавета Чешская", None, None, None, "Карл (Карел) IV; Венцель", "Иоанн (Ян),", 3, None],
    [7, "Карл (Карел) IV,", "король Германии и Чехии (1346-1378), император с 1355", None, None, "Венцель (Вацлав); Сигизмунд", None, 4, None],
    [8, "Венцель (Вацлав),", "король Германии (1376-1400), король Чехии (1378-1419)", None, None, None, None, 5, 10],
    [9, "Людовик (Лайош) I Анжуйский,", "король Венгрии (1342-1382)", None, None, "Мария Анжуйская", None, 4, None],
    [10, "Венцель,", "граф, затем герцог Люксембурга, герцог Брабанта и Лимбурга", None, None, None, None, 4, None],
    [11, "Сигизмунд,", "король Венгрии (1387-1437), король Германии (1410-1437), король Чехии (1419-1421, 1436-1437), император с 1433", None, None, "Елизавета", "Мария; Барбара Целльская", 5, 20],
    [12, "Мария Анжуйская", None, None, None, None, "Сигизмунд", 5, None],
    [13, "Альбрехт V Габсбург,", "герцог Австрийскимй, король Венгрии, Германии и Чехии (1438-1439)", None, None, "Ладислав (Ласло) Постум", "Елизавета", 6, None],
    [14, "Елизавета", None, None, None, "Ладислав (Ласло) Постум", "Альбрехт V Габсбург", 6, None],
    [15, "Барбара Целльская", None, None, None, "Елизавета", "Сигизмунд", 5, None],
    [16, "Ладислав (Ласло) Постум,", "герцог Австрийский (1440-1457), король Венгрии (1440, 1445-1457) и Чехии (1453-1457)", None, None, None, None, 7, None],
]


def _write_sheet(workbook: Workbook, name: str, title: str, rows: list[list[object]]) -> None:
    worksheet = workbook.create_sheet(name)
    worksheet.append(["Название", title])
    worksheet.append(HEADERS)
    for row in rows:
        worksheet.append(row)


def _publisher_book(tmp_path: Path) -> Path:
    workbook = Workbook()
    workbook.remove(workbook.active)
    _write_sheet(workbook, "люксембурги", "Династия Люксембургов", LUXEMBOURG)
    _write_sheet(workbook, "Капетинги и Валуа ч.1", "Поздние Капетинги и ранние Валуа", VALOIS_PART1)
    _write_sheet(workbook, "Капетинги и Валуа ч.2", "Поздние Валуа", VALOIS_PART2)
    path = tmp_path / "publisher-final.xlsx"
    workbook.save(path)
    return path


def test_final_publisher_rows_render_with_publisher_review_config(tmp_path) -> None:
    book = _publisher_book(tmp_path)
    reader = ExcelGenealogyReader()
    parser = GenealogyRowParser()
    assembler = GenealogyAssembler()
    renderer = GraphvizGenealogyRenderer(
        load_render_config(Path("config/render.publisher-review.yaml"))
    )

    sheets = reader.read(book)
    assert [sheet.name for sheet in sheets] == [
        "люксембурги",
        "Капетинги и Валуа ч.1",
        "Капетинги и Валуа ч.2",
    ]

    for index, sheet in enumerate(sheets, start=1):
        genealogy = assembler.assemble(parser.parse(row) for row in sheet.rows)
        renderer.render(
            genealogy,
            tmp_path / f"publisher-{index}.svg",
            title=sheet.display_title,
        )
        assert renderer.last_geometry is not None
        assert renderer.last_geometry["issues"] == ()
