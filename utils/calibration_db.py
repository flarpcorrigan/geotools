import json
import os
import logging
import shutil
import re
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional

from utils.helmert import Helmert7Params

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
CALIBRATIONS_FILE = os.path.join(DATA_DIR, "calibrations.json")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")

# Разрешены буквы, цифры, пробелы, дефисы, подчеркивания. Длина 3-50 символов.
VALID_NAME_PATTERN = re.compile(r'^[a-zA-Zа-яА-ЯёЁ0-9\s\-_]{3,50}$')

@dataclass
class Calibration:
    area_name: str
    source_cs: str
    target_cs: str
    params: Helmert7Params
    is_src_geodetic: bool
    created: str

    def to_dict(self) -> dict:
        return {
            "area_name": self.area_name,
            "source_cs": self.source_cs,
            "target_cs": self.target_cs,
            "params": {
                "dx": self.params.dx, "dy": self.params.dy, "dz": self.params.dz,
                "wx": self.params.wx, "wy": self.params.wy, "wz": self.params.wz, "m": self.params.m,
                "rms": self.params.rms, "max_residual": self.params.max_residual, "num_points": self.params.num_points
            },
            "is_src_geodetic": self.is_src_geodetic,
            "created": self.created,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Calibration":
        params = Helmert7Params(**data["params"])
        return cls(
            area_name=data["area_name"],
            source_cs=data["source_cs"],
            target_cs=data["target_cs"],
            params=params,
            is_src_geodetic=data.get("is_src_geodetic", False),
            created=data.get("created", ""),
        )

def _ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)

def _create_backup():
    if not os.path.exists(CALIBRATIONS_FILE):
        return
    _ensure_dirs()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"calibrations_{timestamp}.json")
    try:
        shutil.copy2(CALIBRATIONS_FILE, backup_file)
        logger.info(f"Создана резервная копия: {backup_file}")
    except Exception as e:
        logger.warning(f"Не удалось создать бэкап: {e}")

def _cleanup_old_backups(max_backups: int = 5):
    if not os.path.exists(BACKUP_DIR):
        return
    backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith("calibrations_") and f.endswith(".json")])
    while len(backups) > max_backups:
        old_path = os.path.join(BACKUP_DIR, backups.pop(0))
        try:
            os.remove(old_path)
        except Exception:
            pass

def validate_name(name: str) -> bool:
    return bool(name and VALID_NAME_PATTERN.match(name.strip()))

def load_calibrations() -> List[Calibration]:
    if not os.path.exists(CALIBRATIONS_FILE):
        return []
    try:
        with open(CALIBRATIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        cals = []
        for item in data:
            try:
                cals.append(Calibration.from_dict(item))
            except Exception:
                continue # Пропускаем поврежденные записи
        return cals
    except Exception:
        return []

def save_calibration(calib: Calibration) -> bool:
    if not validate_name(calib.area_name):
        logger.error(f"Некорректное имя района: '{calib.area_name}'")
        return False
    
    _ensure_dirs()
    _create_backup()
    
    cals = load_calibrations()
    cals = [c for c in cals if c.area_name != calib.area_name] # Перезапись если имя совпало
    cals.append(calib)
    
    temp_file = CALIBRATIONS_FILE + ".tmp"
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump([c.to_dict() for c in cals], f, indent=2, ensure_ascii=False)
        os.replace(temp_file, CALIBRATIONS_FILE) # Атомарная замена
        _cleanup_old_backups()
        logger.info(f"Сохранена калибровка: {calib.area_name}")
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False

def get_calibration(area_name: str) -> Optional[Calibration]:
    for c in load_calibrations():
        if c.area_name == area_name:
            return c
    return None