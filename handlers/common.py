from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from handlers.corrections import cmd_cor as corrections_cmd_cor
from handlers.zero import cmd_zero as zero_cmd_zero

router = Router()


def main_keyboard() -> InlineKeyboardMarkup:
    """Главная клавиатура с кнопками команд."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📐 Поправки", callback_data="cmd_cor"),
                InlineKeyboardButton(text="🎯 Условная СК", callback_data="cmd_zero"),
            ],
            [
                InlineKeyboardButton(text="📂 Конвертер (скоро)", callback_data="soon"),
                InlineKeyboardButton(text="☀️ Солнце (скоро)", callback_data="soon"),
            ],
        ]
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Приветствую, коллега! 👷♂️\n\n"
        "Я — <b>geoTOOLS</b>, твой цифровой помощник "
        "для полевых и камеральных работ.\n\n"
        "Выбери нужную функцию:",
        reply_markup=main_keyboard(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    help_text = (
        "<b>📋 Команды geoTOOLS:</b>\n\n"
        "/start — главное меню\n"
        "/cor — ввод поправок в измерения\n"
        "/zero — перевод в условную систему координат\n"
        "/cancel — отмена текущей операции\n"
        "/help — это сообщение\n\n"
        "<i>Новые функции добавляются регулярно.</i>"
    )
    await message.answer(help_text, reply_markup=main_keyboard())


@router.callback_query(F.data == "cmd_cor")
async def cb_cor(callback: CallbackQuery, state: FSMContext):
    """Вызывает хендлер команды /cor напрямую."""
    await callback.answer()
    await corrections_cmd_cor(callback.message, state)


@router.callback_query(F.data == "cmd_zero")
async def cb_zero(callback: CallbackQuery, state: FSMContext):
    """Вызывает хендлер команды /zero напрямую."""
    await callback.answer()
    await zero_cmd_zero(callback.message, state)


@router.callback_query(F.data == "soon")
async def cb_soon(callback: CallbackQuery):
    await callback.answer("Функция в разработке ", show_alert=True)


@router.message(F.text & ~F.text.startswith("/"))
async def echo_message(message: Message, state: FSMContext):
    # Если пользователь в FSM — не перехватываем
    current_state = await state.get_state()
    if current_state is not None:
        return

    await message.answer(
        "Я пока не понимаю текстовые сообщения. "
        "Используй команды из меню или нажми /help.",
        reply_markup=main_keyboard(),
    )