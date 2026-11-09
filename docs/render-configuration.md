# Настройки рендера

Версия схемы YAML — `1`. Один конфиг управляет типографикой, интервалами и
форматом PDF для CLI и Telegram-бота. Исторические данные, родство и подсказки
поколения/порядка остаются в Excel.

## На сервере

Из корня checkout:

```bash
cp config/render.plus2.yaml data/render.yaml
nano data/render.yaml
```

Compose монтирует `./data` в `/data`. Бот читает `/data/render.yaml` один раз
перед каждой книгой: следующая отправка получит новые настройки, перезапуск
не нужен. Внутри одного задания EPS/PNG/PDF используют один неизменяемый снимок.
Он сохраняется в ZIP как `render-settings.yaml`.

Редактирование `config/render.plus2.yaml` само по себе не меняет бота:
нужно скопировать файл в `data/render.yaml`. Для возврата к базовым значениям:

```bash
cp config/render.default.yaml data/render.yaml
```

Если в `.env` бота задан `BLOODLINES_RENDER_CONFIG`, он имеет приоритет над
`/data/render.yaml`. Указывайте путь **в контейнере**, например
`/data/custom.yaml`, и применяйте изменение окружения через `make recreate-bot`.
Compose фиксирует `BLOODLINES_DATA_DIR=/data` для бота и renderer.

## Локально

```bash
poetry run bloodlines -i examples/input.example.xlsx -o data/output/custom.pdf --render-config config/render.plus2.yaml
poetry run bloodlines -i examples/input.example.xlsx -o data/output/custom-a4.pdf --render-config config/render.plus3.yaml --paper a4
```

Можно скопировать пресет в `./render.yaml` и редактировать его. CLI создаёт
новый builder при каждом запуске; launcher загружает конфиг при старте и
требует перезапуска после изменений. В launcher выбранный в меню A5/A4
передаётся явно и переопределяет `pdf.page_format`.

## Приоритет выбора

Используется первый подходящий вариант:

1. `--render-config` CLI или `render_config_path` Python API.
2. Переменная окружения `BLOODLINES_RENDER_CONFIG`.
3. `$BLOODLINES_DATA_DIR/render.yaml`, **если переменная задана** и файл существует.
4. `render.yaml` в текущем рабочем каталоге.
5. Встроенные значения.

Выбирается **один** файл, а не объединение конфигов. Пропущенные поля в нём
берутся из встроенных значений, а не из другого пресета. Отсутствующий явно
указанный файл или файл из `BLOODLINES_RENDER_CONFIG` — ошибка.
Относительные пути отсчитываются от рабочего каталога процесса.

Каталог «Документы» по умолчанию для входа/выхода сам по себе не участвует в
поиске YAML: для поиска там задайте `BLOODLINES_DATA_DIR` явно. Локальный CLI
не загружает `.env`. Сервис `renderer` тоже не получает весь `.env` автоматически;
для разового переопределения используйте аргумент CLI, например:

```bash
docker compose run --rm renderer -i /data/input/input.xlsx -o /data/output/custom.pdf --render-config /data/custom.yaml
```

## Полный базовый конфиг

```yaml
version: 1
typography:
  font_size_pt: 13.2
  line_height_pt: null
  title_font_size_pt: 19
  note_font_size_pt: 9
layout:
  person_gap_pt: 34
  component_gap_pt: 22
  layer_gap_pt: 30
  page_margin_x_pt: 18
  page_margin_y_pt: 16
  min_page_width_pt: 560
  max_text_line: 20
  max_name_line: 16
pdf:
  page_format: a5
```

| Поле | Назначение | Допустимо |
| --- | --- | --- |
| `typography.font_size_pt` | Имена, титулы, даты | 8–32 pt |
| `typography.line_height_pt` | Высота строки; `null` — автоматически | 1.05–3 × размер текста |
| `typography.title_font_size_pt` | Заголовок всей схемы | 10–48 pt |
| `typography.note_font_size_pt` | Сноски из `Примечание` | 6–24 pt |
| `layout.person_gap_pt` | Интервал между людьми | 24–200 pt |
| `layout.component_gap_pt` | Интервал между компонентами | 12–200 pt |
| `layout.layer_gap_pt` | Интервал между уровнями | 24–200 pt |
| `layout.page_margin_x_pt`, `layout.page_margin_y_pt` | Поля исходного холста | 0–200 pt |
| `layout.min_page_width_pt` | Минимальная ширина исходного холста | 100–4000 pt |
| `layout.max_text_line`, `layout.max_name_line` | Лимиты переноса текста и имён в символах | Целые 4–120 |
| `pdf.page_format` | Бумага PDF, landscape | `a5`, `a4` |

Границы включены. Семейства шрифтов в версии 1 фиксированы: Roboto и
Roboto Medium. Лимиты переноса измеряются в символах; остальные размеры —
в пунктах исходного холста. `pdf.page_format` не меняет холст EPS/SVG/PNG.

Автоматическая высота строки — `font_size_pt × 15 / 13.2` с округлением вверх
до целого. Явный дробный интервал тоже округляется вверх, чтобы измерение
подписей совпадало с целочисленными строками Graphviz.

## Пресеты

| Файл в `config/` | Основной текст | Заголовок | Сноска | Интервал строки |
| --- | --- | --- | --- | --- |
| `render.default.yaml` | 13.2 | 19 | 9 | 15 |
| `render.plus2.yaml` | 15.2 | 21 | 11 | 18 |
| `render.plus3.yaml` | 16.2 | 22 | 12 | 19 |
| `render.publisher-review.yaml` | 15.2 | 21 | 15.2 | 18 |

Все значения в таблице — native pt. Пресет `publisher-review` дополнительно
уменьшает `person_gap_pt` с 34 до 28. Это отдельный вариант для проверки
издательского оформления, а не автоматически выбранный пресет.

## Размер в YAML и размер на бумаге

PDF равномерно масштабирует исходную схему, чтобы она поместилась на A5/A4:

```python
scale = min(available_width / native_width,
            available_height / native_height,
            1.22)
printed_font_size = native_font_size * scale
```

Увеличенные подписи увеличивают и холст, поэтому `+3 pt` в YAML не означает
`+3 pt` в печатном A5. Для читаемости сравнивайте конечный PDF и при необходимости
выбирайте A4; не рассчитывайте только на размер исходного текста.

## Проверка и сравнение

Неизвестные/повторяющиеся ключи, неверные типы, неподдерживаемая версия,
YAML aliases, небезопасные теги и значения вне диапазонов отклоняются.
Максимальный размер файла — 64 КиБ. Пустой файл или только комментарии дают
встроенные значения. Конфиг не отключает проверку геометрии связей.

Для сравнения пресетов на своей книге:

```bash
poetry run python scripts/compare_render_configs.py examples/input.example.xlsx --output-dir comparison-01 --publisher
```

Каталог назначения не должен существовать. Без `--config` сравниваются
`default`, `plus2`, `plus3`; свои файлы можно передать повторяющимся аргументом
`--config path.yaml`. Скрипт сохраняет настройки, нативные PDF, общий PDF
для вариантов без ошибок и `report.json` с хешами, размерами, масштабом,
конечным размером шрифта, предупреждениями и ошибками.
`--publisher` добавляет EPS с контурами и PNG-превью. При сбое хотя бы одного
листа код завершения ненулевой. Проверка примера не гарантирует, что любая
книга с произвольными ручными ограничениями будет успешно размещена.
