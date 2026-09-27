from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Приветствую, коллега! 👷‍♂️\n\n"
        "Я — <b>geoTOOLS</b>, твой цифровой помощник "
        "для полевых и камеральных работ.\n\n"
        "Что я умею:\n"
        "📐 <b>/cor</b> — ввод поправок в полевые измерения\n"
        "📂 Конвертер файлов (скоро)\n"
        "☀️ Расчёт солнца и теней (скоро)\n\n"
        "Используй /help для полного списка команд."
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    help_text = (
        "<b>📋 Команды geoTOOLS:</b>\n\n"
        "/start — перезапуск бота\n"
        "/cor — ввод поправок в измерения\n"
        "/cancel — отмена текущей операции\n"
        "/help — это сообщение\n\n"
        "<i>Новые функции добавляются регулярно.</i>"
    )
    await message.answer(help_text)


@router.message(F.text & ~F.text.startswith("/"))  # <-- ИЗМЕНЕНО ЗДЕСЬ
async def echo_message(message: Message):
    await message.answer(
        "Я пока не понимаю текстовые сообщения. "
        "Используй команды из меню или нажми /help."
    )