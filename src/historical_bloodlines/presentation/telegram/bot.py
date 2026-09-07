from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from tempfile import TemporaryDirectory

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile, Message

from historical_bloodlines.config import prepare_bundled_graphviz
from historical_bloodlines.presentation.telegram.config import (
    TelegramBotSettings,
    load_telegram_bot_settings,
)
from historical_bloodlines.presentation.telegram.generation import (
    TelegramGenerationService,
)

LOGGER = logging.getLogger(__name__)
_RENDER_SEMAPHORE = asyncio.Semaphore(1)


def _router(
    settings: TelegramBotSettings,
    generator: TelegramGenerationService,
) -> Router:
    router = Router(name="historical-bloodlines")

    async def reject_if_forbidden(message: Message) -> bool:
        user_id = message.from_user.id if message.from_user else None
        if settings.is_allowed(user_id):
            return False
        LOGGER.warning("Rejected Telegram user_id=%s", user_id)
        await message.answer("Доступ к этому боту закрыт.")
        return True

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        if await reject_if_forbidden(message):
            return
        await message.answer(
            "Пришли .xlsx файл с родословными. Я верну многостраничный PDF "
            "и ZIP для издательства с EPS + preview PNG."
        )

    @router.message(F.document)
    async def build_from_document(message: Message, bot: Bot) -> None:
        if await reject_if_forbidden(message):
            return

        document = message.document
        if document is None:
            return
        filename = document.file_name or "input.xlsx"
        if Path(filename).suffix.casefold() != ".xlsx":
            await message.answer("Нужен файл в формате .xlsx.")
            return
        if document.file_size and document.file_size > settings.max_upload_bytes:
            limit_mb = settings.max_upload_bytes // (1024 * 1024)
            await message.answer(f"Файл слишком большой. Лимит: {limit_mb} МБ.")
            return

        settings.work_directory.mkdir(parents=True, exist_ok=True)
        status = await message.answer("Файл получен. Начинаю генерацию…")

        try:
            with TemporaryDirectory(
                prefix=f"job_{message.chat.id}_",
                dir=settings.work_directory,
            ) as raw_job_directory:
                job_directory = Path(raw_job_directory)
                input_path = job_directory / "input.xlsx"
                output_directory = job_directory / "output"

                await bot.download(document, destination=input_path)

                async with _RENDER_SEMAPHORE:
                    bundle = await asyncio.to_thread(
                        generator.build,
                        input_path,
                        output_directory,
                    )

                warning_text = ""
                if bundle.warnings:
                    preview = "\n".join(
                        f"• {warning}" for warning in bundle.warnings[:10]
                    )
                    remainder = len(bundle.warnings) - 10
                    if remainder > 0:
                        preview += f"\n• …и ещё {remainder}"
                    warning_text = f"\n\nПредупреждения:\n{preview}"

                await status.edit_text(
                    f"Готово. Родословных: {bundle.genealogy_count}. "
                    f"Предупреждений: {len(bundle.warnings)}.{warning_text}"
                )
                await message.answer_document(
                    FSInputFile(bundle.pdf_path, filename="genealogy.pdf"),
                    caption="PDF-предпросмотр",
                )
                await message.answer_document(
                    FSInputFile(
                        bundle.publisher_zip_path,
                        filename="genealogy_publisher.zip",
                    ),
                    caption="Издательский пакет: EPS + preview PNG",
                )
        except Exception:
            LOGGER.exception(
                "Generation failed for chat_id=%s file=%s",
                message.chat.id,
                filename,
            )
            await status.edit_text(
                "Не удалось сгенерировать родословные. Подробности записаны "
                "в лог контейнера."
            )

    @router.message()
    async def fallback(message: Message) -> None:
        if await reject_if_forbidden(message):
            return
        await message.answer("Пришли Excel-файл .xlsx.")

    return router


async def run_bot() -> None:
    settings = load_telegram_bot_settings()
    prepare_bundled_graphviz()

    session = AiohttpSession(proxy=settings.proxy_url)
    bot = Bot(token=settings.token, session=session)
    dispatcher = Dispatcher()
    dispatcher.include_router(_router(settings, TelegramGenerationService()))

    proxy_mode = settings.proxy_url or "direct"
    LOGGER.info("Starting Telegram bot, network=%s", proxy_mode)
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
