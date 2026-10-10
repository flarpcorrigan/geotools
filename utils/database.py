import aiosqlite
import logging
from datetime import datetime

# Выделенный логгер для событий безопасности
security_logger = logging.getLogger("geoTOOLS_SECURITY")
security_logger.setLevel(logging.INFO)
# Формат: [SECURITY] 2023-10-27 15:30:00 - BLOCKED: user_id=123, username=@badactor
formatter = logging.Formatter("[SECURITY] %(asctime)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
if not security_logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    security_logger.addHandler(ch)

DB_PATH = "access.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Включаем WAL mode для устойчивости к сбоям и конкурентного доступа
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute('''
            CREATE TABLE IF NOT EXISTS allowed_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.commit()

async def is_allowed(user_id: int, admin_id: int) -> bool:
    return user_id == admin_id or await _check_user_in_db(user_id)

async def _check_user_in_db(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT 1 FROM allowed_users WHERE user_id = ?', (user_id,))
        return await cursor.fetchone() is not None

async def add_user(user_id: int, username: str, admin_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT OR REPLACE INTO allowed_users (user_id, username, added_by) 
            VALUES (?, ?, ?)
        ''', (user_id, username, admin_id))
        await db.commit()
    security_logger.info(f"GRANTED: user_id={user_id}, username=@{username}, by admin={admin_id}")

async def remove_user(user_id: int, admin_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM allowed_users WHERE user_id = ?', (user_id,))
        await db.commit()
    security_logger.info(f"REVOKED: user_id={user_id}, by admin={admin_id}")

async def get_all_users() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT user_id, username FROM allowed_users')
        return await cursor.fetchall()

async def log_unauthorized_access(user_id: int, username: str | None):
    """Логирует попытку доступа без прав"""
    security_logger.warning(f"BLOCKED: user_id={user_id}, username=@{username or 'None'}")