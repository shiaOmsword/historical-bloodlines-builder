# Установка и обслуживание VPS

Основной серверный сценарий — постоянно работающий Telegram-бот в Docker.
CLI-генератор остаётся отдельным сервисом Compose для разовых запусков и проверок.
Публичный HTTP-порт, домен, nginx, PostgreSQL и Redis не требуются: бот использует
исходящий long polling к Telegram.

## Подготовка

Нужен Linux-сервер с Git, Make, Docker Engine и плагином Docker Compose.
Для скрипта настройки VLESS нужен Python 3 на хосте. На Ubuntu утилиты можно
установить так:

```bash
sudo apt-get update
sudo apt-get install --yes git make python3
docker --version
docker compose version
```

Docker установите до следующего шага и убедитесь, что текущая учётная запись
может выполнять `docker` без `sudo`. Graphviz, Cairo/Pango, Roboto и Python
приложения устанавливаются внутри образа.

```bash
sudo mkdir -p /opt/apps
sudo chown "$USER":"$(id -gn)" /opt/apps
cd /opt/apps
git clone https://github.com/shiaOmsword/historical-bloodlines-builder.git
cd historical-bloodlines-builder
make init
```

`make init` создаёт `.env`, каталоги `data/input`, `data/output`,
`data/telegram`, `deploy/proxy` и записывает UID/GID владельца checkout.
При повторном запуске обновляет только `BLOODLINES_UID` и `BLOODLINES_GID`,
сохраняя остальные значения `.env`.

## Конфигурация бота

Создайте бота через BotFather и отредактируйте `.env`:

```bash
nano .env
```

| Переменная | Значение / назначение |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Обязательный токен от BotFather |
| `TELEGRAM_ALLOWED_USER_IDS` | Обязательные числовые user ID через запятую; пустой список запрещает запуск |
| `TELEGRAM_MAX_UPLOAD_MB` | Положительное целое число; по умолчанию `20` МиБ |
| `TELEGRAM_PROXY_URL` | Пусто для прямого подключения или `socks5://proxy:1080` для sidecar |
| `BLOODLINES_UID`, `BLOODLINES_GID` | UID/GID пользователя, которому принадлежат файлы на хосте |

Пример нескольких пользователей:

```dotenv
TELEGRAM_BOT_TOKEN=123456:replace-me
TELEGRAM_ALLOWED_USER_IDS=123456789,987654321
TELEGRAM_MAX_UPLOAD_MB=20
TELEGRAM_PROXY_URL=
```

Compose передаёт `.env` сервису `bot`. В Python-приложении загрузчика `.env`
нет; при запуске вне Docker переменные нужно экспортировать в окружение.

## Сборка и первый запуск

```bash
make build-bot
make smoke
```

`make smoke` пересобирает `renderer`, копирует пример в `data/input/smoke.xlsx`
и создаёт EPS, PNG-превью и PDF в `data/output/`. Проверяется весь путь рендера,
а не только наличие `dot`. Это не проверка связи с Telegram.

Выберите сетевой режим:

| Доступ к Telegram | Настройка | Запуск |
| --- | --- | --- |
| Напрямую | `TELEGRAM_PROXY_URL=` | `make up-direct` |
| VLESS + XHTTP + TLS | [Настроить Xray](proxy.md#xray-vless--xhttp--tls) | `make up-xray` |
| Другие VLESS-транспорты | [Настроить sing-box](proxy.md#sing-box) | `make up-proxy` |

```bash
make ps
make logs-bot
```

Отправьте `/start` и `examples/input.example.xlsx` в Telegram. Должны прийти
PDF и ZIP. `Ctrl+C` завершает просмотр логов; контейнер продолжает работать.

## Изменение оформления

```bash
cp config/render.plus2.yaml data/render.yaml
nano data/render.yaml
```

`./data` смонтирован в `/data`, поэтому бот видит файл как `/data/render.yaml`.
Новый YAML применяется к следующей книге без перезапуска или сборки.
Каталог `config/` не смонтирован в контейнер и не копируется Dockerfile:
редактирование пресета в нём само по себе не меняет оформление бота.

Возврат к встроенному оформлению явным конфигом:

```bash
cp config/render.default.yaml data/render.yaml
```

Все поля и приоритеты: [настройки рендера](render-configuration.md).

## Как применять изменения

| Изменение | Действие |
| --- | --- |
| `data/render.yaml` | Следующая отправленная книга |
| Любая переменная `.env` бота | `make recreate-bot` |
| Код Python, зависимости или Dockerfile | `make rebuild-bot` |
| Перезапуск с прежним окружением и образом | `make restart-bot` |
| Новый VLESS URI Xray | `make proxy-config-xray`, `make proxy-check-xray`, `make up-xray` |

`make restart-bot` **не перечитывает `.env`**. `make recreate-bot` и
`make rebuild-bot` затрагивают только бота и не переключают работающий прокси.
После полной остановки запускайте проект командой выбранного сетевого режима.

## Обновление кода

Сначала сохраните свои конфиги и проверьте незакоммиченные изменения:

```bash
cd /opt/apps/historical-bloodlines-builder
git status --short
git checkout main
git pull --ff-only origin main
make init
make rebuild-bot
make smoke
make ps
```

При изменении Compose-настроек Xray повторно выполните `make up-xray`.
После обновления отправьте тестовую книгу боту.

## Ручной рендер на том же сервере

```bash
cp /path/to/book.xlsx data/input/book.xlsx
make render-pdf INPUT_FILE=book.xlsx OUTPUT_NAME=book
make render-eps INPUT_FILE=book.xlsx OUTPUT_NAME=book
```

Получатся `data/output/book.pdf` и каталог `data/output/book/` с EPS/PNG.
Ручной рендер тоже читает `data/render.yaml`. Для A4 только в одном запуске:

```bash
docker compose run --rm renderer -i /data/input/book.xlsx -o /data/output/book-a4.pdf --paper a4
```

## Состояние, логи и остановка

| Команда | Назначение |
| --- | --- |
| `make` | Все команды Makefile |
| `make ps` | Состояние сервисов |
| `make logs-bot` | Логи бота |
| `make logs-proxy` | Логи прокси |
| `make logs` | Логи обоих сервисов |
| `make down` | Остановить проект и удалить контейнеры/сеть Compose; файлы `data/` сохраняются |

Бот и прокси используют `restart: unless-stopped`. Не запускайте одновременно
несколько polling-процессов с одним токеном.

Сохраняйте резервные копии `.env`, `data/render.yaml`, используемого
`deploy/proxy/config.json` или `deploy/proxy/xray.json` и своих Excel-книг.
Эти локальные настройки не попадают в Git. Задания в `data/telegram/`
временные; постоянные ручные результаты лежат в `data/output/`.
