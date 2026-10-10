import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from config import settings

# Импорты
from utils.database import init_db
from middlewares.access import AccessMiddleware
from handlers import (
    common_router, corrections_router, zero_router, 
    calib_router, per_router, admin_router
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Запуск бота geoTOOLS (Secure Mode)...")
    
    # 1. Инициализация защищенной БД
    await init_db()

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # 2. ГЛОБАЛЬНАЯ ЗАЩИТА: Middleware на все типы обновлений (Update)
    dp.update.middleware(AccessMiddleware())

    # 3. Регистрация роутеров
    dp.include_router(admin_router)
    dp.include_router(corrections_router)
    dp.include_router(zero_router)
    dp.include_router(calib_router)
    dp.include_router(per_router)
    dp.include_router(common_router)

    # Очистка вебхука перед polling (безопасный старт)
    await bot.delete_webhook(drop_pending_updates=True)
    
    try:
        logger.info("Бот успешно запущен и ожидает обновления.")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        logger.info("Сессия бота закрыта.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот geoTOOLS остановлен администратором.")