# handlers/__init__.py
from .common import router as common_router
from .corrections import router as corrections_router
from .zero import router as zero_router
from .calib import router as calib_router
from .per import router as per_router
from .admin_router import router as admin_router 

__all__ = [
    "common_router",
    "corrections_router",
    "zero_router",
    "calib_router",
    "per_router",
    "admin_router",
]