"""Public lifecycle and durable generation API.

Legacy split configure/submit/latest-download helpers are intentionally no longer
exported: they cannot prove pre-submit settings or attribute an asset safely.
"""

from .browser import get_lock, get_page, shutdown, startup
from .batch import Runner
from .safe_ui import UIAdapter

__all__ = ["startup", "shutdown", "get_page", "get_lock", "Runner", "UIAdapter"]
