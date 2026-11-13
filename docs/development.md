# Разработка и проверки

Проект использует Python 3.12+, Poetry, Graphviz и CairoSVG. Порядок установки
зависимостей описан в [локальном запуске](local-run.md). Изменения общего
генератора влияют и на CLI, и на Telegram-бота.

## Где искать код

| Каталог / файл | Содержимое |
| --- | --- |
| `src/historical_bloodlines/domain/` | Люди, ключи, отношения, агрегат родословной |
| `src/historical_bloodlines/application/dto/` | Представления входных и разобранных строк |
| `src/historical_bloodlines/application/services/` | Parser, resolver, assembler, общий use case |
| `src/historical_bloodlines/infrastructure/excel/` | Reader XLSX |
| `src/historical_bloodlines/infrastructure/graph/` | Валидация, раскладка, маршруты и renderer |
| `src/historical_bloodlines/infrastructure/pdf.py` | Масштабирование и объединение PDF |
| `src/historical_bloodlines/config/` | Пути, Graphviz runtime, версия и загрузка YAML |
| `src/historical_bloodlines/presentation/telegram/` | Aiogram, настройки доступа, VLESS-конвертеры и генерация комплекта |
| `src/historical_bloodlines/presentation/launcher/` | Rich UI, маршрутизация, диалоги и self-test |
| `src/historical_bloodlines/cli.py` | Typer CLI |
| `config/` | Пресеты рендера, без секретов |
| `scripts/` | Подготовка VPS, прокси, smoke, сравнение пресетов, сборка Windows |

Подробности моделей и активного renderer: [архитектура](architecture.md).

## Тесты

```bash
poetry install
poetry run pytest -q
poetry build
```

Примеры целевых запусков:

```bash
poetry run pytest -q tests/test_pipeline.py
poetry run pytest -q tests/test_render_config.py tests/test_telegram_support.py
poetry run pytest -q tests/test_publisher_review_geometry.py tests/test_notes_and_marriage_alignment.py
```

| Набор | Что проверяет |
| --- | --- |
| `test_pipeline.py` | Чтение, разбор, сборку отношений и генерацию результатов |
| `test_render_config.py` | Значения/приоритеты YAML, валидацию, изоляцию и перечитывание на задание |
| `test_telegram_support.py` | Разбор allowlist, VLESS-конвертеры, генератор приватного конфига |
| Геометрические regression-тесты | Конкретные родственные топологии, оси браков, линии и конфликты |
| `test_notes_and_marriage_alignment.py`, `test_label_layout.py` | Сноски, подписи и их форматирование |
| `test_launcher_navigation.py`, `test_portable_runtime.py` | Навигацию UI и работу portable runtime |

Эти тесты не заменяют live-проверку polling и отправки документов через Telegram.

## Проверки рендера

Контейнерный smoke:

```bash
make smoke
```

Он создаёт EPS, PNG-превью и PDF из примера. Сравнение пресетов:

```bash
poetry run python scripts/compare_render_configs.py examples/input.example.xlsx --output-dir render-qa-local --publisher
```

Каталог должен быть новым. Проверяйте отчёт и конечный размер текста на бумаге,
а для издательской задачи — также импорт EPS в целевую программу.
Синтаксическая проверка прокси отдельно:

```bash
make proxy-check-xray
```

Нужен предварительно сгенерированный Xray-конфиг; доступность удалённой ноды
этой командой не проверяется.

## Локальный запуск бота из исходников

Aiogram и SOCKS-зависимость вынесены из Poetry-зависимостей приложения
в `requirements-bot.txt`:

```bash
poetry run python -m pip install -r requirements-bot.txt
```

Экспортируйте `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USER_IDS` и при необходимости
`TELEGRAM_PROXY_URL`. Для локального запуска задайте доступный для записи
`TELEGRAM_WORK_DIR`: по умолчанию используется серверный `/data/telegram`.
При необходимости экспортируйте `BLOODLINES_RENDER_CONFIG`.

```bash
poetry run python -m historical_bloodlines.presentation.telegram.bot
```

Файл `.env` автоматически не загружается. Не запускайте локальный polling
с токеном одновременно работающего серверного бота.

## GitHub Actions и Windows

| Workflow | Назначение |
| --- | --- |
| `tests.yml` | Pytest на Python 3.12/3.13, Docker smoke, проверка Xray-конфига |
| `render-config-qa.yml` | Тесты и сравнение пресетов с сохранением артефактов |
| `windows-portable.yml` | Windows onedir-сборка по ручному запуску или тегу `v*` |

PyInstaller запускается на Windows. Сценарий сборки упаковывает Graphviz,
проверяет приложение без системных Python/Graphviz и создаёт ZIP. Полные
команды и self-test: [packaging/README.md](../packaging/README.md).

## Документация и конфиги

README описывает основные сценарии, подробности находятся в `docs/`.
`SUMMARY.md` задаёт навигацию GitBook, `.gitbook.yaml` выбирает корень и главную
страницу. При добавлении руководства обновляйте оглавление и относительные
ссылки. Файлы готовы для Git Sync; само подключение репозитория и ветки
выполняется в настройках пространства GitBook.

Не коммитьте токены, VLESS URI, реальные рабочие книги и результаты.
`data/input/`, `data/output/`, `data/telegram/`, локальные YAML и прокси JSON
исключены из Git. Общие пресеты в `config/` версионируются и должны оставаться
воспроизводимыми.
