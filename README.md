# Historical Bloodlines

**Из Excel — в книжные генеалогические схемы.** Каждый заполненный лист `.xlsx`
становится отдельной родословной: поколения идут сверху вниз, супруги находятся
рядом, дети связаны с конкретным союзом, линии состоят из горизонтальных и
вертикальных отрезков.

Основной сценарий — **Telegram-бот на сервере**. Пользователь отправляет книгу и
получает PDF для просмотра и ZIP с материалами для издательства. Администратор
управляет доступом, подключением к Telegram и оформлением через конфигурацию на
сервере. Тот же генератор можно запускать локально через CLI, редактируя
YAML-конфиги без Telegram и Docker.

## Выберите сценарий

| Задача | Инструкция |
| --- | --- |
| Отправить Excel работающему боту | [Telegram-бот](docs/telegram-bot.md) |
| Развернуть и обслуживать бота | [Установка на VPS](docs/ubuntu-vps.md) |
| Подключить VLESS, включая XHTTP + TLS | [Прокси для Telegram](docs/proxy.md) |
| Запустить генератор на своём компьютере | [Локальный запуск и CLI](docs/local-run.md) |
| Подготовить книгу, связи и примечания | [Формат Excel](docs/excel-format.md) |
| Изменить шрифт, интервалы или формат PDF | [Настройки рендера](docs/render-configuration.md) |
| Разобраться с ошибкой | [Диагностика](docs/troubleshooting.md) |
| Изучить устройство проекта и проверки | [Архитектура](docs/architecture.md) · [Разработка](docs/development.md) |

Полное оглавление: [SUMMARY.md](SUMMARY.md).

## Быстрый старт: Telegram-бот на VPS

Нужны Git, Make, Docker Engine и плагин Docker Compose. Для настройки VLESS
нужен Python 3 на хосте. Python приложения, Graphviz, Cairo/Pango и шрифты
устанавливаются внутри Docker-образа.

```bash
git clone https://github.com/shiaOmsword/historical-bloodlines-builder.git
cd historical-bloodlines-builder
make init
nano .env
```

В `.env` укажите токен от BotFather и числовые ID разрешённых пользователей:

```dotenv
TELEGRAM_BOT_TOKEN=123456:replace-me
TELEGRAM_ALLOWED_USER_IDS=123456789
TELEGRAM_MAX_UPLOAD_MB=20
TELEGRAM_PROXY_URL=
```

При прямом доступе сервера к Telegram:

```bash
make build-bot
make up-direct
make logs-bot
```

Для VLESS + XHTTP + TLS перед запуском настройте [Xray](docs/proxy.md).
Затем отправьте боту `/start` и файл `.xlsx`, например
[examples/input.example.xlsx](examples/input.example.xlsx).

| Результат | Содержимое |
| --- | --- |
| `genealogy.pdf` | Одна страница на родословную, A5 landscape по умолчанию |
| `genealogy_publisher.zip` | EPS с текстом в контурах, PNG-превью и снимок `render-settings.yaml` |

## Управление оформлением на сервере

Скопируйте пресет в файл, который читает бот:

```bash
cp config/render.plus2.yaml data/render.yaml
```

Изменения `data/render.yaml` применятся к **следующей отправленной книге** без
перезапуска. Настройки фиксируются на весь комплект EPS/PNG/PDF одного задания.
Можно редактировать файл вручную; параметры описаны в
[руководстве по рендеру](docs/render-configuration.md).

| Что изменили | Как применить |
| --- | --- |
| `data/render.yaml` | Отправить следующую книгу |
| Токен, список пользователей или другие значения `.env` бота | `make recreate-bot` |
| Код или зависимости | `make rebuild-bot` |
| VLESS-конфиг Xray | `make proxy-config-xray`, `make proxy-check-xray`, `make up-xray` |

## Быстрый старт: локальная генерация

Нужны Python 3.12+, Poetry и системные библиотеки рендера.
[Установка для вашей ОС и подробности CLI](docs/local-run.md).

```bash
poetry install
poetry run bloodlines -i examples/input.example.xlsx -o data/output/genealogy.pdf
```

Своя конфигурация и PDF A4:

```bash
poetry run bloodlines -i examples/input.example.xlsx -o data/output/genealogy.pdf --render-config config/render.plus2.yaml --paper a4
```

Также доступны `bloodlines-launcher` с интерактивным меню и
[portable-сборка для Windows](packaging/README.md).

## Возможности и границы

- PDF, SVG, PNG и издательский EPS; несколько листов обрабатываются за один запуск.
- Несколько браков, одноимённые люди, примечания и подсказки поколения/порядка.
- Детерминированные ID людей и проверка циклов родительских связей.
- Roboto / Roboto Medium, настраиваемые размеры текста и интервалы.
- Проверка маршрутов связей: при неразрешимом конфликте сборка завершается ошибкой.

Источником генеалогических данных остаётся Excel; отдельная БД не требуется.
В боте сейчас нет команд редактирования книги или настроек. Результаты заданий
бота временные: скачивайте их из Telegram. PDF равномерно масштабирует схему на
страницу, поэтому размер текста в YAML не равен его размеру на бумаге.

## Лицензия

[MIT](LICENSE).
