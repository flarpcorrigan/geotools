import logging
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import Update, Message
from config import settings
from utils.database import is_allowed, log_unauthorized_access

logger = logging.getLogger(__name__)

class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        # Извлекаем пользователя из любого типа события
        user = None
        if event.message:
            user = event.message.from_user
        elif event.callback_query:
            user = event.callback_query.from_user
        elif event.inline_query:
            user = event.inline_query.from_user
        elif event.chat_member:
            user = event.chat_member.from_user

        # Если пользователя нет в событии (например, системное обновление), пропускаем
        if not user:
            return await handler(event, data)

        # Проверка прав
        if not await is_allowed(user.id, settings.ADMIN_ID):
            # Логируем попытку взлома/несанкционированного доступа
            await log_unauthorized_access(user.id, user.username)
            
            # Отвечаем ТОЛЬКО на обычные сообщения. 
            # На колбэки и инлайн не отвечаем, чтобы не "светить" активностью бота злоумышленнику.
            if event.message:
                await event.message.answer(
                    "🚫 <b>Доступ запрещен.</b>\n"
                    "Ваша попытка использования бота geoTOOLS была залогирована.\n"
                    "Для получения доступа обратитесь к администратору."
                )
            
            # Прерываем цепочку выполнения. Хендлер НЕ будет вызван.
            return
        
        # Если доступ разрешен, передаем управление дальше
        return await handler(event, data)