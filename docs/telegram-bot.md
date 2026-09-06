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
sh scripts/init_vps.sh
```

`init_vps.sh` updates only `BLOODLINES_UID` / `BLOODLINES_GID` and preserves existing Telegram/proxy settings in `.env`.

## 2. Create a Telegram bot

Create a bot with BotFather and copy its token.
Find your numeric Telegram user ID and put both values into `.env`:

```dotenv
TELEGRAM_BOT_TOKEN=123456:replace-me
TELEGRAM_ALLOWED_USER_IDS=123456789
TELEGRAM_MAX_UPLOAD_MB=20
```

Several allowed users can be comma-separated:

```dotenv
TELEGRAM_ALLOWED_USER_IDS=123456789,987654321
```

The allowlist is mandatory. The bot refuses to start if it is empty.

## 3. Direct network mode

If the VPS can reach Telegram directly:

```dotenv
TELEGRAM_PROXY_URL=
```

Start the bot:

```bash
docker compose build bot
docker compose up -d bot
docker compose logs -f bot
```

## 4. VLESS mode for a restricted VPS

The project can run a private sing-box sidecar. Only the bot's Telegram traffic is sent through it; the whole VPS is not placed behind a tunnel.

Generate `deploy/proxy/config.json` from a normal `vless://` share link:

```bash
python3 scripts/configure_vless_proxy.py
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
docker compose --profile proxy run --rm proxy check -c /etc/sing-box/config.json
```

Start proxy and bot:

```bash
docker compose --profile proxy up -d proxy bot
```

Watch logs:

```bash
docker compose logs -f proxy bot
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

## 6. Operations

Status:

```bash
docker compose ps
```

Bot logs:

```bash
docker compose logs --tail=200 bot
```

Proxy logs:

```bash
docker compose logs --tail=200 proxy
```

Restart bot:

```bash
docker compose restart bot
```

Rebuild after code updates:

```bash
docker compose build bot
docker compose up -d bot
```

For VLESS mode:

```bash
docker compose --profile proxy up -d proxy bot
```
