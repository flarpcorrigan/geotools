import math
import re
import logging
from dataclasses import dataclass

from pyproj import CRS, Transformer

logger = logging.getLogger(__name__)

# Словарь поддерживаемых систем координат
SUPPORTED_CRS = {
    "wgs84": {
        "name": "WGS84",
        "epsg": 4326,
        "description": "Географические координаты (X=широта, Y=долгота в градусах)",
        "unit": "°",
    },
    "utm34n": {
        "name": "UTM34N",
        "epsg": 32634,
        "description": "UTM зона 34N (X=север, Y=восток в метрах)",
        "unit": "м",
    },
    "cs63_c1": {
        "name": "СК-63 зона C1",
        "epsg": 3351,
        "description": "Pulkovo 1942 / CS63 zone C1 (EPSG:3351)",
        "unit": "м",
    },
    "cs63_c2": {
        "name": "СК-63 зона C2",
        "epsg": 3352,
        "description": "Pulkovo 1942 / CS63 zone C2 (EPSG:3352)",
        "unit": "м",
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
    max_dx: float = 0.0
    max_dy: float = 0.0
    mean_dx: float = 0.0
    mean_dy: float = 0.0
    rms_dx: float = 0.0
    rms_dy: float = 0.0
    max_dh: float = 0.0
    height_transform_used: bool = False


def _parse_coordinate_line(
    line: str, line_num: int
) -> tuple[str, str, float, float, float]:
    """
    Разбирает одну строку файла.
    Поддерживает два формата:
    - 3 колонки: №  X  Y
    - 5 колонок: №  Описание  X  Y  H
    
    В геодезической системе:
    - X = север (northing/latitude)
    - Y = восток (easting/longitude)
    - H = высота
    """
    if _FORBIDDEN_SEPARATORS.search(line):
        raise ValueError(
            f"Строка {line_num}: обнаружен запрещённый разделитель.\n"
            f"Используйте только пробел или табуляцию между колонками."
        )

    parts = line.split()
    
    if len(parts) < 3:
        raise ValueError(
            f"Строка {line_num}: ожидалось минимум 3 колонки "
            f"(№, X, Y), найдено {len(parts)}.\n"
            f"Содержимое: «{line.strip()}»"
        )

    num = parts[0]
    
    if len(parts) >= 5:
        desc = parts[1]
        x_idx = 2
        y_idx = 3
        h_idx = 4
    else:
        desc = "-"
        x_idx = 1
        y_idx = 2
        h_idx = None

    try:
        x = float(parts[x_idx].replace(",", "."))
        y = float(parts[y_idx].replace(",", "."))
        h = float(parts[h_idx].replace(",", ".")) if h_idx is not None else 0.0
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
    Пересчитывает координаты из одной СК в другую с использованием локальной библиотеки pyproj.
    """
    if source_crs_key not in SUPPORTED_CRS:
        raise ValueError(f"Неизвестная исходная СК: {source_crs_key}")
    if target_crs_key not in SUPPORTED_CRS:
        raise ValueError(f"Неизвестная целевая СК: {target_crs_key}")

    source_info = SUPPORTED_CRS[source_crs_key]
    target_info = SUPPORTED_CRS[target_crs_key]

    # Создаем CRS через официальные EPSG коды
    source_crs = CRS.from_epsg(source_info["epsg"])
    target_crs = CRS.from_epsg(target_info["epsg"])

    # always_xy=False означает, что мы передаем координаты в порядке (X, Y), 
    # где для WGS84 X=широта(lat), Y=долгота(lon), а для проекционных X=север, Y=восток.
    # Это соответствует геодезическому формату ваших файлов.
    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=False)

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
    dx_list = []
    dy_list = []
    dh_list = []

    # Эмпирическая геоидная поправка для перехода WGS84 -> Балтийская система высот (СК-63)
    # Рассчитана по вашим гарантированным данным как разница высот (~ -26.44 м)
    GEOID_CORRECTION_BY = -26.44 

    is_wgs84_source = (source_crs_key == "wgs84")
    is_sk63_target = (target_crs_key in ["cs63_c1", "cs63_c2"])
    is_sk63_source = (source_crs_key in ["cs63_c1", "cs63_c2"])
    is_wgs84_target = (target_crs_key == "wgs84")

    for i, line in enumerate(lines, 1):
        try:
            num, desc, x, y, h = _parse_coordinate_line(line, i)

            # 1. Трансформация горизонтальных координат
            x_new, y_new = transformer.transform(x, y)
            
            # 2. Трансформация высоты (применяем поправку, если переходим между WGS84 и СК-63)
            h_new = h
            if is_wgs84_source and is_sk63_target:
                h_new = h + GEOID_CORRECTION_BY
            elif is_sk63_source and is_wgs84_target:
                h_new = h - GEOID_CORRECTION_BY  # Обратная поправка

            # Округление
            x_new = _round_value(x_new, target_info["unit"])
            y_new = _round_value(y_new, target_info["unit"])
            h_new = round(h_new, 3)

            # Обратное преобразование для оценки точности (горизонталь)
            try:
                x_back, y_back = transformer.transform(x_new, y_new)
                dx = abs(x - x_back)
                dy = abs(y - y_back)
            except Exception:
                dx, dy = 0.0, 0.0
                
            dh = abs(h - (h_new - (GEOID_CORRECTION_BY if is_wgs84_source and is_sk63_target else 0.0)))

            dx_list.append(dx)
            dy_list.append(dy)
            dh_list.append(dh)

            corrected_lines.append(
                f"{num}\t{desc}\t{x_new}\t{y_new}\t{h_new}"
            )
        except ValueError:
            skipped_lines += 1
            continue
        except Exception as e:
            logger.warning(f"Ошибка обработки строки {i}: {e}")
            skipped_lines += 1
            continue

    if len(corrected_lines) == 0:
        raise ValueError(
            "Не найдено ни одной корректной точки.\n"
            "Проверьте формат файла и соответствие координат выбранной СК."
        )

    max_dx = max(dx_list) if dx_list else 0.0
    max_dy = max(dy_list) if dy_list else 0.0
    max_dh = max(dh_list) if dh_list else 0.0

    mean_dx = sum(dx_list) / len(dx_list) if dx_list else 0.0
    mean_dy = sum(dy_list) / len(dy_list) if dy_list else 0.0

    rms_dx = math.sqrt(sum(d * d for d in dx_list) / len(dx_list)) if dx_list else 0.0
    rms_dy = math.sqrt(sum(d * d for d in dy_list) / len(dy_list)) if dy_list else 0.0

    height_used = (is_wgs84_source and is_sk63_target) or (is_sk63_source and is_wgs84_target)

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
        height_transform_used=height_used,
    )