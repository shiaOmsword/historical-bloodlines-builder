# Прокси для Telegram

Если сервер не может обращаться к Telegram напрямую, бот подключается к SOCKS5
внутри сети Compose. Сервис `proxy` отправляет трафик через VLESS. Прокси влияет
на соединения бота с Telegram, а не на весь сетевой трафик VPS.

Начальная настройка: [установка VPS](ubuntu-vps.md). Все команды выполняйте
из корня checkout после `make init`. Генератор конфига требует Python 3 на хосте.

| VLESS-ссылка | Движок | Файл |
| --- | --- | --- |
| `type=xhttp&security=tls` | Xray | `deploy/proxy/xray.json` |
| TCP, WebSocket, gRPC, HTTP/H2, HTTPUpgrade | sing-box | `deploy/proxy/config.json` |

Оба варианта используют **один и тот же** сервис `proxy` и адрес
`socks5://proxy:1080`. Порт `1080` не публикуется на хост.

## Xray: VLESS + XHTTP + TLS

```bash
make proxy-config-xray
```

Вставьте `vless://` ссылку в скрытый ввод. Скрипт создаст приватный файл
`deploy/proxy/xray.json` с правами `0600`, где они поддерживаются. Ссылка не
попадёт в историю команд. Файл sing-box при этом не меняется.

В `.env` задайте:

```dotenv
TELEGRAM_PROXY_URL=socks5://proxy:1080
```

```bash
make proxy-check-xray
make up-xray
make logs
```

`make proxy-check-xray` проверяет конфиг самим Xray, но не доступность удалённой
ноды. Полная проверка — `/start` и отправка книги в Telegram.

Xray-конвертер переносит сервер, порт, UUID, SNI, fingerprint, ALPN, XHTTP Host,
path, mode и JSON-объект `extra`. Значения query декодируются один раз. Поддержаны
режимы `auto`, `packet-up`, `stream-up`, `stream-one`; без mode используется
`auto`. Нужны `type=xhttp`, `security=tls`, `encryption=none` (или отсутствие
encryption), без VLESS flow и без `allowInsecure=true`. Сертификат должен быть
действителен для SNI; при отсутствии SNI используется имя сервера.

`make up-xray` использует `compose.xray.yaml` поверх `compose.yaml`, заменяя
движок того же сервиса. Команда пересоздаёт прокси и бота, перечитывает `.env`
и запускает Xray с UID/GID владельца checkout для чтения приватного конфига.

После изменения ссылки повторите:

```bash
make proxy-config-xray
make proxy-check-xray
make up-xray
```

## sing-box

Генератор поддерживает plain TCP, TLS или Reality, а также WebSocket, gRPC,
HTTP/H2 и HTTPUpgrade. Для Reality нужен `pbk`; учитываются `sid`, `sni` и `fp`.
XHTTP этим генератором не поддерживается — используйте Xray.

```bash
make proxy-config
```

После ввода ссылки задайте в `.env` тот же `TELEGRAM_PROXY_URL`:

```bash
make proxy-check
make up-proxy
make logs
```

При регенерации конфига уже работающего sing-box явно пересоздайте прокси:

```bash
docker compose --profile proxy up -d --force-recreate proxy bot
```

Обычный `make up-proxy` не гарантирует перечитывание изменённого содержимого
bind-mounted файла уже работающим процессом.

## Переключение и обслуживание

| Действие | Команды |
| --- | --- |
| Перейти на Xray | Сгенерировать/проверить Xray-конфиг, затем `make up-xray` |
| Перейти с Xray на sing-box | Сгенерировать/проверить sing-box-конфиг, затем `make up-proxy` |
| Вернуться к прямому доступу | Очистить `TELEGRAM_PROXY_URL` в `.env`, выполнить `make down`, затем `make up-direct` |
| Логи / статус | `make logs-proxy`, `make logs-bot`, `make ps` |
| Остановить проект | `make down` |

После остановки запускайте Xray командой `make up-xray`: `make up-proxy`
выбирает sing-box. Для обновления только бота работают `make recreate-bot` и
`make rebuild-bot`; они не меняют работающий прокси.

Для прямой команды Compose с Xray используйте оба файла:

```bash
docker compose -f compose.yaml -f compose.xray.yaml --profile proxy up -d --force-recreate proxy bot
```

Конфиги и VLESS-ссылки содержат реквизиты подключения. Файлы `deploy/proxy/*.json`
исключены из Git; сохраняйте их отдельно вместе с `.env`.
