import html
import logging
import os
import tempfile
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from utils.helmert import solve_helmert_7param
from utils.calibration_db import Calibration, save_calibration, validate_name

logger = logging.getLogger(__name__)
router = Router()

def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_calib")]])

class CalibStates(StatesGroup):
    waiting_source_name = State()
    waiting_source_file = State()
    waiting_target_name = State()
    waiting_target_file = State()
    waiting_area_name = State()

@router.message(Command("calib"))
async def cmd_calib(message: Message, state: FSMContext):
    await state.set_state(CalibStates.waiting_source_name)
    await message.answer(
        "<b>🔧 Калибровка (7 параметров Гельмерта)</b>\n\n"
        "<b>Шаг 1/5:</b> Введите <b>название исходной СК</b> (например: WGS84).\n"
        "Для отмены — /cancel",
        reply_markup=cancel_kb(),
    )

@router.message(CalibStates.waiting_source_name, F.text)
async def handle_source_name(message: Message, state: FSMContext):
    await state.update_data(source_cs=message.text.strip())
    await state.set_state(CalibStates.waiting_source_file)
    await message.answer(
        "<b>Шаг 2/5:</b> Отправьте <b>.txt файл</b> с исходными координатами.\n\n"
        "<b>Формат:</b> <code>№  B  L  H</code> или <code>№  x  y  h</code>\n"
        "(разделитель: пробел или табуляция). Минимум 4 точки.",
        reply_markup=cancel_kb(),
    )

@router.message(CalibStates.waiting_source_file, F.document)
async def handle_source_file(message: Message, state: FSMContext, bot: Bot):
    await _process_calib_file(message, state, bot, is_source=True)

@router.message(CalibStates.waiting_target_name, F.text)
async def handle_target_name(message: Message, state: FSMContext):
    await state.update_data(target_cs=message.text.strip())
    await state.set_state(CalibStates.waiting_target_file)
    await message.answer(
        "<b>Шаг 4/5:</b> Отправьте <b>.txt файл</b> с целевыми координатами.\n\n"
        "<b>Формат:</b> <code>№  X  Y  Z</code> (или x, y, h как декартовы).\n"
        "Номера точек должны строго совпадать с первым файлом.",
        reply_markup=cancel_kb(),
    )

@router.message(CalibStates.waiting_target_file, F.document)
async def handle_target_file(message: Message, state: FSMContext, bot: Bot):
    await _process_calib_file(message, state, bot, is_source=False)

async def _process_calib_file(message: Message, state: FSMContext, bot: Bot, is_source: bool):
    doc = message.document
    if not doc.file_name or not doc.file_name.lower().endswith(".txt"):
        await message.answer("⚠️ Только файлы .txt", reply_markup=cancel_kb())
        return
    if doc.file_size and doc.file_size > 1024 * 1024:
        await message.answer("⚠️ Файл слишком большой (макс. 1 МБ)", reply_markup=cancel_kb())
        return

    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        file_info = await bot.get_file(doc.file_id)
        await bot.download_file(file_info.file_path, temp_path)

        with open(temp_path, "r", encoding="utf-8-sig") as f:
            lines = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]

        points = {}
        is_geodetic = False
        for i, line in enumerate(lines, 1):
            parts = line.split()
            if len(parts) < 4:
                continue
            try:
                pt_id = parts[0]
                # Если 4 колонки после ID, считаем что это B, L, H (если первая > 10, это явно градусы)
                # Или просто сохраняем как есть, а тип определим по первой точке
                v1, v2, v3 = float(parts[1].replace(",",".")), float(parts[2].replace(",",".")), float(parts[3].replace(",","."))
                if i == 1 and abs(v1) < 90: # Эвристика: если первая координата < 90, это широта
                    is_geodetic = True
                points[pt_id] = (v1, v2, v3)
            except ValueError:
                continue

        if len(points) < 4:
            await message.answer("⚠️ Найдено менее 4 корректных точек. Проверьте формат.", reply_markup=cancel_kb())
            return

        if is_source:
            await state.update_data(source_points=points, is_src_geodetic=is_geodetic)
            await state.set_state(CalibStates.waiting_target_name)
            await message.answer(
                f"✅ Принято {len(points)} точек.\n\n"
                "<b>Шаг 3/5:</b> Введите <b>название целевой СК</b> (например: СК-63 С1).",
                reply_markup=cancel_kb(),
            )
        else:
            data = await state.get_data()
            src_pts = data.get("source_points", {})
            
            common_ids = list(set(src_pts.keys()) & set(points.keys()))
            if len(common_ids) < 4:
                await message.answer("⚠️ Менее 4 совпадающих номеров точек в файлах.", reply_markup=cancel_kb())
                return

            src_coords = [src_pts[pid] for pid in common_ids]
            tgt_coords = [points[pid] for pid in common_ids]
            
            params = solve_helmert_7param(src_coords, tgt_coords, data.get("is_src_geodetic", False))
            await state.update_data(helmert_params=params, common_ids=common_ids)
            
            await state.set_state(CalibStates.waiting_area_name)
            await message.answer(
                f"✅ <b>Расчет завершен!</b>\n\n"
                f"📊 Точек в расчете: {params.num_points}\n"
                f"🎯 RMS невязки: <code>{params.rms:.4f}</code> м\n"
                f"📏 Макс. невязка: <code>{params.max_residual:.4f}</code> м\n\n"
                f"<b>Шаг 5/5:</b> Введите <b>название района работ</b> для сохранения (например: Гродно_Центр).\n"
                f"(Только буквы, цифры, пробелы, дефисы. 3-50 символов).",
                reply_markup=cancel_kb(),
            )

    except Exception as e:
        logger.exception("Ошибка калибровки")
        await message.answer(f"❌ Ошибка: {html.escape(str(e))}", reply_markup=cancel_kb())
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

@router.message(CalibStates.waiting_area_name, F.text)
async def handle_area_name(message: Message, state: FSMContext):
    area_name = message.text.strip()
    if not validate_name(area_name):
        await message.answer("❌ Некорректное имя. Используйте 3-50 символов (буквы, цифры, пробелы, дефисы).")
        return

    data = await state.get_data()
    calib = Calibration(
        area_name=area_name,
        source_cs=data.get("source_cs", "Unknown"),
        target_cs=data.get("target_cs", "Unknown"),
        params=data["helmert_params"],
        is_src_geodetic=data.get("is_src_geodetic", False),
        created=datetime.now().strftime("%Y-%m-%d %H:%M")
    )

    if save_calibration(calib):
        await state.clear()
        await message.answer(
            f"✅ <b>Калибровка сохранена!</b>\n\n"
            f"📍 Район: <code>{area_name}</code>\n"
            f"🔄 {calib.source_cs} → {calib.target_cs}\n"
            f"🎯 RMS: {calib.params.rms:.4f} м\n\n"
            f"Теперь используйте /per для пересчета."
        )
    else:
        await message.answer("❌ Ошибка сохранения. Попробуйте другое имя.")

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    if await state.get_state() is None:
        await message.answer("Нечего отменять.")
        return
    await state.clear()
    await message.answer("❌ Операция отменена.")

@router.callback_query(F.data == "cancel_calib")
async def cb_cancel(callback, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Отменено.")
    await callback.answer()