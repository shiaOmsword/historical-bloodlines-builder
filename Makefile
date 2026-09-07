.DEFAULT_GOAL := help

COMPOSE ?= docker compose
PROXY_COMPOSE := $(COMPOSE) --profile proxy
PYTHON ?= python3

INPUT_FILE ?= input.xlsx
OUTPUT_NAME ?= genealogy

.PHONY: help init build build-bot up-direct up-proxy down ps \
	logs logs-bot logs-proxy restart-bot recreate-bot rebuild-bot \
	proxy-config proxy-check smoke render-eps render-pdf

help:
	@printf '%s\n' \
		'Historical Bloodlines commands:' \
		'' \
		'  make init          - initialize VPS UID/GID and data directories' \
		'  make build         - build renderer and bot images' \
		'  make build-bot     - build only the bot image' \
		'  make up-direct     - start bot with direct Telegram access' \
		'  make up-proxy      - start sing-box proxy + bot' \
		'  make down          - stop all project services' \
		'  make ps            - show Compose service status' \
		'' \
		'  make logs          - follow bot and proxy logs' \
		'  make logs-bot      - follow bot logs' \
		'  make logs-proxy    - follow proxy logs' \
		'' \
		'  make restart-bot   - restart current bot container (same env/image)' \
		'  make recreate-bot  - recreate bot and reload .env changes' \
		'  make rebuild-bot   - rebuild image and recreate bot after code changes' \
		'' \
		'  make proxy-config  - create sing-box config from a VLESS URI' \
		'  make proxy-check   - validate generated sing-box config' \
		'  make smoke         - run full Docker renderer smoke test' \
		'' \
		'  make render-eps    - render data/input/$(INPUT_FILE) to EPS package' \
		'  make render-pdf    - render data/input/$(INPUT_FILE) to PDF' \
		'' \
		'Examples:' \
		'  make recreate-bot' \
		'  make up-proxy' \
		'  make render-pdf INPUT_FILE=book.xlsx OUTPUT_NAME=book'

init:
	sh scripts/init_vps.sh

build:
	$(COMPOSE) build renderer bot

build-bot:
	$(COMPOSE) build bot

up-direct:
	$(COMPOSE) up -d bot

up-proxy:
	$(PROXY_COMPOSE) up -d proxy bot

down:
	$(PROXY_COMPOSE) down

ps:
	$(PROXY_COMPOSE) ps

logs:
	$(PROXY_COMPOSE) logs -f --tail=200 bot proxy

logs-bot:
	$(COMPOSE) logs -f --tail=200 bot

logs-proxy:
	$(PROXY_COMPOSE) logs -f --tail=200 proxy

restart-bot:
	$(COMPOSE) restart bot

recreate-bot:
	$(COMPOSE) up -d --force-recreate bot

rebuild-bot:
	$(COMPOSE) build bot
	$(COMPOSE) up -d --force-recreate bot

proxy-config:
	$(PYTHON) scripts/configure_vless_proxy.py

proxy-check:
	$(PROXY_COMPOSE) run --rm proxy check -c /etc/sing-box/config.json

smoke:
	sh scripts/docker_smoke.sh

render-eps:
	$(COMPOSE) run --rm renderer \
		-i /data/input/$(INPUT_FILE) \
		-o /data/output/$(OUTPUT_NAME).eps

render-pdf:
	$(COMPOSE) run --rm renderer \
		-i /data/input/$(INPUT_FILE) \
		-o /data/output/$(OUTPUT_NAME).pdf
