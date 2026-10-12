import time
import logging
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import Update

logger = logging.getLogger(__name__)

class ThrottlingMiddleware(BaseMiddleware):
    """Middleware для защиты от флуда"""
    
    def __init__(self, rate_limit: float = 1.0):
        self._rate_limit = rate_limit
        self._last_request: Dict[int, float] = {}
    
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        user = None
        if event.message:
            user = event.message.from_user
        elif event.callback_query:
            user = event.callback_query.from_user
        
        if not user:
            return await handler(event, data)
        
        user_id = user.id
        current_time = time.time()
        last_time = self._last_request.get(user_id, 0.0)
        
        if current_time - last_time < self._rate_limit:
            logger.debug(f"Throttled user {user_id}")
            return
        
        self._last_request[user_id] = current_time
        return await handler(event, data)