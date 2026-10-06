import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import settings
from handlers import common_router, corrections_router, zero_router, calib_router, per_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Запуск бота geoTOOLS...")

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Функциональные роутеры — первыми
    dp.include_router(corrections_router)
    dp.include_router(zero_router)
    dp.include_router(calib_router)
    dp.include_router(per_router)
    # common_router — последним (содержит echo-обработчик)
    dp.include_router(common_router)

    await bot.delete_webhook(drop_pending_updates=True)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот geoTOOLS остановлен.")