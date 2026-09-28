import html
import logging
import os
import tempfile
import uuid

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from utils.zero import process_zero_transformation, _parse_coordinate_line

logger = logging.getLogger(__name__)
router = Router()

MAX_FILE_SIZE = 1 * 1024 * 1024  # 1 МБ
ITEMS_PER_PAGE = 10  # Точек на странице


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_zero")]
        ]
    )


def build_keyboard(points: list, page: int) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру с пагинацией."""
    total_pages = max(1, (len(points) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_points = points[start_idx:end_idx]

    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    # Кнопки с точками (по 2 в ряд)
    row = []
    for num, x, y in page_points:
        btn_text = f"№{num} ({x}, {y})"
        row.append(
            InlineKeyboardButton(
                text=btn_text, callback_data=f"zero_select_{num}"
            )
        )
        if len(row) == 2:
            keyboard.inline_keyboard.append(row)
            row = []
    if row:
        keyboard.inline_keyboard.append(row)

    # Навигация по страницам
    nav_row = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(
                text="⬅️ Назад", callback_data=f"zero_page_{page - 1}"
            )
        )

    nav_row.append(
        InlineKeyboardButton(
            text=f"📄 {page + 1}/{total_pages}", callback_data="zero_ignore"
        )
    )

    if page < total_pages - 1:
        nav_row.append(
            InlineKeyboardButton(
                text="Вперёд ➡️", callback_data=f"zero_page_{page + 1}"
            )
        )

    if nav_row:
        keyboard.inline_keyboard.append(nav_row)

    # Кнопка ручного ввода
    keyboard.inline_keyboard.append(
        [
            InlineKeyboardButton(
                text="✏️ Ввести номер вручную", callback_data="zero_manual"
            )
        ]
    )

    # Кнопка отмены
    keyboard.inline_keyboard.append(
        [
            InlineKeyboardButton(
                text="❌ Отмена", callback_data="cancel_zero"
            )
        ]
    )

    return keyboard


class ZeroStates(StatesGroup):
    waiting_file = State()
    waiting_point_selection = State()
    waiting_manual_input = State()


@router.message(Command("zero"))
async def cmd_zero(message: Message, state: FSMContext):
    await state.set_state(ZeroStates.waiting_file)
    await message.answer(
        "<b>🎯 Перевод в условную систему координат</b>\n\n"
        "Эта функция переводит координаты в условную систему, "
        "где выбранная вами точка станет (0, 0).\n\n"
        "<b>Формат .txt файла</b> (разделитель — только пробел или табуляция):\n"
        "<code>№  X  Y</code>\n\n"
        "• Бот покажет список всех точек\n"
        "• Вы выберете, какую точку сделать нулевой\n"
        "• Все остальные точки пересчитаются относительно неё\n\n"
        "<i>✨ Координаты автоматически округляются до 3 знаков.</i>\n"
        "<i>✨ Лишние строки игнорируются.</i>\n\n"
        "📎 Отправьте <b>.txt</b> файл для обработки.",
        reply_markup=cancel_keyboard(),
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    current = await state.get_state()
    if current is None:
        await message.answer("Нечего отменять.")
        return
    await state.clear()
    await message.answer("❌ Операция отменена.")


@router.callback_query(F.data == "cancel_zero")
async def cb_cancel_zero(callback: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    if current is None:
        await callback.answer("Нечего отменять.", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text("❌ Операция отменена.")
    await callback.answer()


@router.message(ZeroStates.waiting_file, F.document)
async def handle_zero_file(message: Message, state: FSMContext, bot: Bot):
    document = message.document
    file_name = document.file_name or ""

    if not file_name.lower().endswith(".txt"):
        await message.answer(
            "⚠️ Поддерживаются только файлы <b>.txt</b>.",
            reply_markup=cancel_keyboard(),
        )
        return

    if document.file_size and document.file_size > MAX_FILE_SIZE:
        await message.answer(
            f"⚠️ Файл слишком большой "
            f"({document.file_size // 1024} КБ). "
            f"Максимум {MAX_FILE_SIZE // 1024} КБ.",
            reply_markup=cancel_keyboard(),
        )
        return

    temp_input = None

    try:
        temp_input_fd, temp_input_path = tempfile.mkstemp(
            suffix=".txt", prefix="zero_in_"
        )
        os.close(temp_input_fd)
        temp_input = temp_input_path

        tg_file = await bot.get_file(document.file_id)
        await bot.download_file(tg_file.file_path, temp_input)

        with open(temp_input, "r", encoding="utf-8-sig") as f:
            content = f.read()

        raw_lines = content.strip().splitlines()
        lines = [ln for ln in raw_lines if ln.strip()]

        points = []
        for i, line in enumerate(lines, 1):
            try:
                num, x, y = _parse_coordinate_line(line, i)
                points.append((num, x, y))
            except ValueError:
                continue

        if not points:
            await message.answer(
                "⚠️ Не найдено ни одной корректной точки.",
                reply_markup=cancel_keyboard(),
            )
            return

        await state.update_data(
            file_content=content,
            points=points,
            temp_input=temp_input,
            current_page=0,
        )

        await state.set_state(ZeroStates.waiting_point_selection)
        keyboard = build_keyboard(points, page=0)

        await message.answer(
            f"📋 Найдено <b>{len(points)}</b> точек.\n\n"
            f"Выберите точку, которая станет (0, 0):\n"
            f"(листайте страницы или введите номер вручную)",
            reply_markup=keyboard,
        )

    except ValueError as e:
        await message.answer(
            f"⚠️ <b>Ошибка в файле:</b>\n\n{html.escape(str(e))}",
            reply_markup=cancel_keyboard(),
        )
    except UnicodeDecodeError:
        await message.answer(
            "⚠️ Не удалось прочитать файл.\n"
            "Убедитесь, что кодировка — <b>UTF-8</b> "
            "(не Windows-1251).",
            reply_markup=cancel_keyboard(),
        )
    except Exception:
        logger.exception("Непредвиденная ошибка в handle_zero_file")
        await message.answer(
            "❌ Внутренняя ошибка при обработке. "
            "Попробуйте другой файл или сообщите разработчику.",
            reply_markup=cancel_keyboard(),
        )
    finally:
        # Не удаляем temp_input — он понадобится после выбора точки
        pass


@router.message(ZeroStates.waiting_file, F.text)
async def wrong_input_in_zero(message: Message):
    await message.answer(
        "⚠️ Я жду <b>.txt файл</b> с координатами.\n"
        "Отправьте документ или нажмите кнопку отмены.",
        reply_markup=cancel_keyboard(),
    )


@router.callback_query(
    ZeroStates.waiting_point_selection, F.data.startswith("zero_select_")
)
async def handle_point_selection(callback: CallbackQuery, state: FSMContext):
    selected_num = callback.data.replace("zero_select_", "")
    await callback.answer()
    await process_and_send(callback.message, state, selected_num)


@router.callback_query(
    ZeroStates.waiting_point_selection, F.data.startswith("zero_page_")
)
async def handle_pagination(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.replace("zero_page_", ""))
    await callback.answer()

    data = await state.get_data()
    points = data.get("points", [])

    await state.update_data(current_page=page)
    keyboard = build_keyboard(points, page=page)

    await callback.message.edit_reply_markup(reply_markup=keyboard)


@router.callback_query(
    ZeroStates.waiting_point_selection, F.data == "zero_manual"
)
async def handle_manual_mode(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(ZeroStates.waiting_manual_input)
    await callback.message.edit_text(
        "✏️ Напишите <b>номер точки</b> текстом (например: 105).\n"
        "Для отмены — /cancel или кнопка ниже.",
        reply_markup=cancel_keyboard(),
    )


@router.message(ZeroStates.waiting_manual_input, F.text)
async def handle_manual_input(message: Message, state: FSMContext):
    selected_num = message.text.strip()
    await process_and_send(message, state, selected_num)


async def process_and_send(message: Message, state: FSMContext, selected_num: str):
    """Общая функция расчёта и отправки файла."""
    data = await state.get_data()
    file_content = data.get("file_content")
    temp_input = data.get("temp_input")

    if not file_content:
        await message.answer(
            "Данные не найдены. Начните заново: /zero",
            reply_markup=cancel_keyboard(),
        )
        await state.clear()
        return

    temp_output = None
    try:
        result = process_zero_transformation(file_content, selected_num)

        temp_output_fd, temp_output_path = tempfile.mkstemp(
            suffix=".txt", prefix="zero_out_"
        )
        os.close(temp_output_fd)
        temp_output = temp_output_path

        with open(temp_output, "w", encoding="utf-8") as f:
            f.write("\n".join(result.corrected_lines))

        summary = (
            f"✅ <b>Перевод в условную систему выполнен!</b>\n\n"
            f"📊 <b>Начало координат (0, 0):</b>\n"
            f"  Точка №<code>{result.selected_num}</code>\n"
            f"  X = <code>{result.selected_x:.3f}</code>\n"
            f"  Y = <code>{result.selected_y:.3f}</code>\n\n"
            f"📍 Обработано точек: <b>{result.total_points}</b>"
        )

        result_doc = FSInputFile(
            temp_output,
            filename=f"zero_{uuid.uuid4().hex[:6]}.txt",
        )
        await message.answer_document(document=result_doc, caption=summary)
        await state.clear()

    except ValueError as e:
        await message.answer(
            f"⚠️ <b>Ошибка:</b>\n\n{html.escape(str(e))}\n\n"
            f"Попробуйте выбрать другую точку или /cancel.",
            reply_markup=cancel_keyboard(),
        )
    except Exception:
        logger.exception("Непредвиденная ошибка в process_and_send")
        await message.answer(
            "❌ Внутренняя ошибка при обработке. "
            "Попробуйте другой файл или сообщите разработчику.",
            reply_markup=cancel_keyboard(),
        )
    finally:
        for path in (temp_input, temp_output):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass