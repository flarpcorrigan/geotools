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

from utils.coor import process_coordinate_transformation, SUPPORTED_CRS

logger = logging.getLogger(__name__)
router = Router()

MAX_FILE_SIZE = 1 * 1024 * 1024  # 1 МБ


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_coor")]
        ]
    )


def crs_selection_keyboard(prefix: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора системы координат."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    row = []
    for key, info in SUPPORTED_CRS.items():
        btn_text = f"{info['name']}"
        row.append(
            InlineKeyboardButton(
                text=btn_text,
                callback_data=f"{prefix}{key}"
            )
        )
        if len(row) == 2:
            keyboard.inline_keyboard.append(row)
            row = []
    if row:
        keyboard.inline_keyboard.append(row)

    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_coor")
    ])
    return keyboard


class CoorStates(StatesGroup):
    waiting_source_crs = State()
    waiting_target_crs = State()
    waiting_file = State()


@router.message(Command("coor"))
async def cmd_coor(message: Message, state: FSMContext):
    await state.set_state(CoorStates.waiting_source_crs)

    crs_list = "\n".join(
        f"• <b>{info['name']}</b> — {info['description']}"
        for info in SUPPORTED_CRS.values()
    )

    await message.answer(
        "<b>🌐 Пересчёт координат между СК</b>\n\n"
        "Эта функция пересчитывает координаты из одной системы в другую "
        "с автоматической оценкой точности.\n\n"
        "<b>Поддерживаемые СК:</b>\n"
        f"{crs_list}\n\n"
        "<b>Формат .txt файла</b> (разделитель — только пробел или табуляция):\n"
        "<code>№  Описание  X  Y  H</code>\n\n"
        "<i>️ Для WGS84: X = долгота, Y = широта (в градусах).</i>\n"
        "<i>ℹ️ Для проекционных СК: X = восток, Y = север (в метрах).</i>\n"
        "<i>️ Высота H передаётся без изменений.</i>\n\n"
        "<b>Шаг 1/3:</b> Выберите <b>исходную</b> систему координат:",
        reply_markup=crs_selection_keyboard("coor_source_"),
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    current = await state.get_state()
    if current is None:
        await message.answer("Нечего отменять.")
        return
    await state.clear()
    await message.answer("❌ Операция отменена.")


@router.callback_query(F.data == "cancel_coor")
async def cb_cancel_coor(callback: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    if current is None:
        await callback.answer("Нечего отменять.", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text(" Операция отменена.")
    await callback.answer()


# ── Выбор исходной СК ─
@router.callback_query(CoorStates.waiting_source_crs, F.data.startswith("coor_source_"))
async def handle_source_crs(callback: CallbackQuery, state: FSMContext):
    source_key = callback.data.replace("coor_source_", "")
    await callback.answer()

    await state.update_data(source_crs=source_key)
    await state.set_state(CoorStates.waiting_target_crs)

    source_info = SUPPORTED_CRS[source_key]
    await callback.message.edit_text(
        f"✅ Исходная СК: <b>{source_info['name']}</b>\n"
        f"<i>{source_info['description']}</i>\n\n"
        f"<b>Шаг 2/3:</b> Выберите <b>целевую</b> систему координат:",
        reply_markup=crs_selection_keyboard("coor_target_"),
    )


# ── Выбор целевой СК ──
@router.callback_query(CoorStates.waiting_target_crs, F.data.startswith("coor_target_"))
async def handle_target_crs(callback: CallbackQuery, state: FSMContext):
    target_key = callback.data.replace("coor_target_", "")
    await callback.answer()

    data = await state.get_data()
    source_key = data.get("source_crs")

    if source_key == target_key:
        await callback.answer(
            "Исходная и целевая СК совпадают! Выберите другую.",
            show_alert=True,
        )
        return

    await state.update_data(target_crs=target_key)
    await state.set_state(CoorStates.waiting_file)

    source_info = SUPPORTED_CRS[source_key]
    target_info = SUPPORTED_CRS[target_key]

    await callback.message.edit_text(
        f"✅ Исходная СК: <b>{source_info['name']}</b>\n"
        f"✅ Целевая СК: <b>{target_info['name']}</b>\n\n"
        f"<b>Шаг 3/3:</b> Отправьте <b>.txt</b> файл с координатами.\n"
        f"Формат: <code>№  Описание  X  Y  H</code>",
        reply_markup=cancel_keyboard(),
    )


# ── Приём файла ──
@router.message(CoorStates.waiting_file, F.document)
async def handle_coor_file(message: Message, state: FSMContext, bot: Bot):
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
    temp_output = None

    try:
        temp_input_fd, temp_input_path = tempfile.mkstemp(
            suffix=".txt", prefix="coor_in_"
        )
        os.close(temp_input_fd)
        temp_input = temp_input_path

        temp_output_fd, temp_output_path = tempfile.mkstemp(
            suffix=".txt", prefix="coor_out_"
        )
        os.close(temp_output_fd)
        temp_output = temp_output_path

        tg_file = await bot.get_file(document.file_id)
        await bot.download_file(tg_file.file_path, temp_input)

        with open(temp_input, "r", encoding="utf-8-sig") as f:
            content = f.read()

        data = await state.get_data()
        source_key = data.get("source_crs")
        target_key = data.get("target_crs")

        result = process_coordinate_transformation(content, source_key, target_key)

        with open(temp_output, "w", encoding="utf-8") as f:
            f.write("\n".join(result.corrected_lines))

        # Формируем сводку с оценкой точности
        summary = (
            f"✅ <b>Пересчёт координат выполнен!</b>\n\n"
            f"📊 <b>Параметры преобразования:</b>\n"
            f"  Исходная СК: <code>{result.source_crs}</code>\n"
            f"  Целевая СК: <code>{result.target_crs}</code>\n\n"
            f"📍 Пересчитано точек: <b>{result.total_points}</b>\n"
        )

        if result.skipped_lines > 0:
            summary += f"⚠️ Пропущено строк: {result.skipped_lines}\n\n"
        else:
            summary += "\n"

        if result.height_transform_used:
            summary += (
                f"📏 <b>Трансформация высот активна</b>\n"
                f"<i>Применена геоидная поправка WGS84 ↔ Балтийская 1977</i>\n\n"
            )

        summary += (
            f"🎯 <b>Оценка точности</b> (локальный расчет pyproj):\n"
            f"  Макс. отклонение X: <code>{result.max_dx:.2e}</code>\n"
            f"  Макс. отклонение Y: <code>{result.max_dy:.2e}</code>\n"
            f"  Макс. откл. H: <code>{result.max_dh:.3f}</code>\n\n"
            f"<i>Примечание: без системных грид-файлов горизонтальная точность ~3-4 м.</i>"
        )

        result_doc = FSInputFile(
            temp_output,
            filename=f"coor_{uuid.uuid4().hex[:6]}.txt",
        )
        await message.answer_document(document=result_doc, caption=summary)
        await state.clear()

    except ValueError as e:
        await message.answer(
            f"⚠️ <b>Ошибка:</b>\n\n{html.escape(str(e))}\n\n"
            f"Проверьте формат файла и соответствие координат выбранной СК.",
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
        logger.exception("Непредвиденная ошибка в handle_coor_file")
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


@router.message(CoorStates.waiting_file, F.text)
async def wrong_input_in_coor(message: Message):
    await message.answer(
        "⚠️ Я жду <b>.txt файл</b> с координатами.\n"
        "Отправьте документ или нажмите кнопку отмены.",
        reply_markup=cancel_keyboard(),
    )