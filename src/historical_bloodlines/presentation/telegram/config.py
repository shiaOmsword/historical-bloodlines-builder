from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class TelegramBotConfigurationError(RuntimeError):
    """Raised when required Telegram bot settings are missing or invalid."""


def _parse_allowed_user_ids(raw_value: str) -> frozenset[int]:
    values: set[int] = set()
    for item in raw_value.split(","):
        normalized = item.strip()
        if not normalized:
            continue
        try:
            values.add(int(normalized))
        except ValueError as exc:
            raise TelegramBotConfigurationError(
                "TELEGRAM_ALLOWED_USER_IDS must contain comma-separated integer IDs"
            ) from exc
    return frozenset(values)


@dataclass(frozen=True, slots=True)
class TelegramBotSettings:
    token: str
    allowed_user_ids: frozenset[int]
    proxy_url: str | None
    work_directory: Path
    max_upload_bytes: int = 20 * 1024 * 1024

    def is_allowed(self, user_id: int | None) -> bool:
        return user_id is not None and user_id in self.allowed_user_ids


def load_telegram_bot_settings() -> TelegramBotSettings:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise TelegramBotConfigurationError("TELEGRAM_BOT_TOKEN is required")

    allowed_user_ids = _parse_allowed_user_ids(
        os.getenv("TELEGRAM_ALLOWED_USER_IDS", "")
    )
    if not allowed_user_ids:
        raise TelegramBotConfigurationError(
            "TELEGRAM_ALLOWED_USER_IDS must contain at least one Telegram user ID"
        )

    proxy_url = os.getenv("TELEGRAM_PROXY_URL", "").strip() or None
    work_directory = Path(
        os.getenv("TELEGRAM_WORK_DIR", "/data/telegram")
    ).expanduser()
    max_upload_mb = os.getenv("TELEGRAM_MAX_UPLOAD_MB", "20").strip()
    try:
        max_upload_bytes = int(max_upload_mb) * 1024 * 1024
    except ValueError as exc:
        raise TelegramBotConfigurationError(
            "TELEGRAM_MAX_UPLOAD_MB must be an integer"
        ) from exc

    if max_upload_bytes <= 0:
        raise TelegramBotConfigurationError(
            "TELEGRAM_MAX_UPLOAD_MB must be greater than zero"
        )

    return TelegramBotSettings(
        token=token,
        allowed_user_ids=allowed_user_ids,
        proxy_url=proxy_url,
        work_directory=work_directory,
        max_upload_bytes=max_upload_bytes,
    )
