# Historical Bloodlines

Генератор книжных генеалогических схем из Excel. Каждый заполненный лист книги
преобразуется в отдельную родословную, после чего проект создаёт многостраничный
PDF либо набор SVG/PNG-файлов.

Проект рассчитан не на отображение произвольного графа, а на исторические
генеалогические таблицы: поколения идут сверху вниз, супруги располагаются рядом,
дети выходят из конкретного семейного союза, а все соединения состоят только из
горизонтальных и вертикальных сегментов.

## Возможности

- чтение `.xlsx` через `openpyxl`;
- отдельная родословная для каждого листа Excel;
- A5 landscape по умолчанию для книжной печати;
- A4 landscape через параметр CLI;
- PDF, SVG и PNG;
- поддержка нескольких браков и одноимённых людей;
- один визуальный узел на человека без дублирования в разных ветвях;
- терминальные подписи ветвей, даже если для них нет отдельной строки Excel;
- явные CLI-предупреждения при создании placeholder-узлов;
- проверка циклов родительских связей через NetworkX;
- фиксированная раскладка и ручная ортогональная маршрутизация линий;
- стабильные идентификаторы: одинаковый Excel даёт воспроизводимую структуру графа;
- автоматические тесты для Python 3.12 и 3.13 в GitHub Actions.

## Требования

- Python 3.12 или новее;
- Poetry;
- системный Graphviz: команды `dot` и `neato` должны быть доступны в `PATH`.

Проверка Graphviz:

```powershell
dot -V
neato -V
```

### Установка Graphviz

Windows: установите Graphviz, добавьте каталог `bin` в `PATH` и перезапустите
PowerShell.

Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install graphviz
```

macOS:

```bash
brew install graphviz
```

## Установка проекта

Клонируйте или скачайте репозиторий, затем выполните:

```bash
cd historical-bloodlines
poetry install
```

Проверка:

```bash
poetry run pytest -q
poetry run bloodlines --help
```

## Быстрый запуск

PDF в формате A5 landscape:

```powershell
poetry run bloodlines -i data/input/input.xlsx -o data/output/genealogy.pdf
```

PDF в формате A4 landscape:

```powershell
poetry run bloodlines -i data/input/input.xlsx -o data/output/genealogy.pdf --page-format a4
```

`--paper a4` является алиасом `--page-format a4`.

SVG:

```powershell
poetry run bloodlines -i data/input/input.xlsx -o data/output/genealogy.svg
```

Если в книге несколько заполненных листов, SVG и PNG сохраняются в отдельный
каталог:

```text
data/output/genealogy/
├── 001_Династия_Комнинов.svg
├── 002_Династия_Каролингов.svg
└── ...
```

Пример входного файла находится в `examples/input.example.xlsx`.

## Формат Excel

Каждый лист представляет отдельную родословную.

Можно использовать служебную строку с полным названием:

```text
A1: Название
B1: Династия Комнинов (1081–1185)
```

Следующая строка должна содержать заголовки:

| № | Имя | Титул | Начало правления | Конец правления | Дети | Брак |
|---|---|---|---|---|---|---|

Если строка `Название` отсутствует, заголовком схемы становится имя листа.
Внутренним идентификатором строки остаётся сочетание имени листа и значения `№`.
Красивое отображаемое название не влияет на связи.

Несколько детей, супругов или титулов разделяются точкой с запятой либо переносом
строки:

```text
1) Генрих V; 2) Жоффруа Плантагенет
```

Уточнение одноимённого человека можно указать в скобках или после запятой:

```text
Альберт II (герцог)
Альберт II, герцог Австрии
```

Несколько периодов правления задаются согласованными списками начальных и
конечных годов.

## Как работает проект

```text
Excel workbook
    ↓
RawGenealogyRowDTO
    ↓
GenealogyRowParser
    ↓
ParsedGenealogyRowDTO
    ↓
GenealogyAssembler + PersonReferenceResolver
    ↓
Genealogy domain model
    ↓
NetworkXGenealogyValidator
    ↓
fixed layout + orthogonal connectors
    ↓
Graphviz neato -n2
    ↓
PDF / SVG / PNG
```

DTO переносят данные между этапами. Domain-модель хранит людей и отношения как
отдельные объекты. Связи не вкладываются в `Person`, поэтому один человек не
дублируется и не образуется циклический объектный граф.

NetworkX используется для проверки и графовых вычислений. Graphviz не решает,
где должны находиться люди и как проводить связи: приложение заранее вычисляет
все координаты и передаёт их в `neato -n2` только для создания векторного файла.

Подробное описание: [`docs/architecture.md`](docs/architecture.md).

## Структура проекта

```text
src/historical_bloodlines/
├── application/
│   ├── dto/
│   └── services/
├── domain/
├── infrastructure/
│   ├── excel/
│   ├── graph/
│   └── pdf.py
├── config/
└── cli.py
```

- `application` — сценарий сборки, parser, assembler и resolver;
- `domain` — `Person`, value objects и relation objects;
- `infrastructure/excel` — чтение Excel;
- `infrastructure/graph` — проверка, layout и Graphviz renderer;
- `infrastructure/pdf.py` — нормализация страниц A4/A5 и сборка PDF-книги;
- `cli.py` — команда `bloodlines`.

## Ключевые архитектурные решения

**Всё обрабатывается в памяти.** Excel уже является постоянным источником данных,
а файл небольшой и обрабатывается за один запуск. База данных добавила бы ORM,
миграции и транзакции без пользы для текущего сценария.

**Имя не является идентификатором.** Человек идентифицируется исходным листом и
номером строки. UUID детерминированно вычисляется из этого ключа.

**Отношения хранятся отдельно.** `MarriageRelation`, `ParentChildRelation` и
`FamilyChildRelation` содержат UUID людей и являются источником истины для
рендера.

**Сначала создаются люди, потом связи.** Двухпроходная сборка позволяет ссылаться
на человека, расположенного ниже в Excel.

**Graphviz не выполняет layout.** Это защищает схему от диагоналей, петель,
непредсказуемых изгибов и дублирования семейных узлов.

## Разработка

Запуск тестов:

```bash
poetry run pytest -q
```

Проверка сборки пакета:

```bash
poetry build
```

Перед commit не добавляйте реальные рабочие книги и результаты рендера в
`data/input` и `data/output`: эти каталоги исключены через `.gitignore`.

## Ограничения

- поддерживается только `.xlsx`;
- выходной формат — PDF, SVG или PNG;
- терминальная подпись без отдельной строки создаётся как placeholder-узел и
  фиксируется в предупреждениях сборки;
- разрешение неоднозначных имён опирается на имя, титул, уточнение и контекст
  строк Excel, поэтому исходные таблицы должны оставаться последовательными;
- системный Graphviz устанавливается отдельно от Python-пакета `graphviz`.

## Лицензия

MIT. См. [`LICENSE`](LICENSE).

## Интерактивный Rich launcher

Для запуска без ручного набора аргументов доступна отдельная интерактивная
оболочка:

```powershell
poetry run bloodlines-launcher
```

Лаунчер не заменяет обычную команду `bloodlines`, а работает поверх того же
`BuildGenealogyUseCase`. В нём доступны:

- быстрая сборка с путями из `Settings` и PDF A5;
- выбор входного Excel, PDF/SVG/PNG и выходного пути;
- выбор A5 или A4 для PDF;
- просмотр текущей конфигурации и доступности Graphviz;
- открытие каталога результатов.

Навигация построена на стеке маршрутов. Экран возвращает одну из команд
`push`, `pop`, `replace`, `reset`, `stay` или `exit`, а `Router` изменяет
историю переходов. Экраны не создают и не импортируют друг друга напрямую.

```text
MainScreen
    -> push(BuildMenu)
BuildMenuScreen
    -> push(CustomBuild)
CustomBuildScreen
    -> replace(BuildResult)
BuildResultScreen
    -> pop()
BuildMenuScreen
```

Код лаунчера находится в
`src/historical_bloodlines/presentation/launcher/`.

## Portable Windows-приложение

Для пользователей без Python и Graphviz предусмотрена `onedir`-сборка. После
распаковки архива запускается только:

```text
HistoricalBloodlines.exe
```

Внутри `_internal/graphviz` находится собственный Graphviz, поэтому системная
установка не требуется. Пользователь выбирает `.xlsx` и место сохранения через
стандартные окна Windows. После построения launcher предлагает открыть результат
или показать его в Проводнике.

Пути по умолчанию создаются в пользовательской папке «Документы»:

```text
Documents/Historical Bloodlines/
├── input/input.xlsx
└── output/genealogy.pdf
```

Переменные `BLOODLINES_DATA_DIR`, `BLOODLINES_INPUT_FILE` и
`BLOODLINES_OUTPUT_FILE` по-прежнему позволяют переопределить эти пути.

### Сборка `.exe`

PyInstaller должен запускаться на Windows. Установите Graphviz на машине
сборки, затем выполните из корня проекта:

```powershell
.\scripts\build_windows.ps1
```

Если Graphviz не добавлен в `PATH`:

```powershell
.\scripts\build_windows.ps1 -GraphvizHome "C:\Program Files\Graphviz"
```

Скрипт выполняет следующие действия:

1. устанавливает зависимости проекта и PyInstaller;
2. запускает тесты;
3. копирует полную Windows-установку Graphviz в `vendor/graphviz`;
4. создаёт `dist/HistoricalBloodlines/HistoricalBloodlines.exe`;
5. копирует portable-сборку во временный путь с пробелами;
6. убирает Python и системный Graphviz из `PATH`;
7. запускает полный self-test Excel → Graphviz → PDF;
8. создаёт `release/HistoricalBloodlines-windows-x64.zip`.

Ручной self-test готовой сборки:

```powershell
.\dist\HistoricalBloodlines\HistoricalBloodlines.exe --self-test
```

Подробности находятся в [`packaging/README.md`](packaging/README.md).

### Сборка через GitHub Actions

Workflow `.github/workflows/windows-portable.yml` запускается вручную через
`workflow_dispatch` либо при публикации тега `v*`. После успешного запуска в
Artifacts появляется архив `HistoricalBloodlines-windows-x64`.
