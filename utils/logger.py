import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logger():
    """
    Настраивает централизованное логирование с ротацией файлов.
    Логи сохраняются в директорию logs/ и дублируются в консоль.
    """
    # Создаем директорию для логов, если её нет
    os.makedirs("logs", exist_ok=True)
    
    # Форматтер для единообразия всех логов
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Файловый обработчик с ротацией (5 МБ на файл, храним 3 архивных файла)
    file_handler = RotatingFileHandler(
        "logs/bot.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    
    # Консольный обработчик
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # Настройка корневого логгера (force=True очищает старые обработчики, если они были)
    logging.basicConfig(
        level=logging.INFO,
        handlers=[file_handler, console_handler],
        force=True
    )
    
    # Настройка специального логгера для событий безопасности
    # Он автоматически унаследует обработчики (файл + консоль) от корневого логгера
    security_logger = logging.getLogger("geoTOOLS_SECURITY")
    security_logger.setLevel(logging.INFO)
    
    return logging.getLogger(__name__)