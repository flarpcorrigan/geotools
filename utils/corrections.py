import math
import re
from dataclasses import dataclass


# Запрещённые разделители колонок (разрешены только пробел и табуляция)
_FORBIDDEN_SEPARATORS = re.compile(r"[;|]")


@dataclass
class CorrectionResult:
    """Результат расчёта поправок."""
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

    # Округление до 3 знаков
    x = round(x, 3)
    y = round(y, 3)
    h = round(h, 3)

    return num, desc, x, y, h


def process_corrections(
    file_content: str,
    max_lines: int = 10_000,
    max_line_length: int = 1000,
) -> CorrectionResult:
    """
    Главная функция расчёта поправок.

    Алгоритм:
      1. Строка 1 — фактические координаты контрольной точки.
      2. Строка 2 — измеренные координаты той же точки.
      3. Поправка = Факт − Измер (ΔX, ΔY, ΔH).
      4. Поправка прибавляется ко всем корректным строкам начиная с 3-й.
      5. Некорректные строки (комментарии, подписи) игнорируются.
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
            "Файл должен содержать минимум 3 непустые строки:\n"
            "  1 — фактические координаты (Факт)\n"
            "  2 — измеренные координаты (Измер)\n"
            "  3+ — точки для коррекции"
        )

    if len(lines) > max_lines:
        raise ValueError(
            f"Слишком большой файл ({len(lines)} строк). "
            f"Максимум {max_lines}."
        )

    _, _, x_fact, y_fact, h_fact = _parse_coordinate_line(lines[0], 1)
    _, _, x_meas, y_meas, h_meas = _parse_coordinate_line(lines[1], 2)

    dx = x_fact - x_meas
    dy = y_fact - y_meas
    dh = h_fact - h_meas

    corrected_lines: list[str] = []
    corrected_lines.append(lines[0].strip())
    corrected_lines.append(lines[1].strip())

    point_count = 0

    for i in range(2, len(lines)):
        try:
            num, desc, x, y, h = _parse_coordinate_line(lines[i], i + 1)
            x_corr = x + dx
            y_corr = y + dy
            h_corr = h + dh
            corrected_lines.append(
                f"{num}\t{desc}\t{x_corr:.3f}\t{y_corr:.3f}\t{h_corr:.3f}"
            )
            point_count += 1
        except ValueError:
            # Игнорируем "мусорные" строки
            continue

    if point_count == 0:
        raise ValueError(
            "Не найдено ни одной корректной точки для обработки.\n"
            "Проверьте формат файла."
        )

    return CorrectionResult(
        dx=dx,
        dy=dy,
        dh=dh,
        corrected_lines=corrected_lines,
        total_points=point_count,
    )