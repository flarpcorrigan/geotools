import math
import re
from dataclasses import dataclass, field

from pyproj import CRS, Transformer


# Словарь поддерживаемых систем координат
SUPPORTED_CRS = {
    "wgs84": {
        "name": "WGS84",
        "epsg": 4326,
        "description": "Географические координаты (долгота, широта в градусах)",
        "unit": "°",
        "has_height": True,
        "height_note": "H — эллипсоидальная высота (м)",
    },
    "utm34n": {
        "name": "UTM34N",
        "epsg": 32634,
        "description": "UTM зона 34N (метры)",
        "unit": "м",
        "has_height": False,
        "height_note": "H передаётся без изменений",
    },
    "cs63_c1": {
        "name": "СК-63 зона C1",
        "epsg": 28461,
        "description": "Pulkovo 1942 / Gauss-Kruger zone 1 (метры)",
        "unit": "м",
        "has_height": False,
        "height_note": "H передаётся без изменений",
    },
    "cs63_c2": {
        "name": "СК-63 зона C2",
        "epsg": 28462,
        "description": "Pulkovo 1942 / Gauss-Kruger zone 2 (метры)",
        "unit": "м",
        "has_height": False,
        "height_note": "H передаётся без изменений",
    },
}

_FORBIDDEN_SEPARATORS = re.compile(r"[;|]")


@dataclass
class CoorResult:
    """Результат пересчёта координат."""
    source_crs: str
    target_crs: str
    corrected_lines: list[str]
    total_points: int
    skipped_lines: int
    # Оценка точности
    max_dx: float = 0.0
    max_dy: float = 0.0
    mean_dx: float = 0.0
    mean_dy: float = 0.0
    rms_dx: float = 0.0
    rms_dy: float = 0.0
    max_dh: float = 0.0


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

    return num, desc, x, y, h


def _round_value(value: float, unit: str) -> float:
    """Округление: для градусов — 6 знаков, для метров — 3."""
    if unit == "°":
        return round(value, 6)
    return round(value, 3)


def process_coordinate_transformation(
    file_content: str,
    source_crs_key: str,
    target_crs_key: str,
    max_lines: int = 10_000,
    max_line_length: int = 1000,
) -> CoorResult:
    """
    Пересчитывает координаты из одной СК в другую с оценкой точности.

    Оценка точности выполняется через обратное преобразование:
    исходные координаты → целевая СК → исходная СК,
    затем сравниваются с оригиналом.
    """
    if source_crs_key not in SUPPORTED_CRS:
        raise ValueError(f"Неизвестная исходная СК: {source_crs_key}")
    if target_crs_key not in SUPPORTED_CRS:
        raise ValueError(f"Неизвестная целевая СК: {target_crs_key}")

    source_info = SUPPORTED_CRS[source_crs_key]
    target_info = SUPPORTED_CRS[target_crs_key]

    # Создаём трансформеры: прямой и обратный
    source_crs = CRS.from_epsg(source_info["epsg"])
    target_crs = CRS.from_epsg(target_info["epsg"])

    transformer_forward = Transformer.from_crs(
        source_crs, target_crs, always_xy=True
    )
    transformer_backward = Transformer.from_crs(
        target_crs, source_crs, always_xy=True
    )

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

    corrected_lines = []
    skipped_lines = 0

    # Для оценки точности
    dx_list = []
    dy_list = []
    dh_list = []

    for i, line in enumerate(lines, 1):
        try:
            num, desc, x, y, h = _parse_coordinate_line(line, i)

            # Прямое преобразование
            x_new, y_new = transformer_forward.transform(x, y)
            h_new = h  # Высота передаётся без изменений

            # Округление
            x_new = _round_value(x_new, target_info["unit"])
            y_new = _round_value(y_new, target_info["unit"])
            h_new = round(h_new, 3)

            # Обратное преобразование для оценки точности
            x_back, y_back = transformer_backward.transform(x_new, y_new)

            # Разности в единицах исходной СК
            dx = abs(x - x_back)
            dy = abs(y - y_back)
            dh = abs(h - h_new)  # всегда 0, но считаем для полноты

            dx_list.append(dx)
            dy_list.append(dy)
            dh_list.append(dh)

            corrected_lines.append(
                f"{num}\t{desc}\t{x_new}\t{y_new}\t{h_new}"
            )
        except ValueError:
            # Игнорируем некорректные строки (комментарии, подписи)
            skipped_lines += 1
            continue
        except Exception:
            skipped_lines += 1
            continue

    if len(corrected_lines) == 0:
        raise ValueError(
            "Не найдено ни одной корректной точки.\n"
            "Проверьте формат файла и соответствие координат выбранной СК."
        )

    # Статистика точности
    max_dx = max(dx_list) if dx_list else 0.0
    max_dy = max(dy_list) if dy_list else 0.0
    max_dh = max(dh_list) if dh_list else 0.0

    mean_dx = sum(dx_list) / len(dx_list) if dx_list else 0.0
    mean_dy = sum(dy_list) / len(dy_list) if dy_list else 0.0

    rms_dx = math.sqrt(sum(d * d for d in dx_list) / len(dx_list)) if dx_list else 0.0
    rms_dy = math.sqrt(sum(d * d for d in dy_list) / len(dy_list)) if dy_list else 0.0

    return CoorResult(
        source_crs=source_info["name"],
        target_crs=target_info["name"],
        corrected_lines=corrected_lines,
        total_points=len(corrected_lines),
        skipped_lines=skipped_lines,
        max_dx=max_dx,
        max_dy=max_dy,
        mean_dx=mean_dx,
        mean_dy=mean_dy,
        rms_dx=rms_dx,
        rms_dy=rms_dy,
        max_dh=max_dh,
    )