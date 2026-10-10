from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.filters import Command
from config import settings
from utils.database import add_user, remove_user, get_all_users

admin_routerrouter = Router()

# ЖЕСТКИЙ ФИЛЬТР: Хендлеры сработают ТОЛЬКО если ID отправителя совпадает с ADMIN_ID
admin_router.message.filter(F.from_user.id == settings.ADMIN_ID)

@admin_router.message(Command("grant", "allow"))
async def grant_access(message: Message, bot: Bot):
    """Выдать доступ. Использование: ответ на сообщение пользователя или /grant <user_id>"""
    bot_user = await bot.get_me()
    
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        if not target_user:
            await message.answer("⚠️ Не удалось определить пользователя в ответном сообщении.")
            return
        if target_user.id == bot_user.id:
            await message.answer("⚠️ Нельзя выдать доступ самому боту.")
            return
            
        user_id = target_user.id
        username = target_user.username or "Без_username"
    else:
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer(
                "⚠️ <b>Неверный формат.</b>\n"
                "Используйте:\n"
                "1. Ответьте на сообщение пользователя командой /grant\n"
                "2. Или введите: /grant <числовой_user_id>"
            )
            return
        
        try:
            user_id = int(parts[1])
        except ValueError:
            await message.answer("⚠️ ID пользователя должен быть числом.")
            return
            
        if user_id == bot_user.id:
            await message.answer("⚠️ Нельзя выдать доступ самому боту.")
            return
            
        username = "Неизвестно (добавлен по ID)"

    await add_user(user_id, username, settings.ADMIN_ID)
    await message.answer(f"✅ <b>Доступ разрешен:</b>\nID: <code>{user_id}</code>\nUsername: @{username}")

@admin_router.message(Command("revoke", "deny"))
async def revoke_access(message: Message, bot: Bot):
    """Отозвать доступ. Использование: ответ на сообщение или /revoke <user_id>"""
    bot_user = await bot.get_me()
    
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
    else:
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer("⚠️ Используйте: /revoke <user_id> или ответьте на сообщение.")
            return
        try:
            user_id = int(parts[1])
        except ValueError:
            await message.answer("⚠️ ID пользователя должен быть числом.")
            return

    if user_id == bot_user.id:
        await message.answer("⚠️ Невозможно отозвать доступ у бота.")
        return
    if user_id == settings.ADMIN_ID:
        await message.answer("⚠️ Невозможно отозвать доступ у главного администратора.")
        return

    await remove_user(user_id, settings.ADMIN_ID)
    await message.answer(f"❌ <b>Доступ отозван:</b>\nID: <code>{user_id}</code>")

@admin_router.message(Command("users", "list"))
async def list_users(message: Message):
    """Показать всех пользователей с доступом"""
    users = await get_all_users()
    # Фильтруем админа из списка для чистоты вывода
    filtered_users = [(u_id, u_name) for u_id, u_name in users if u_id != settings.ADMIN_ID]
    
    if not filtered_users:
        await message.answer("📋 Список доступа пуст (кроме главного администратора).")
        return
    
    text = "📋 <b>Авторизованные пользователи:</b>\n\n"
    for u_id, u_name in filtered_users:
        text += f"👤 <code>{u_id}</code> — @{u_name or 'Без username'}\n"
    
    # Если список очень длинный, можно разбить на сообщения, но для геодезистов обычно это < 50 человек
    await message.answer(text)