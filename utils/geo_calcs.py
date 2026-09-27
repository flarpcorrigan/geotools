import math

def dd_to_dms(dd: float) -> tuple:
    """Перевод из десятичных градусов в градусы, минуты, секунды."""
    d = int(dd)
    md = abs(dd - d) * 60
    m = int(md)
    s = (md - m) * 60
    return d, m, s

def dms_to_dd(d: int, m: int, s: float) -> float:
    """Перевод из градусов, минут, секунд в десятичные градусы."""
    sign = -1 if d < 0 else 1
    return sign * (abs(d) + m / 60 + s / 3600)