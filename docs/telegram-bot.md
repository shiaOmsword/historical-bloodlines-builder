# Telegram generation bot

The bot is a thin presentation layer over the existing `BuildGenealogyUseCase`.
It accepts one `.xlsx` workbook and returns:

- `genealogy.pdf` — multi-page preview;
- `genealogy_publisher.zip` — publisher package with EPS files and preview PNGs.

## 1. Update the VPS

```bash
cd /opt/apps/historical-bloodlines-builder
git checkout main
git pull --ff-only origin main
make init
```

`make init` updates only `BLOODLINES_UID` / `BLOODLINES_GID` and preserves existing Telegram/proxy settings in `.env`.

## 2. Configure Telegram access

Create a bot with BotFather and copy its token.
Find the numeric Telegram user IDs of everyone who should be allowed to use the bot and put them into `.env`:

```dotenv
TELEGRAM_BOT_TOKEN=123456:replace-me
TELEGRAM_ALLOWED_USER_IDS=123456789
TELEGRAM_MAX_UPLOAD_MB=20
```

Several allowed users are comma-separated:

```dotenv
TELEGRAM_ALLOWED_USER_IDS=123456789,987654321,555555555
```

The allowlist is mandatory. The bot refuses to start if it is empty.

After changing `TELEGRAM_ALLOWED_USER_IDS`, `TELEGRAM_BOT_TOKEN`, proxy settings or any other `.env` value, recreate the bot container so Compose reloads the environment:

```bash
make recreate-bot
```

A plain `make restart-bot` restarts the existing container with its current environment and does not reload changed `.env` values.

## 3. Direct network mode

If the VPS can reach Telegram directly:

```dotenv
TELEGRAM_PROXY_URL=
```

Start the bot:

```bash
make build-bot
make up-direct
make logs-bot
```

## 4. VLESS mode for a restricted VPS

The project can run a private sing-box sidecar. Only the bot's Telegram traffic is sent through it; the whole VPS is not placed behind a tunnel.

Generate `deploy/proxy/config.json` from a normal `vless://` share link:

```bash
make proxy-config
```

The command asks for the URI without echoing it to the terminal. The generated file is gitignored and is chmod `0600` where supported.

Supported share-link modes include:

- TLS;
- Reality (`pbk`, `sid`, `sni`, `fp`);
- plain TCP;
- WebSocket;
- gRPC;
- HTTP / H2 transport;
- HTTPUpgrade.

Then set:

```dotenv
TELEGRAM_PROXY_URL=socks5://proxy:1080
```

Validate sing-box configuration:

```bash
make proxy-check
```

Start proxy and bot:

```bash
make up-proxy
```

Watch logs:

```bash
make logs
```

The proxy service does not publish port `1080` to the public host. It is reachable only inside the Compose network as `proxy:1080`.

## 5. Usage

Send `/start`, then attach an `.xlsx` workbook.

The bot:

1. verifies the Telegram user allowlist;
2. verifies `.xlsx` extension and upload size;
3. downloads the workbook into a private temporary job directory;
4. serializes rendering with one process-wide semaphore;
5. generates EPS + preview PNG and PDF through the existing application layer;
6. sends PDF and publisher ZIP back to Telegram;
7. removes the temporary job directory after sending.

Renderer warnings are included in the result message. Exceptions are written to container logs without exposing tracebacks to Telegram users.

## 6. Makefile operations

Show all commands:

```bash
make
```

Status:

```bash
make ps
```

Bot logs:

```bash
make logs-bot
```

Proxy logs:

```bash
make logs-proxy
```

Restart bot without reloading `.env`:

```bash
make restart-bot
```

Recreate bot and reload `.env` changes:

```bash
make recreate-bot
```

Rebuild image and recreate bot after code changes:

```bash
make rebuild-bot
```

Full renderer smoke test:

```bash
make smoke
```

Manual renderer usage:

```bash
make render-pdf INPUT_FILE=book.xlsx OUTPUT_NAME=book
make render-eps INPUT_FILE=book.xlsx OUTPUT_NAME=book
```

The workbook for manual rendering must be under `data/input/`.
