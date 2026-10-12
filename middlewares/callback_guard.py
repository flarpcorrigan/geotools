import logging
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Update

logger = logging.getLogger(__name__)

class CallbackGuardMiddleware(BaseMiddleware):
    """Защищает от нажатия на устаревшие инлайн-кнопки"""
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        if isinstance(event, CallbackQuery):
            state = data.get("state")
            if state:
                current_state = await state.get_state()
                if current_state:
                    state_data = await state.get_data()
                    active_msg_id = state_data.get("active_message_id")
                    
                    if active_msg_id is not None and event.message.message_id != active_msg_id:
                        logger.warning(
                            f"Blocked outdated callback: user={event.from_user.id}, "
                            f"clicked_msg_id={event.message.message_id}, expected={active_msg_id}"
                        )
                        await event.answer(
                            "⚠️ Это сообщение устарело. Используйте актуальное меню или нажмите /cancel.",
                            show_alert=True
                        )
                        return
            
        return await handler(event, data)