from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from handlers.corrections import cmd_cor as corrections_cmd_cor
from handlers.zero import cmd_zero as zero_cmd_zero

router = Router()

MENU_BUTTON_TEXT = "📋 Меню"


def menu_reply_keyboard() -> ReplyKeyboardMarkup:
    """Reply-клавиатура с кнопкой Меню (всегда под полем ввода)."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=MENU_BUTTON_TEXT)]
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Нажмите 'Меню' для выбора функции",
    )


def main_inline_keyboard() -> InlineKeyboardMarkup:
    """Inline-клавиатура со списком функций."""
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
        "Приветствую, коллега! 👷‍♂️\n\n"
        "Я — <b>geoTOOLS</b>, твой цифровой помощник "
        "для полевых и камеральных работ.\n\n"
        "Нажми кнопку <b>📋 Меню</b> под полем ввода, чтобы выбрать функцию.",
        reply_markup=menu_reply_keyboard(),
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
    await message.answer(help_text, reply_markup=menu_reply_keyboard())


@router.message(F.text == MENU_BUTTON_TEXT)
async def handle_menu_button(message: Message, state: FSMContext):
    """Обработчик нажатия кнопки 'Меню'."""
    await state.clear()
    
    menu_text = (
        "<b>️ Доступные функции geoTOOLS:</b>\n\n"
        
        "<b> Поправки</b>\n"
        "Рассчитывает поправки по контрольной точке и применяет их ко всем остальным точкам.\n"
        "Формат: № Описание X Y H\n\n"
        
        "<b>🎯 Условная СК</b>\n"
        "Переводит координаты в условную систему. Первая точка становится (0, 0), "
        "вторая задаёт направление на север.\n"
        "Формат: № X Y\n\n"
        
        "<b> Конвертер</b> <i>(в разработке)</i>\n"
        "Конвертация между форматами CSV, KML, DXF.\n\n"
        
        "<b>☀️ Солнце</b> <i>(в разработке)</i>\n"
        "Расчёт положения солнца и теней для полевых работ.\n\n"
        
        "Выбери нужную функцию:"
    )
    
    await message.answer(
        menu_text,
        reply_markup=main_inline_keyboard(),
    )


@router.callback_query(F.data == "cmd_cor")
async def cb_cor(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await corrections_cmd_cor(callback.message, state)


@router.callback_query(F.data == "cmd_zero")
async def cb_zero(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await zero_cmd_zero(callback.message, state)


@router.callback_query(F.data == "soon")
async def cb_soon(callback: CallbackQuery):
    await callback.answer("Функция в разработке 🚧", show_alert=True)


@router.message(F.text & ~F.text.startswith("/") & (F.text != MENU_BUTTON_TEXT))
async def echo_message(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        return

    await message.answer(
        "Я пока не понимаю текстовые сообщения. "
        "Нажми кнопку <b>📋 Меню</b> для выбора функции.",
        reply_markup=menu_reply_keyboard(),
    )