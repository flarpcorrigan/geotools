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

from utils.corrections import process_corrections, _parse_coordinate_line

logger = logging.getLogger(__name__)
router = Router()

MAX_FILE_SIZE = 1 * 1024 * 1024  # 1 МБ
ITEMS_PER_PAGE = 10  # Строк на странице


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_cor")]
        ]
    )


def build_line_keyboard(
    lines: list,
    page: int,
    callback_prefix: str,
    exclude_indices: list[int] | None = None,
) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру со списком строк файла."""
    if exclude_indices is None:
        exclude_indices = []

    # Исключаем уже выбранные строки
    filtered_lines = [
        (idx, num, desc, x, y, h)
        for idx, num, desc, x, y, h in lines
        if idx not in exclude_indices
    ]

    total_pages = max(1, (len(filtered_lines) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_lines = filtered_lines[start_idx:end_idx]

    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    # Кнопки со строками (по 1 в ряд для читаемости)
    for idx, num, desc, x, y, h in page_lines:
        btn_text = f"№{num} {desc} ({x}, {y}, {h})"
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=btn_text,
                callback_data=f"{callback_prefix}{idx}"
            )
        ])

    # Навигация по страницам
    nav_row = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"{callback_prefix}page_{page - 1}"
            )
        )

    nav_row.append(
        InlineKeyboardButton(
            text=f"📄 {page + 1}/{total_pages}",
            callback_data="cor_ignore"
        )
    )

    if page < total_pages - 1:
        nav_row.append(
            InlineKeyboardButton(
                text="Вперёд ➡️",
                callback_data=f"{callback_prefix}page_{page + 1}"
            )
        )

    if nav_row:
        keyboard.inline_keyboard.append(nav_row)

    # Кнопка отмены
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_cor")
    ])

    return keyboard


class CorrectionStates(StatesGroup):
    waiting_file = State()
    waiting_fact_line = State()
    waiting_meas_line = State()


@router.message(Command("cor"))
async def cmd_cor(message: Message, state: FSMContext):
    await state.set_state(CorrectionStates.waiting_file)
    await message.answer(
        "<b> Ввод поправок в полевые измерения</b>\n\n"
        "Эта функция рассчитывает поправки по контрольной точке "
        "и автоматически применяет их ко всем остальным точкам.\n\n"
        "<b>Формат .txt файла</b> (разделитель — только пробел или табуляция):\n"
        "<code>№  Описание  X  Y  H</code>\n\n"
        "• Бот покажет все строки файла\n"
        "• Вы выберете строку с <b>фактическими</b> координатами контрольной точки\n"
        "• Затем выберете строку с <b>измеренными</b> координатами\n"
        "• Поправки применятся ко всем остальным точкам\n\n"
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


@router.callback_query(F.data == "cancel_cor")
async def cb_cancel_cor(callback: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    if current is None:
        await callback.answer("Нечего отменять.", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text("❌ Операция отменена.")
    await callback.answer()


@router.message(CorrectionStates.waiting_file, F.document)
async def handle_cor_file(message: Message, state: FSMContext, bot: Bot):
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
            suffix=".txt", prefix="cor_in_"
        )
        os.close(temp_input_fd)
        temp_input = temp_input_path

        tg_file = await bot.get_file(document.file_id)
        await bot.download_file(tg_file.file_path, temp_input)

        with open(temp_input, "r", encoding="utf-8-sig") as f:
            content = f.read()

        raw_lines = content.strip().splitlines()
        lines = [ln for ln in raw_lines if ln.strip()]

        # Парсим все строки
        parsed_lines = []
        for i, line in enumerate(lines):
            try:
                num, desc, x, y, h = _parse_coordinate_line(line, i + 1)
                parsed_lines.append((i, num, desc, x, y, h))
            except ValueError:
                continue

        if len(parsed_lines) < 3:
            await message.answer(
                "⚠️ Не найдено достаточно корректных строк (минимум 3).",
                reply_markup=cancel_keyboard(),
            )
            return

        await state.update_data(
            file_content=content,
            parsed_lines=parsed_lines,
            temp_input=temp_input,
            current_page=0,
        )

        await state.set_state(CorrectionStates.waiting_fact_line)
        keyboard = build_line_keyboard(parsed_lines, page=0, callback_prefix="cor_fact_")

        await message.answer(
            f"📋 Найдено <b>{len(parsed_lines)}</b> корректных строк.\n\n"
            f"<b>Шаг 1/3:</b> Выберите строку с <b>фактическими</b> координатами контрольной точки:",
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
        logger.exception("Непредвиденная ошибка в handle_cor_file")
        await message.answer(
            "❌ Внутренняя ошибка при обработке. "
            "Попробуйте другой файл или сообщите разработчику.",
            reply_markup=cancel_keyboard(),
        )
    finally:
        pass


@router.message(CorrectionStates.waiting_file, F.text)
async def wrong_input_in_cor(message: Message):
    await message.answer(
        "⚠️ Я жду <b>.txt файл</b> с координатами.\n"
        "Отправьте документ или нажмите кнопку отмены.",
        reply_markup=cancel_keyboard(),
    )


# ── Выбор строки с фактическими данными ──
@router.callback_query(
    CorrectionStates.waiting_fact_line, F.data.startswith("cor_fact_")
)
async def handle_fact_line(callback: CallbackQuery, state: FSMContext):
    data_part = callback.data.replace("cor_fact_", "")

    if data_part.startswith("page_"):
        page = int(data_part.replace("page_", ""))
        await callback.answer()

        data = await state.get_data()
        parsed_lines = data.get("parsed_lines", [])

        await state.update_data(current_page=page)
        keyboard = build_line_keyboard(parsed_lines, page=page, callback_prefix="cor_fact_")

        await callback.message.edit_reply_markup(reply_markup=keyboard)
        return

    # Выбор строки
    fact_line_index = int(data_part)
    await callback.answer()
    await state.update_data(fact_line_index=fact_line_index)
    await state.set_state(CorrectionStates.waiting_meas_line)

    data = await state.get_data()
    parsed_lines = data.get("parsed_lines", [])
    keyboard = build_line_keyboard(
        parsed_lines,
        page=0,
        callback_prefix="cor_meas_",
        exclude_indices=[fact_line_index],
    )

    # Получаем данные выбранной строки
    fact_data = next((p for p in parsed_lines if p[0] == fact_line_index), None)
    fact_num = fact_data[1] if fact_data else "?"

    await callback.message.edit_text(
        f"✅ Выбрана строка <b>№{fact_num}</b> с фактическими данными.\n\n"
        f"<b>Шаг 2/3:</b> Теперь выберите строку с <b>измеренными</b> координатами контрольной точки:",
        reply_markup=keyboard,
    )


# ── Выбор строки с измеренными данными ──
@router.callback_query(
    CorrectionStates.waiting_meas_line, F.data.startswith("cor_meas_")
)
async def handle_meas_line(callback: CallbackQuery, state: FSMContext):
    data_part = callback.data.replace("cor_meas_", "")

    if data_part.startswith("page_"):
        page = int(data_part.replace("page_", ""))
        await callback.answer()

        data = await state.get_data()
        parsed_lines = data.get("parsed_lines", [])
        fact_line_index = data.get("fact_line_index")

        await state.update_data(current_page=page)
        keyboard = build_line_keyboard(
            parsed_lines,
            page=page,
            callback_prefix="cor_meas_",
            exclude_indices=[fact_line_index],
        )

        await callback.message.edit_reply_markup(reply_markup=keyboard)
        return

    # Выбор строки
    meas_line_index = int(data_part)
    await callback.answer()

    # Запускаем обработку
    await process_and_send(callback.message, state, meas_line_index)


# ── Общая функция расчёта и отправки ──
async def process_and_send(message: Message, state: FSMContext, meas_line_index: int):
    """Общая функция расчёта и отправки файла."""
    data = await state.get_data()
    file_content = data.get("file_content")
    temp_input = data.get("temp_input")
    fact_line_index = data.get("fact_line_index")

    if not file_content or fact_line_index is None:
        await message.answer(
            "Данные не найдены. Начните заново: /cor",
            reply_markup=cancel_keyboard(),
        )
        await state.clear()
        return

    temp_output = None
    try:
        result = process_corrections(file_content, fact_line_index, meas_line_index)

        temp_output_fd, temp_output_path = tempfile.mkstemp(
            suffix=".txt", prefix="cor_out_"
        )
        os.close(temp_output_fd)
        temp_output = temp_output_path

        with open(temp_output, "w", encoding="utf-8") as f:
            f.write("\n".join(result.corrected_lines))

        summary = (
            f"✅ <b>Поправки рассчитаны и применены!</b>\n\n"
            f"📊 <b>Фактические данные:</b>\n"
            f"  Точка №<code>{result.fact_num}</code> ({result.fact_desc})\n"
            f"  X = <code>{result.fact_x:.3f}</code>, "
            f"Y = <code>{result.fact_y:.3f}</code>, "
            f"H = <code>{result.fact_h:.3f}</code>\n\n"
            f"📏 <b>Измеренные данные:</b>\n"
            f"  Точка №<code>{result.meas_num}</code> ({result.meas_desc})\n"
            f"  X = <code>{result.meas_x:.3f}</code>, "
            f"Y = <code>{result.meas_y:.3f}</code>, "
            f"H = <code>{result.meas_h:.3f}</code>\n\n"
            f"🔧 <b>Поправки (Факт − Измер):</b>\n"
            f"  ΔX = <code>{result.dx:+.3f}</code>\n"
            f"  ΔY = <code>{result.dy:+.3f}</code>\n"
            f"  ΔH = <code>{result.dh:+.3f}</code>\n\n"
            f"📍 Скорректировано точек: <b>{result.total_points}</b>"
        )

        result_doc = FSInputFile(
            temp_output,
            filename=f"corrected_{uuid.uuid4().hex[:6]}.txt",
        )
        await message.answer_document(document=result_doc, caption=summary)
        await state.clear()

    except ValueError as e:
        await message.answer(
            f"⚠️ <b>Ошибка:</b>\n\n{html.escape(str(e))}\n\n"
            f"Попробуйте выбрать другие строки или /cancel.",
            reply_markup=cancel_keyboard(),
        )
    except Exception:
        logger.exception("Непредвиденная ошибка в process_and_send")
        await message.answer(
            " Внутренняя ошибка при обработке. "
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