import os
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, FSInputFile
from aiogram.filters import Command
from aiogram.utils.markdown import hpre
from config import settings
from utils.database import (
    add_user, remove_user, get_all_users, 
    get_user_by_username, get_user_by_id
)

logger = logging.getLogger(__name__)
router = Router()

# Глобальная защита: роутер реагирует только на сообщения от главного админа
router.message.filter(F.from_user.id == settings.ADMIN_ID)

# Кэш для хранения ID последних сообщений бота (чтобы удалять старые и не спамить)
bot_messages_cache: dict[int, int] = {}

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

async def cleanup_previous_message(chat_id: int, bot: Bot):
    message_id = bot_messages_cache.get(chat_id)
    if message_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass
        finally:
            if chat_id in bot_messages_cache:
                del bot_messages_cache[chat_id]

async def send_and_track(message: Message, text: str, bot: Bot):
    await cleanup_previous_message(message.chat.id, bot)
    response = await message.answer(text)
    bot_messages_cache[message.chat.id] = response.message_id
    try:
        await message.delete()
    except Exception:
        pass

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
    
    if target_type == 'id' and target_value == bot_user.id:
        await send_and_track(message, "⚠️ Нельзя выдать доступ самому боту.", bot)
        return
    
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
    else:
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
    else:
        user_id = target_value
    
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
        if u_date:
            try:
                date_parts = u_date.split(' ')[0]
                formatted_date = f"📅 {date_parts}"
            except Exception:
                formatted_date = "📅 дата неизвестна"
        else:
            formatted_date = "📅 дата неизвестна"
        
        text += f"👤 <code>{u_id}</code> — @{u_name or 'Без username'}\n   {formatted_date}\n"
    
    await send_and_track(message, text, bot)


@router.message(Command("log"))
async def handle_log_command(message: Message, bot: Bot):
    """
    Отправляет логи администратору.
    Использование:
    /log - отправляет файл лога целиком (до 5 МБ)
    /log <N> - отправляет последние N строк лога текстом (макс. 2000)
    """
    log_file_path = "logs/bot.log"
    
    # Проверяем существование файла (здесь используется os, который импортирован в начале)
    if not os.path.exists(log_file_path):
        await message.answer("⚠️ Файл логов не найден. Возможно, бот только что запущен или папка logs не создана.")
        return

    parts = message.text.split()
    
    # Если указан аргумент (количество строк)
    if len(parts) > 1:
        try:
            n_lines = int(parts[1])
            if n_lines <= 0 or n_lines > 2000:
                await message.answer(
                    "⚠️ Укажите число строк от 1 до 2000.\nПример: <code>/log 50</code>",
                    parse_mode="HTML"
                )
                return
            
            with open(log_file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            last_lines = lines[-n_lines:]
            text = "".join(last_lines)
            
            await message.answer(
                f"📋 <b>Последние {len(last_lines)} строк лога:</b>\n\n{hpre(text)}",
                parse_mode="HTML"
            )
            try:
                await message.delete()
            except Exception:
                pass
            return
        except ValueError:
            await message.answer(
                "⚠️ Неверный формат. Используйте <code>/log</code> или <code>/log &lt;число&gt;</code>",
                parse_mode="HTML"
            )
            return

    # Отправка файла целиком
    try:
        log_file = FSInputFile(log_file_path)
        await bot.send_document(
            chat_id=message.chat.id,
            document=log_file,
            caption="📄 <b>Файл логов бота</b>\n\n<i>Последние события находятся в конце файла.</i>",
            parse_mode="HTML"
        )
        try:
            await message.delete()
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Ошибка при отправке лога: {e}")
        await message.answer(f"❌ Ошибка при отправке файла лога: {e}")