import html
import logging
import os
import tempfile
import uuid

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile, Message

from utils.corrections import process_corrections

logger = logging.getLogger(__name__)
router = Router()

MAX_FILE_SIZE = 1 * 1024 * 1024  # 1 МБ


class CorrectionStates(StatesGroup):
    waiting_file = State()


@router.message(Command("cor"))
async def cmd_cor(message: Message, state: FSMContext):
    await state.set_state(CorrectionStates.waiting_file)
    await message.answer(
        "<b>📐 Ввод поправок в полевые измерения</b>\n\n"
        "Эта функция рассчитывает поправки по контрольной точке "
        "и автоматически применяет их ко всем остальным точкам.\n\n"
        "<b>Формат .txt файла</b> (разделитель — только пробел или табуляция):\n"
        "<code>№  Описание  X  Y  H</code>\n\n"
        "• <b>Строка 1</b> — фактические координаты контрольной точки\n"
        "• <b>Строка 2</b> — измеренные координаты той же точки\n"
        "• <b>Строки 3+</b> — точки, к которым применится поправка\n\n"
        "<i>✨ Координаты автоматически округляются до 3 знаков после запятой.</i>\n"
        "<i>✨ Лишние строки (комментарии, подписи) игнорируются.</i>\n\n"
        "<b>Пример файла:</b>\n"
        "<code>1 Факт  5000.123 3000.456 100.789\n"
        "2 Измер 5000.000 3000.500 100.700\n"
        "3 Тчк1  4999.500 3001.200 101.300\n"
        "4 Тчк2  5001.100 2999.800  99.500\n"
        "# Конец файла (игнорируется)</code>\n\n"
        "📎 Отправьте <b>.txt</b> файл для обработки.\n"
        "Для отмены — /cancel"
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    current = await state.get_state()
    if current is None:
        await message.answer("Нечего отменять.")
        return
    await state.clear()
    await message.answer("❌ Операция отменена.")


@router.message(CorrectionStates.waiting_file, F.document)
async def handle_cor_file(message: Message, state: FSMContext, bot: Bot):
    document = message.document
    file_name = document.file_name or ""

    if not file_name.lower().endswith(".txt"):
        await message.answer(
            "⚠️ Поддерживаются только файлы <b>.txt</b>.\n"
            "Отправьте правильный файл или /cancel."
        )
        return

    if document.file_size and document.file_size > MAX_FILE_SIZE:
        await message.answer(
            f"⚠️ Файл слишком большой "
            f"({document.file_size // 1024} КБ). "
            f"Максимум {MAX_FILE_SIZE // 1024} КБ."
        )
        return

    temp_input = None
    temp_output = None

    try:
        # Безопасное создание временных файлов (права 0600)
        temp_input_fd, temp_input_path = tempfile.mkstemp(
            suffix=".txt", prefix="geo_in_"
        )
        os.close(temp_input_fd)
        temp_input = temp_input_path

        temp_output_fd, temp_output_path = tempfile.mkstemp(
            suffix=".txt", prefix="geo_out_"
        )
        os.close(temp_output_fd)
        temp_output = temp_output_path

        # Скачиваем файл
        tg_file = await bot.get_file(document.file_id)
        await bot.download_file(tg_file.file_path, temp_input)

        # Читаем (utf-8-sig убирает BOM)
        with open(temp_input, "r", encoding="utf-8-sig") as f:
            content = f.read()

        # Считаем поправки
        result = process_corrections(content)

        # Записываем результат
        with open(temp_output, "w", encoding="utf-8") as f:
            f.write("\n".join(result.corrected_lines))

        # Сводка
        summary = (
            f"✅ <b>Поправки рассчитаны и применены!</b>\n\n"
            f"📊 <b>Поправки (Факт − Измер):</b>\n"
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
            f"⚠️ <b>Ошибка в файле:</b>\n\n{html.escape(str(e))}\n\n"
            f"Исправьте файл и отправьте снова, или /cancel."
        )
    except UnicodeDecodeError:
        await message.answer(
            "⚠️ Не удалось прочитать файл.\n"
            "Убедитесь, что кодировка — <b>UTF-8</b> "
            "(не Windows-1251)."
        )
    except Exception:
        logger.exception("Непредвиденная ошибка в handle_cor_file")
        await message.answer(
            "❌ Внутренняя ошибка при обработке. "
            "Попробуйте другой файл или сообщите разработчику."
        )
    finally:
        for path in (temp_input, temp_output):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    logger.warning("Не удалось удалить %s", path)


@router.message(CorrectionStates.waiting_file, F.text)
async def wrong_input_in_cor(message: Message):
    await message.answer(
        "⚠️ Я жду <b>.txt файл</b> с координатами.\n"
        "Отправьте документ или /cancel для отмены."
    )