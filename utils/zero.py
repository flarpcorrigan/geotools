import math
import re
from dataclasses import dataclass


_FORBIDDEN_SEPARATORS = re.compile(r"[;|]")


@dataclass
class ZeroResult:
    """Результат перевода в условную систему координат."""
    selected_num: str
    selected_x: float
    selected_y: float
    corrected_lines: list[str]
    total_points: int


def _parse_coordinate_line(line: str, line_num: int) -> tuple[str, float, float]:
    """
    Разбирает одну строку файла.
    Ожидаемый формат: №  X  Y
    Разделитель — ТОЛЬКО пробел или табуляция.
    """
    if _FORBIDDEN_SEPARATORS.search(line):
        raise ValueError(
            f"Строка {line_num}: обнаружен запрещённый разделитель.\n"
            f"Используйте только пробел или табуляцию между колонками."
        )

    parts = line.split()
    if len(parts) < 3:
        raise ValueError(
            f"Строка {line_num}: ожидалось 3 колонки "
            f"(№, X, Y), найдено {len(parts)}.\n"
            f"Содержимое: «{line.strip()}»"
        )

    num = parts[0]

    try:
        x = float(parts[1].replace(",", "."))
        y = float(parts[2].replace(",", "."))
    except ValueError:
        raise ValueError(
            f"Строка {line_num}: не удалось распознать числа X, Y.\n"
            f"Убедитесь, что координаты записаны числами."
        )

    for val, name in [(x, "X"), (y, "Y")]:
        if math.isinf(val) or math.isnan(val):
            raise ValueError(
                f"Строка {line_num}: координата {name} имеет недопустимое значение."
            )

    x = round(x, 3)
    y = round(y, 3)

    return num, x, y


def process_zero_transformation(
    file_content: str,
    selected_num: str,
    max_lines: int = 10_000,
    max_line_length: int = 1000,
) -> ZeroResult:
    """
    Переводит координаты в условную систему относительно выбранной точки.

    Алгоритм:
      1. Парсит все точки из файла.
      2. Находит выбранную точку по номеру.
      3. Пересчитывает все точки: X_new = X_old - X_selected, Y_new = Y_old - Y_selected.
    """
    raw_lines = file_content.strip().splitlines()

    for i, ln in enumerate(raw_lines, 1):
        if len(ln) > max_line_length:
            raise ValueError(
                f"Строка {i} слишком длинная ({len(ln)} символов). "
                f"Максимум {max_line_length}."
            )

    lines = [ln for ln in raw_lines if ln.strip()]

    if len(lines) < 1:
        raise ValueError("Файл пуст или содержит только пустые строки.")

    if len(lines) > max_lines:
        raise ValueError(
            f"Слишком большой файл ({len(lines)} строк). "
            f"Максимум {max_lines}."
        )

    points = []
    for i, line in enumerate(lines, 1):
        try:
            num, x, y = _parse_coordinate_line(line, i)
            points.append((num, x, y))
        except ValueError:
            continue

    if len(points) == 0:
        raise ValueError(
            "Не найдено ни одной корректной точки.\n"
            "Проверьте формат файла."
        )

    selected_point = None
    for num, x, y in points:
        if num == selected_num:
            selected_point = (num, x, y)
            break

    if selected_point is None:
        raise ValueError(
            f"Точка с номером «{selected_num}» не найдена в файле."
        )

    _, x_sel, y_sel = selected_point

    corrected_lines = []
    for num, x, y in points:
        x_new = x - x_sel
        y_new = y - y_sel
        corrected_lines.append(f"{num}\t{x_new:.3f}\t{y_new:.3f}")

    return ZeroResult(
        selected_num=selected_num,
        selected_x=x_sel,
        selected_y=y_sel,
        corrected_lines=corrected_lines,
        total_points=len(points),
    )