import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.filters import Command
from config import settings
from utils.database import (
    add_user, remove_user, get_all_users, 
    get_user_by_username, get_user_by_id
)

router = Router()
router.message.filter(F.from_user.id == settings.ADMIN_ID)

# Кэш с ограничением размера и временем жизни
MAX_CACHE_SIZE = 100
CACHE_TTL = 3600

class MessageCache:
    """Простой кэш с TTL и ограничением размера"""
    def __init__(self, max_size: int, ttl: int):
        self._cache = {}
        self._max_size = max_size
        self._ttl = ttl
    
    def get(self, chat_id: int) -> int | None:
        if chat_id not in self._cache:
            return None
        message_id, timestamp = self._cache[chat_id]
        if asyncio.get_event_loop().time() - timestamp > self._ttl:
            del self._cache[chat_id]
            return None
        return message_id
    
    def set(self, chat_id: int, message_id: int):
        if len(self._cache) >= self._max_size:
            oldest_key = min(self._cache, key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]
        self._cache[chat_id] = (message_id, asyncio.get_event_loop().time())
    
    def delete(self, chat_id: int):
        self._cache.pop(chat_id, None)

bot_messages_cache = MessageCache(MAX_CACHE_SIZE, CACHE_TTL)

async def cleanup_previous_message(chat_id: int, bot: Bot):
    message_id = bot_messages_cache.get(chat_id)
    if message_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass
        finally:
            bot_messages_cache.delete(chat_id)

async def send_and_track(message: Message, text: str, bot: Bot):
    await cleanup_previous_message(message.chat.id, bot)
    response = await message.answer(text)
    bot_messages_cache.set(message.chat.id, response.message_id)
    try:
        await message.delete()
    except Exception:
        pass

def parse_target_argument(arg: str) -> tuple[str, str | int]:
    """
    Парсит аргумент команды.
    Возвращает (тип, значение):
    - ('username', 'username_without_@') если начинается с @
    - ('id', числовой_id) если число
    """
    if arg.startswith('@'):
        return ('username', arg[1:])  # Убираем символ @
    else:
        try:
            return ('id', int(arg))
        except ValueError:
            return ('invalid', arg)

@router.message(Command("grant", "allow"))
async def grant_access(message: Message, bot: Bot):
    """Выдать доступ. Использование: /grant <user_id> или /grant @username"""
    bot_user = await bot.get_me()
    parts = message.text.split()
    
    if len(parts) < 2:
        await send_and_track(
            message,
            "⚠️ <b>Неверный формат.</b>\n"
            "Используйте:\n"
            "• /grant &lt;числовой_user_id&gt;\n"
            "• /grant @username",
            bot
        )
        return
    
    target_type, target_value = parse_target_argument(parts[1])
    
    if target_type == 'invalid':
        await send_and_track(
            message,
            "⚠️ Неверный формат аргумента.\n"
            "Используйте числовой ID или @username",
            bot
        )
        return
    
    # Проверяем, не пытается ли админ выдать доступ боту
    if target_type == 'id' and target_value == bot_user.id:
        await send_and_track(message, "⚠️ Нельзя выдать доступ самому боту.", bot)
        return
    
    # Получаем информацию о пользователе
    if target_type == 'username':
        user_info = await get_user_by_username(target_value)
        if not user_info:
            await send_and_track(
                message,
                f"⚠️ Пользователь @{target_value} не найден в базе данных.\n"
                "Попросите пользователя написать боту, чтобы он появился в системе.",
                bot
            )
            return
        user_id, username = user_info
    else:  # target_type == 'id'
        user_info = await get_user_by_id(target_value)
        if user_info:
            user_id, username = user_info
        else:
            user_id = target_value
            username = "Неизвестно (добавлен по ID)"
    
    await add_user(user_id, username, settings.ADMIN_ID)
    await send_and_track(
        message,
        f"✅ <b>Доступ разрешен:</b>\nID: <code>{user_id}</code>\nUsername: @{username}",
        bot
    )

@router.message(Command("revoke", "deny"))
async def revoke_access(message: Message, bot: Bot):
    """Отозвать доступ. Использование: /revoke <user_id> или /revoke @username"""
    bot_user = await bot.get_me()
    parts = message.text.split()
    
    if len(parts) < 2:
        await send_and_track(
            message,
            "⚠️ <b>Неверный формат.</b>\n"
            "Используйте:\n"
            "• /revoke &lt;числовой_user_id&gt;\n"
            "• /revoke @username",
            bot
        )
        return
    
    target_type, target_value = parse_target_argument(parts[1])
    
    if target_type == 'invalid':
        await send_and_track(
            message,
            "⚠️ Неверный формат аргумента.\n"
            "Используйте числовой ID или @username",
            bot
        )
        return
    
    # Получаем ID пользователя
    if target_type == 'username':
        user_info = await get_user_by_username(target_value)
        if not user_info:
            await send_and_track(
                message,
                f"⚠️ Пользователь @{target_value} не найден в списке доступа.",
                bot
            )
            return
        user_id, _ = user_info
    else:  # target_type == 'id'
        user_id = target_value
    
    # Проверки безопасности
    if user_id == bot_user.id:
        await send_and_track(message, "⚠️ Невозможно отозвать доступ у бота.", bot)
        return
    if user_id == settings.ADMIN_ID:
        await send_and_track(message, "⚠️ Невозможно отозвать доступ у главного администратора.", bot)
        return
    
    await remove_user(user_id, settings.ADMIN_ID)
    await send_and_track(
        message,
        f"❌ <b>Доступ отозван:</b>\nID: <code>{user_id}</code>",
        bot
    )

@router.message(Command("users", "list"))
async def list_users(message: Message, bot: Bot):
    """Показать всех пользователей с доступом и датой добавления"""
    users = await get_all_users()
    filtered_users = [(u_id, u_name, u_date) for u_id, u_name, u_date in users if u_id != settings.ADMIN_ID]
    
    if not filtered_users:
        await send_and_track(
            message,
            "📋 Список доступа пуст (кроме главного администратора).",
            bot
        )
        return
    
    text = "📋 <b>Авторизованные пользователи:</b>\n\n"
    for u_id, u_name, u_date in filtered_users:
        # Форматируем дату
        if u_date:
            try:
                # Парсим дату из БД (формат: YYYY-MM-DD HH:MM:SS)
                date_parts = u_date.split(' ')[0]  # Берём только дату без времени
                formatted_date = f"📅 {date_parts}"
            except:
                formatted_date = "📅 дата неизвестна"
        else:
            formatted_date = "📅 дата неизвестна"
        
        text += f"👤 <code>{u_id}</code> — @{u_name or 'Без username'}\n   {formatted_date}\n"
    
    await send_and_track(message, text, bot)