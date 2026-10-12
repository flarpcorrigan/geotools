import logging
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

logger = logging.getLogger(__name__)
router = Router()

MENU_BUTTON_TEXT = "📋 Меню"

def menu_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=MENU_BUTTON_TEXT)]],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Нажмите 'Меню' для выбора функции",
    )

def main_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📐 Поправки", callback_data="cmd_cor"),
                InlineKeyboardButton(text="🎯 Условная СК", callback_data="cmd_zero"),
            ],
            [
                InlineKeyboardButton(text="🔧 Калибровка", callback_data="cmd_calib"),
                InlineKeyboardButton(text="🔄 Пересчет", callback_data="cmd_per"),
            ],
            [
                InlineKeyboardButton(text="☀️ Солнце (скоро)", callback_data="soon"),
                InlineKeyboardButton(text="📂 Конвертер (скоро)", callback_data="soon"),
            ],
        ]
    )

async def check_active_process(callback: CallbackQuery, state: FSMContext) -> bool:
    """Проверяет, не запущен ли уже другой процесс"""
    current_state = await state.get_state()
    if current_state is not None:
        await callback.answer(
            "⚠️ Сначала завершите текущую операцию (нажмите /cancel) или дождитесь её окончания.",
            show_alert=True
        )
        return False
    return True

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    msg = await message.answer(
        "Приветствую, коллега! 👷‍♂️\n\n"
        "Я — <b>geoTOOLS</b>, твой цифровой помощник "
        "для полевых и камеральных работ.\n\n"
        "Нажми кнопку <b>📋 Меню</b> под полем ввода, чтобы выбрать функцию.",
        reply_markup=menu_reply_keyboard(),
    )
    await state.update_data(active_message_id=msg.message_id)

@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext):
    help_text = (
        "<b>🛠️ Команды geoTOOLS:</b>\n\n"
        "/start — главное меню\n"
        "/cor — ввод поправок в измерения\n"
        "/zero — перевод в условную систему координат\n"
        "/calib — калибровка (7 параметров Гельмерта)\n"
        "/per — пересчёт координат между СК\n"
        "/cancel — отмена текущей операции\n"
        "/help — это сообщение\n\n"
        "<i>Новые функции добавляются регулярно.</i>"
    )
    msg = await message.answer(help_text, reply_markup=menu_reply_keyboard())
    await state.update_data(active_message_id=msg.message_id)

@router.message(F.text)
async def handle_menu_button(message: Message, state: FSMContext):
    if message.text == MENU_BUTTON_TEXT:
        await state.clear()
        menu_text = (
            "<b>🛠️ Доступные функции geoTOOLS:</b>\n\n"
            "<b>📐 Поправки</b>\nРассчитывает поправки по контрольной точке.\n\n"
            "<b>🎯 Условная СК</b>\nПереводит координаты в условную систему.\n\n"
            "<b>🔧 Калибровка</b>\nРасчет 7 параметров Гельмерта по точкам.\n\n"
            "<b>🔄 Пересчёт СК</b>\nПересчитывает координаты с применением калибровки.\n\n"
            "Выбери нужную функцию:"
        )
        msg = await message.answer(menu_text, reply_markup=main_inline_keyboard())
        await state.update_data(active_message_id=msg.message_id)
        return

    current_state = await state.get_state()
    if current_state is not None:
        return

    msg = await message.answer(
        "Я пока не понимаю текстовые сообщения. "
        "Нажми кнопку <b>📋 Меню</b> для выбора функции.",
        reply_markup=menu_reply_keyboard(),
    )
    await state.update_data(active_message_id=msg.message_id)

@router.callback_query(F.data == "cmd_cor")
async def cb_cor(callback: CallbackQuery, state: FSMContext):
    if not await check_active_process(callback, state):
        return
    await callback.answer()
    await state.clear()
    from handlers.corrections import cmd_cor as corrections_cmd_cor
    await corrections_cmd_cor(callback.message, state)

@router.callback_query(F.data == "cmd_zero")
async def cb_zero(callback: CallbackQuery, state: FSMContext):
    if not await check_active_process(callback, state):
        return
    await callback.answer()
    await state.clear()
    from handlers.zero import cmd_zero as zero_cmd_zero
    await zero_cmd_zero(callback.message, state)

@router.callback_query(F.data == "cmd_calib")
async def cb_calib(callback: CallbackQuery, state: FSMContext):
    if not await check_active_process(callback, state):
        return
    await callback.answer()
    await state.clear()
    from handlers.calib import cmd_calib as calib_cmd
    await calib_cmd(callback.message, state)

@router.callback_query(F.data == "cmd_per")
async def cb_per(callback: CallbackQuery, state: FSMContext):
    if not await check_active_process(callback, state):
        return
    await callback.answer()
    await state.clear()
    from handlers.per import cmd_per as per_cmd
    await per_cmd(callback.message, state)

@router.callback_query(F.data == "soon")
async def cb_soon(callback: CallbackQuery):
    await callback.answer("Функция в разработке 🚧", show_alert=True)