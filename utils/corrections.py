import math
import re
from dataclasses import dataclass


_FORBIDDEN_SEPARATORS = re.compile(r"[;|]")


@dataclass
class CorrectionResult:
    """Результат расчёта поправок."""
    fact_num: str
    fact_desc: str
    fact_x: float
    fact_y: float
    fact_h: float
    meas_num: str
    meas_desc: str
    meas_x: float
    meas_y: float
    meas_h: float
    dx: float
    dy: float
    dh: float
    corrected_lines: list[str]
    total_points: int


def _parse_coordinate_line(
    line: str, line_num: int
) -> tuple[str, str, float, float, float]:
    """
    Разбирает одну строку файла.
    Ожидаемый формат: №  Описание  X  Y  H
    Разделитель — ТОЛЬКО пробел или табуляция.
    """
    if _FORBIDDEN_SEPARATORS.search(line):
        raise ValueError(
            f"Строка {line_num}: обнаружен запрещённый разделитель.\n"
            f"Используйте только пробел или табуляцию между колонками."
        )

    parts = line.split()
    if len(parts) < 5:
        raise ValueError(
            f"Строка {line_num}: ожидалось 5 колонок "
            f"(№, Описание, X, Y, H), найдено {len(parts)}.\n"
            f"Содержимое: «{line.strip()}»"
        )

    num = parts[0]
    desc = parts[1]

    try:
        x = float(parts[2].replace(",", "."))
        y = float(parts[3].replace(",", "."))
        h = float(parts[4].replace(",", "."))
    except ValueError:
        raise ValueError(
            f"Строка {line_num}: не удалось распознать числа X, Y, H.\n"
            f"Убедитесь, что координаты записаны числами."
        )

    for val, name in [(x, "X"), (y, "Y"), (h, "H")]:
        if math.isinf(val) or math.isnan(val):
            raise ValueError(
                f"Строка {line_num}: координата {name} имеет недопустимое значение."
            )

    x = round(x, 3)
    y = round(y, 3)
    h = round(h, 3)

    return num, desc, x, y, h


def process_corrections(
    file_content: str,
    fact_line_index: int,
    meas_line_index: int,
    max_lines: int = 10_000,
    max_line_length: int = 1000,
) -> CorrectionResult:
    """
    Главная функция расчёта поправок.

    Args:
        file_content: содержимое файла
        fact_line_index: индекс строки с фактическими координатами (0-based)
        meas_line_index: индекс строки с измеренными координатами (0-based)
        max_lines: максимальное количество строк
        max_line_length: максимальная длина строки

    Алгоритм:
      1. Парсит все строки файла.
      2. Находит строки с фактическими и измеренными координатами по индексам.
      3. Вычисляет поправки: Δ = Факт − Измер.
      4. Применяет поправки ко всем остальным строкам.
    """
    raw_lines = file_content.strip().splitlines()

    for i, ln in enumerate(raw_lines, 1):
        if len(ln) > max_line_length:
            raise ValueError(
                f"Строка {i} слишком длинная ({len(ln)} символов). "
                f"Максимум {max_line_length}."
            )

    lines = [ln for ln in raw_lines if ln.strip()]

    if len(lines) < 3:
        raise ValueError(
            "Файл должен содержать минимум 3 непустые строки."
        )

    if len(lines) > max_lines:
        raise ValueError(
            f"Слишком большой файл ({len(lines)} строк). "
            f"Максимум {max_lines}."
        )

    if fact_line_index < 0 or fact_line_index >= len(lines):
        raise ValueError(
            f"Неверный индекс строки с фактическими данными: {fact_line_index}."
        )

    if meas_line_index < 0 or meas_line_index >= len(lines):
        raise ValueError(
            f"Неверный индекс строки с измеренными данными: {meas_line_index}."
        )

    if fact_line_index == meas_line_index:
        raise ValueError(
            "Строки с фактическими и измеренными данными совпадают."
        )

    # Парсим все строки
    parsed_lines = []
    for i, line in enumerate(lines):
        try:
            num, desc, x, y, h = _parse_coordinate_line(line, i + 1)
            parsed_lines.append((i, num, desc, x, y, h))
        except ValueError:
            continue

    if len(parsed_lines) < 2:
        raise ValueError(
            "Не найдено достаточно корректных строк для обработки."
        )

    # Находим фактические и измеренные данные
    fact_data = None
    meas_data = None

    for idx, num, desc, x, y, h in parsed_lines:
        if idx == fact_line_index:
            fact_data = (num, desc, x, y, h)
        elif idx == meas_line_index:
            meas_data = (num, desc, x, y, h)

    if fact_data is None:
        raise ValueError(
            f"Строка {fact_line_index + 1} не содержит корректных данных."
        )

    if meas_data is None:
        raise ValueError(
            f"Строка {meas_line_index + 1} не содержит корректных данных."
        )

    fact_num, fact_desc, x_fact, y_fact, h_fact = fact_data
    meas_num, meas_desc, x_meas, y_meas, h_meas = meas_data

    # Вычисляем поправки
    dx = x_fact - x_meas
    dy = y_fact - y_meas
    dh = h_fact - h_meas

    # Формируем результат
    corrected_lines = []
    point_count = 0

    for idx, num, desc, x, y, h in parsed_lines:
        if idx == fact_line_index or idx == meas_line_index:
            # Сохраняем исходные строки без изменений
            corrected_lines.append(lines[idx].strip())
        else:
            # Применяем поправки
            x_corr = x + dx
            y_corr = y + dy
            h_corr = h + dh
            corrected_lines.append(
                f"{num}\t{desc}\t{x_corr:.3f}\t{y_corr:.3f}\t{h_corr:.3f}"
            )
            point_count += 1

    if point_count == 0:
        raise ValueError(
            "Не найдено ни одной точки для применения поправок."
        )

    return CorrectionResult(
        fact_num=fact_num,
        fact_desc=fact_desc,
        fact_x=x_fact,
        fact_y=y_fact,
        fact_h=h_fact,
        meas_num=meas_num,
        meas_desc=meas_desc,
        meas_x=x_meas,
        meas_y=y_meas,
        meas_h=h_meas,
        dx=dx,
        dy=dy,
        dh=dh,
        corrected_lines=corrected_lines,
        total_points=point_count,
    )