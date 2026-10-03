import math
import re
from dataclasses import dataclass


_FORBIDDEN_SEPARATORS = re.compile(r"[;|]")


@dataclass
class ZeroResult:
    """Результат перевода в условную систему координат."""
    first_num: str
    first_x: float
    first_y: float
    second_num: str | None
    second_x: float | None
    second_y: float | None
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
    first_num: str,
    second_num: str | None = None,
    max_lines: int = 10_000,
    max_line_length: int = 1000,
) -> ZeroResult:
    """
    Переводит координаты в условную систему.

    Алгоритм:
      1. Парсит все точки из файла.
      2. Находит первую точку (станет началом координат 0, 0).
      3. Если указана вторая точка — выполняет поворот так, чтобы вектор 
         от первой ко второй указывал на север (вдоль оси Y).
      4. Пересчитывает все точки.
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

    # Парсим все точки
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

    # Ищем первую точку
    first_point = None
    for num, x, y in points:
        if num == first_num:
            first_point = (num, x, y)
            break

    if first_point is None:
        raise ValueError(
            f"Первая точка с номером «{first_num}» не найдена в файле."
        )

    _, x1, y1 = first_point

    # Ищем вторую точку (если указана)
    second_point = None
    if second_num is not None:
        for num, x, y in points:
            if num == second_num:
                second_point = (num, x, y)
                break

        if second_point is None:
            raise ValueError(
                f"Вторая точка с номером «{second_num}» не найдена в файле."
            )

        _, x2, y2 = second_point

        # Проверяем, что точки не совпадают
        if x1 == x2 and y1 == y2:
            raise ValueError(
                "Первая и вторая точки совпадают. "
                "Невозможно определить направление на север."
            )

    # Формируем результат
    corrected_lines = []

    if second_point is None:
        # Только сдвиг (без поворота)
        for num, x, y in points:
            x_new = x - x1
            y_new = y - y1
            corrected_lines.append(f"{num}\t{x_new:.3f}\t{y_new:.3f}")
    else:
        # Сдвиг + поворот (ГЕОДЕЗИЧЕСКАЯ система: Север = ось X)
        dx = x2 - x1
        dy = y2 - y1
        r = math.sqrt(dx * dx + dy * dy)

        for num, x, y in points:
            # Сдвиг
            x_shifted = x - x1
            y_shifted = y - y1

            # Поворот (вектор от точки 1 к точке 2 должен указывать на Север, т.е. на ось X)
            x_new = (x_shifted * dx + y_shifted * dy) / r
            y_new = (y_shifted * dx - x_shifted * dy) / r

            corrected_lines.append(f"{num}\t{x_new:.3f}\t{y_new:.3f}")

    return ZeroResult(
        first_num=first_num,
        first_x=x1,
        first_y=y1,
        second_num=second_num,
        second_x=x2 if second_point else None,
        second_y=y2 if second_point else None,
        corrected_lines=corrected_lines,
        total_points=len(points),
    )