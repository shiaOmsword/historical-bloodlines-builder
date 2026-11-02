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

### VLESS + XHTTP + TLS with Xray

For a share link containing `type=xhttp&security=tls`, use the Xray sidecar instead of sing-box:

```bash
make proxy-config-xray
```

Paste the VLESS link at the hidden prompt. This creates the private, gitignored `deploy/proxy/xray.json`; it does not overwrite the sing-box configuration. The generator transfers the server, port, UUID, SNI, fingerprint, ALPN, XHTTP Host, path, mode and optional JSON `extra`. Query values are URL-decoded once. An omitted mode uses `auto`. This Xray generator supports XHTTP with TLS and `encryption=none`; use the existing sing-box generator for other transports. TLS certificate verification remains enabled.

Set the same proxy address in `.env`:

```dotenv
TELEGRAM_PROXY_URL=socks5://proxy:1080
```

Then validate and start:

```bash
make proxy-check-xray
make up-xray
make logs
```

`make proxy-check-xray` checks the config with Xray itself; it does not test connectivity to the remote node. `make up-xray` recreates both proxy and bot, reloads `.env` and applies regenerated proxy settings. Send `/start` and a workbook to verify the complete Telegram path.

This mode uses `compose.xray.yaml` over the base Compose file and replaces the same `proxy` service, so there is no second SOCKS listener or published host port. The official Xray image runs with the checkout UID/GID to read the configuration with mode `0600`. The VPS needs network access to the VLESS endpoint and a certificate valid for the link's SNI.

After changing the VLESS link, repeat `make proxy-config-xray`, `make proxy-check-xray` and `make up-xray`. Normal bot-only updates (`make recreate-bot` / `make rebuild-bot`), logs, status and `make down` also work with this mode. Use `make up-xray` to start the proxy again after stopping the project; `make up-proxy` selects sing-box instead.

To switch back to sing-box, generate/check its configuration with `make proxy-config` and `make proxy-check`, then run `make up-proxy`.

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
