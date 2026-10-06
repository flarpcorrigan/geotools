import html
import logging
import os
import tempfile
import uuid

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from utils.helmert import geodetic_to_cartesian, cartesian_to_geodetic, apply_helmert_7param
from utils.calibration_db import load_calibrations, get_calibration

logger = logging.getLogger(__name__)
router = Router()

def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_per")]])

class PerStates(StatesGroup):
    waiting_selection = State()
    waiting_file = State()

@router.message(Command("per"))
async def cmd_per(message: Message, state: FSMContext):
    cals = load_calibrations()
    if not cals:
        await message.answer("📭 База пуста. Используйте /calib.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for i, c in enumerate(cals, 1):
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=f"{i}. {c.area_name} ({c.source_cs} → {c.target_cs})", callback_data=f"per_sel_{c.area_name}")
        ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_per")])

    await state.set_state(PerStates.waiting_selection)
    await message.answer("<b>🔄 Пересчет координат</b>\n\nВыберите калибровку:", reply_markup=kb)

@router.callback_query(PerStates.waiting_selection, F.data.startswith("per_sel_"))
async def handle_selection(callback: CallbackQuery, state: FSMContext):
    area_name = callback.data.replace("per_sel_", "")
    cal = get_calibration(area_name)
    if not cal:
        await callback.answer("Не найдено.", show_alert=True)
        return

    await state.update_data(calib=cal)
    await state.set_state(PerStates.waiting_file)
    await callback.message.edit_text(
        f"✅ Выбрано: <b>{cal.area_name}</b>\n"
        f"🔄 {cal.source_cs} → {cal.target_cs}\n\n"
        f"Отправьте <b>.txt файл</b> для пересчета.\n"
        f"<b>Формат:</b> <code>№  Описание  x  y  h</code>\n"
        f"(разделитель: пробел или табуляция).",
        reply_markup=cancel_kb(),
    )
    await callback.answer()

@router.message(PerStates.waiting_file, F.document)
async def handle_per_file(message: Message, state: FSMContext, bot: Bot):
    doc = message.document
    if not doc.file_name or not doc.file_name.lower().endswith(".txt"):
        await message.answer("⚠️ Только .txt", reply_markup=cancel_kb())
        return
    if doc.file_size and doc.file_size > 1024 * 1024:
        await message.answer("⚠️ Файл > 1 МБ", reply_markup=cancel_kb())
        return

    data = await state.get_data()
    cal = data.get("calib")
    
    temp_in = temp_out = None
    try:
        fd_in, temp_in = tempfile.mkstemp(suffix=".txt")
        os.close(fd_in)
        fd_out, temp_out = tempfile.mkstemp(suffix=".txt")
        os.close(fd_out)

        file_info = await bot.get_file(doc.file_id)
        await bot.download_file(file_info.file_path, temp_in)

        with open(temp_in, "r", encoding="utf-8-sig") as f:
            lines = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]

        out_lines = []
        sum_res = 0.0
        count = 0

        for line in lines:
            parts = line.split()
            if len(parts) < 4: # Минимум №, x, y, h (описание опционально, но по ТЗ оно есть)
                # Пробуем парсить как №, x, y, h
                if len(parts) == 4:
                    pt_id, x_str, y_str, h_str = parts[0], parts[1], parts[2], parts[3]
                    desc = "-"
                else:
                    continue
            else:
                pt_id, desc = parts[0], parts[1]
                x_str, y_str, h_str = parts[2], parts[3], parts[4]

            try:
                x = float(x_str.replace(",", "."))
                y = float(y_str.replace(",", "."))
                h = float(h_str.replace(",", "."))
            except ValueError:
                continue

            # Если исходная была геодезической, конвертируем входные данные (которые мы считаем B,L,H) в X,Y,Z
            # НО: по ТЗ входной файл для /per имеет формат "№, описание, x, y, h". 
            # Мы предполагаем, что пользователь подает координаты в исходной системе.
            # Если исходная система была B,L,H, мы должны интерпретировать входные x,y,h как B,L,H.
            if cal.is_src_geodetic:
                X, Y, Z = geodetic_to_cartesian(x, y, h)
                X_new, Y_new, Z_new = apply_helmert_7param(X, Y, Z, cal.params, to_geodetic=False)
                # Возвращаем в геодезические или оставляем в декартовых? 
                # Обычно пересчет в местную СК дает декартовы x,y,h. Оставим их как есть, или конвертируем обратно?
                # Для универсальности вернем декартовы x,y,h (как X,Y,Z), так как целевая СК обычно плоская.
                x_out, y_out, h_out = X_new, Y_new, Z_new
            else:
                x_out, y_out, h_out = apply_helmert_7param(x, y, h, cal.params, to_geodetic=False)

            out_lines.append(f"{pt_id}\t{desc}\t{x_out:.3f}\t{y_out:.3f}\t{h_out:.3f}")
            count += 1

        if count == 0:
            await message.answer("⚠️ Нет корректных точек.", reply_markup=cancel_kb())
            return

        with open(temp_out, "w", encoding="utf-8") as f:
            f.write("\n".join(out_lines))

        summary = (
            f"✅ <b>Пересчет выполнен!</b>\n\n"
            f"📍 Район: <code>{cal.area_name}</code>\n"
            f"🔄 {cal.source_cs} → {cal.target_cs}\n"
            f"📊 Обработано точек: <b>{count}</b>\n\n"
            f"<b>🎯 Оценка точности калибровки:</b>\n"
            f"  RMS: <code>{cal.params.rms:.4f}</code> м\n"
            f"  Макс. невязка: <code>{cal.params.max_residual:.4f}</code> м"
        )

        result_file = FSInputFile(temp_out, filename=f"result_{cal.area_name}_{uuid.uuid4().hex[:6]}.txt")
        await message.answer_document(document=result_file, caption=summary)
        await state.clear()

    except Exception as e:
        logger.exception("Ошибка пересчета")
        await message.answer(f"❌ Ошибка: {html.escape(str(e))}", reply_markup=cancel_kb())
    finally:
        for p in (temp_in, temp_out):
            if p and os.path.exists(p):
                os.remove(p)

@router.callback_query(F.data == "cancel_per")
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Отменено.")
    await callback.answer()