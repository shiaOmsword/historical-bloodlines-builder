# Локальный запуск и CLI

Локально используется тот же `BuildGenealogyUseCase`, что и в Telegram-боте.
Можно править Excel и YAML на компьютере, запускать сборку и сразу смотреть
результат. Токен Telegram, прокси и сервер для этого не нужны.

## Установка из исходников

Нужны Python 3.12+ (пакет допускает версии `<4.0`) и Poetry 2.x.

```bash
git clone https://github.com/shiaOmsword/historical-bloodlines-builder.git
cd historical-bloodlines-builder
poetry install
```

Установите также системный Graphviz с `dot`, `neato` и Cairo backend,
библиотеки Cairo/Pango и шрифты Roboto / Roboto Medium. Python-пакет `graphviz`
не содержит сами исполняемые файлы Graphviz.

### Ubuntu / Debian

```bash
sudo apt-get update
sudo apt-get install --yes graphviz fontconfig fonts-roboto libcairo2 libpango-1.0-0 libpangocairo-1.0-0
dot -V
neato -V
fc-match Roboto
fc-match "Roboto Medium"
```

### Windows

Установите Graphviz и добавьте его `bin` в `PATH`, затем откройте новый
PowerShell. Для исходников также нужны доступные Cairo/Pango DLL и Roboto.
Если не хотите настраивать нативные библиотеки, используйте Docker/WSL или
[portable-сборку](../packaging/README.md).

```powershell
dot -V
neato -V
poetry run python -c "import cairosvg; print(cairosvg.__version__)"
```

### macOS

```bash
brew install graphviz cairo pango
```

Установите семейство Roboto в систему. Без нужных шрифтов Graphviz может выбрать
замену и изменить размеры подписей.

## Первая сборка

Из корня репозитория:

```bash
poetry run bloodlines --help
poetry run bloodlines -i examples/input.example.xlsx -o data/output/genealogy.pdf
```

Расширение выходного пути определяет формат:

| Команда с `-o` | Результат |
| --- | --- |
| `data/output/genealogy.pdf` | Один PDF, одна landscape-страница на заполненный лист |
| `data/output/genealogy.svg` | Каталог `data/output/genealogy/` с SVG по листам |
| `data/output/genealogy.png` | Такой же каталог с PNG |
| `data/output/genealogy.eps` | Такой же каталог с EPS и `*.preview.png` |

Для SVG/PNG/EPS **всегда создаётся каталог**, даже если в книге один лист.
Имена файлов имеют вид `001_Название.svg`. Ручной CLI не создаёт издательский
ZIP автоматически: это делает Telegram-обёртка.

```bash
poetry run bloodlines -i examples/input.example.xlsx -o data/output/genealogy.svg
poetry run bloodlines -i examples/input.example.xlsx -o data/output/genealogy.eps
poetry run bloodlines -i examples/input.example.xlsx -o data/output/genealogy-a4.pdf --paper a4
```

## Свой конфиг

Скопируйте пресет в локальный файл `render.yaml`, затем редактируйте его:

```bash
cp config/render.plus2.yaml render.yaml
poetry run bloodlines -i examples/input.example.xlsx -o data/output/custom.pdf --render-config render.yaml
```

В PowerShell вместо `cp` можно использовать `Copy-Item`. Файл `render.yaml`
в корне исключён из Git. Для воспроизводимого запуска лучше явно указывать
`--render-config`; [правила поиска и поля YAML](render-configuration.md).

## Аргументы и пути по умолчанию

| Аргумент | Назначение |
| --- | --- |
| `-i`, `--input` | Входная книга `.xlsx` |
| `-o`, `--output` | Выходной путь `.pdf`, `.svg`, `.png` или `.eps` |
| `--render-config` | Явный путь к YAML оформления |
| `--page-format`, `--paper` | `a5` или `a4`; переопределяет `pdf.page_format` для PDF |

Если не передать путь, используются настройки окружения:

| Переменная | Значение по умолчанию |
| --- | --- |
| `BLOODLINES_DATA_DIR` | Пользовательские «Документы» / `Historical Bloodlines` |
| `BLOODLINES_INPUT_FILE` | `<data_dir>/input/input.xlsx` |
| `BLOODLINES_OUTPUT_FILE` | `<data_dir>/output/genealogy.svg` |
| `BLOODLINES_RENDER_CONFIG` | Не задана; используется поиск YAML |
| `BLOODLINES_DOCUMENTS_DIR` | Системный путь «Документы»; можно переопределить базовый каталог |

Поэтому локальный CLI без `-i`/`-o` не выбирает автоматически `./data` checkout.
Файл `.env` CLI тоже не читает. В bash переменные можно задать перед командой,
в PowerShell — через `$env:BLOODLINES_DATA_DIR`.

## Launcher и Windows portable

```bash
poetry run bloodlines-launcher
```

Launcher предлагает меню сборки, выбор Excel и PDF/SVG/PNG/EPS, A5/A4 для PDF,
проверку путей и открытие результатов. Диалоги выбора файлов требуют GUI;
на сервере без рабочего стола используйте CLI. YAML загружается при создании
builder: после его изменения перезапустите launcher. Выбранный в меню A5/A4
передаётся явно и имеет приоритет над `pdf.page_format` из YAML.

Portable запускается через `HistoricalBloodlines.exe`. Распакуйте **весь**
архив в доступную для записи папку: Graphviz находится внутри `_internal`,
копирования одного EXE недостаточно. Сборка и self-test описаны
в [packaging/README.md](../packaging/README.md).

## Разовый запуск в Docker

Системные библиотеки на хосте не нужны. После `make init` и `make build`:

```bash
cp examples/input.example.xlsx data/input/input.xlsx
make render-pdf
make render-eps
```

Это доступно и на локальной машине с Docker. Полный пример установки и
прямых команд Compose: [руководство VPS](ubuntu-vps.md).
