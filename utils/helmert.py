import math
from dataclasses import dataclass
from typing import List, Tuple

# Параметры эллипсоида WGS-84 (для конвертации B,L,H если они поданы)
A_WGS84 = 6378137.0
F_WGS84 = 1 / 298.257223563
E2_WGS84 = 2 * F_WGS84 - F_WGS84**2

@dataclass
class Helmert7Params:
    dx: float
    dy: float
    dz: float
    wx: float  # в радианах
    wy: float
    wz: float
    m: float   # масштаб (доля единицы, например 0.000001)
    rms: float
    max_residual: float
    num_points: int

def geodetic_to_cartesian(B_deg: float, L_deg: float, H: float) -> Tuple[float, float, float]:
    """Конвертация B, L, H (градусы, метры) в X, Y, Z (метры) на эллипсоиде WGS84."""
    B = math.radians(B_deg)
    L = math.radians(L_deg)
    N = A_WGS84 / math.sqrt(1 - E2_WGS84 * (math.sin(B)**2))
    X = (N + H) * math.cos(B) * math.cos(L)
    Y = (N + H) * math.cos(B) * math.sin(L)
    Z = (N * (1 - E2_WGS84) + H) * math.sin(B)
    return X, Y, Z

def cartesian_to_geodetic(X: float, Y: float, Z: float) -> Tuple[float, float, float]:
    """Конвертация X, Y, Z в B, L, H (градусы, метры)."""
    L = math.atan2(Y, X)
    p = math.sqrt(X**2 + Y**2)
    B = math.atan2(Z, p * (1 - E2_WGS84))
    
    # Итерации для точного B
    for _ in range(5):
        N = A_WGS84 / math.sqrt(1 - E2_WGS84 * (math.sin(B)**2))
        H_new = p / math.cos(B) - N
        B = math.atan2(Z, p * (1 - E2_WGS84 * N / (N + H_new)))
    
    H = p / math.cos(B) - (A_WGS84 / math.sqrt(1 - E2_WGS84 * (math.sin(B)**2)))
    return math.degrees(B), math.degrees(L), H

def solve_helmert_7param(
    src_coords: List[Tuple[float, float, float]], # X, Y, Z или B, L, H (будет конвертировано)
    tgt_coords: List[Tuple[float, float, float]], # X, Y, Z
    is_src_geodetic: bool
) -> Helmert7Params:
    """Решает 7-параметрическое преобразование Гельмерта методом МНК."""
    n = len(src_coords)
    if n < 4:
        raise ValueError("Для 7 параметров нужно минимум 4 точки.")
    
    # Подготовка матриц A (3n x 7) и L (3n x 1)
    A = []
    L_vec = []
    
    residuals = []
    
    for i in range(n):
        if is_src_geodetic:
            X1, Y1, Z1 = geodetic_to_cartesian(*src_coords[i])
        else:
            X1, Y1, Z1 = src_coords[i]
            
        X2, Y2, Z2 = tgt_coords[i]
        
        # Строки матрицы A для одной точки (параметры: dX, dY, dZ, wx, wy, wz, m)
        A.append([1.0, 0.0, 0.0,  0.0,  Z1, -Y1,  X1])
        A.append([0.0, 1.0, 0.0, -Z1,  0.0,  X1,  Y1])
        A.append([0.0, 0.0, 1.0,  Y1, -X1,  0.0,  Z1])
        
        L_vec.append(X2 - X1)
        L_vec.append(Y2 - Y1)
        L_vec.append(Z2 - Z1)
        
    # Решение нормальных уравнений: params = (A^T * A)^(-1) * A^T * L
    params = _solve_least_squares(A, L_vec)
    dx, dy, dz, wx, wy, wz, m = params
    
    # Оценка точности (невязки)
    max_res = 0.0
    sum_sq_res = 0.0
    
    for i in range(n):
        if is_src_geodetic:
            X1, Y1, Z1 = geodetic_to_cartesian(*src_coords[i])
        else:
            X1, Y1, Z1 = src_coords[i]
            
        X2, Y2, Z2 = tgt_coords[i]
        
        X_calc = X1 + dx + m*X1 + wy*Z1 - wz*Y1
        Y_calc = Y1 + dy + m*Y1 + wz*X1 - wx*Z1
        Z_calc = Z1 + dz + m*Z1 + wx*Y1 - wy*X1
        
        res = math.sqrt((X2 - X_calc)**2 + (Y2 - Y_calc)**2 + (Z2 - Z_calc)**2)
        residuals.append(res)
        if res > max_res:
            max_res = res
        sum_sq_res += res**2
        
    rms = math.sqrt(sum_sq_res / (3 * n - 7)) if (3 * n - 7) > 0 else 0.0
    
    return Helmert7Params(
        dx=dx, dy=dy, dz=dz, wx=wx, wy=wy, wz=wz, m=m,
        rms=rms, max_residual=max_res, num_points=n
    )

def apply_helmert_7param(
    X: float, Y: float, Z: float,
    params: Helmert7Params,
    to_geodetic: bool = False
) -> Tuple[float, float, float]:
    """Применяет 7 параметров к точке. Возвращает X,Y,Z или B,L,H."""
    X_new = X + params.dx + params.m*X + params.wy*Z - params.wz*Y
    Y_new = Y + params.dy + params.m*Y + params.wz*X - params.wx*Z
    Z_new = Z + params.dz + params.m*Z + params.wx*Y - params.wy*X
    
    if to_geodetic:
        return cartesian_to_geodetic(X_new, Y_new, Z_new)
    return X_new, Y_new, Z_new

def _solve_least_squares(A: List[List[float]], L: List[float]) -> List[float]:
    """Решает СЛАУ методом Гаусса для нормальных уравнений МНК."""
    rows = len(A)
    cols = len(A[0])
    
    # A^T * A
    ATA = [[0.0] * cols for _ in range(cols)]
    for i in range(cols):
        for j in range(cols):
            for k in range(rows):
                ATA[i][j] += A[k][i] * A[k][j]
                
    # A^T * L
    ATL = [0.0] * cols
    for i in range(cols):
        for k in range(rows):
            ATL[i] += A[k][i] * L[k]
            
    return _gauss_elimination(ATA, ATL)

def _gauss_elimination(A: List[List[float]], b: List[float]) -> List[float]:
    n = len(b)
    aug = [row[:] + [b[i]] for i, row in enumerate(A)]
    
    for i in range(n):
        max_row = i
        for k in range(i + 1, n):
            if abs(aug[k][i]) > abs(aug[max_row][i]):
                max_row = k
        aug[i], aug[max_row] = aug[max_row], aug[i]
        
        if abs(aug[i][i]) < 1e-12:
            raise ValueError("Матрица вырождена. Проверьте геометрию точек (они не должны лежать на одной прямой/плоскости).")
            
        for k in range(i + 1, n):
            factor = aug[k][i] / aug[i][i]
            for j in range(i, n + 1):
                aug[k][j] -= factor * aug[i][j]
                
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = aug[i][n]
        for j in range(i + 1, n):
            x[i] -= aug[i][j] * x[j]
        x[i] /= aug[i][i]
    return x