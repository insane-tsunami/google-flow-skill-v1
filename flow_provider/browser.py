"""Owned browser context. Never attaches to or cleans up external Chrome."""

import asyncio

from playwright.async_api import async_playwright

from . import settings
from .security import ProfileLock

_playwright = None
_context = None
_page = None
_profile_lock = None
_lock = asyncio.Lock()


def launch_options():
    return {
        "headless": settings.FLOW_HEADLESS,
        "channel": "chrome",
        "chromium_sandbox": not settings.FLOW_UNSAFE_NO_SANDBOX,
        "args": ["--no-sandbox"] if settings.FLOW_UNSAFE_NO_SANDBOX else [],
        "accept_downloads": True,
        "viewport": {"width": 1280, "height": 900},
    }


async def startup():
    global _playwright, _context, _page, _profile_lock
    if _context is not None:
        return
    if settings.FLOW_SESSION_FILE:
        raise ValueError("Legacy storage_state disabled; use a dedicated human-login profile")
    if not settings.FLOW_CHROME_PROFILE:
        raise ValueError("Dedicated profile is required")
    _profile_lock = ProfileLock(settings.FLOW_CHROME_PROFILE).acquire()
    try:
        _playwright = await async_playwright().start()
        _context = await _playwright.chromium.launch_persistent_context(
            user_data_dir=settings.FLOW_CHROME_PROFILE, **launch_options()
        )
        _page = _context.pages[0] if _context.pages else await _context.new_page()
    except BaseException:
        await shutdown()
        raise


async def shutdown():
    global _playwright, _context, _page, _profile_lock
    try:
        if _context:
            await _context.close()
    finally:
        try:
            if _playwright:
                await _playwright.stop()
        finally:
            _playwright = _context = _page = None
            if _profile_lock:
                _profile_lock.close()
                _profile_lock = None


async def get_page():
    if _context is None:
        await startup()
    if _page is None or _page.is_closed():
        # Never restart mid-generation: the job may have consumed credits.
        raise RuntimeError("Owned page closed; resume using persisted job state")
    return _page


def get_lock():
    return _lock
