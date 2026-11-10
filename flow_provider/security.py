"""Kernel-owned profile exclusion; no Chrome lock deletion or PID killing."""

import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from .selectors import control


class ProfileLock:
    def __init__(self, profile):
        self.profile = Path(profile).resolve()
        self.handle = None

    def acquire(self):
        self.profile.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.profile.chmod(0o700)
        target = self.profile / ".flow-automation.lock"
        if target.is_symlink():
            raise RuntimeError("Unsafe automation lock")
        fd = os.open(target, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        self.handle = os.fdopen(fd, "r+")
        try:
            if os.name == "nt":
                import msvcrt

                if target.stat().st_size == 0:
                    self.handle.write(" ")
                    self.handle.flush()
                self.handle.seek(0)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            self.handle = None
            raise RuntimeError("Profile busy: another automation owns the lock") from None
        self.handle.seek(0)
        self.handle.truncate()
        json.dump({"pid": os.getpid(), "uid": getattr(os, "getuid", lambda: None)()}, self.handle)
        self.handle.flush()
        return self

    def close(self):
        if self.handle:
            # Closing releases the OS lock even after process death. Never unlink:
            # unlinking would permit a second process to lock a different inode.
            self.handle.close()
            self.handle = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *args):
        self.close()


async def auth_state(page, *, trusted=False):
    host = urlsplit(page.url).hostname
    if host == "accounts.google.com":
        return "login_required"
    if not trusted and host not in ("labs.google", "flow.google.com"):
        return "unverifiable"
    if await control(page, "login", optional=True) is not None:
        return "login_required"
    if await control(page, "new_project", optional=True) is not None:
        return "authenticated"
    if "/project/" in page.url:
        if await control(page, "settings", optional=True) is not None:
            return "authenticated"
        # Agent projects expose no direct-model settings. Require the project
        # shell, home navigation and an actual composer, not a generic tune icon.
        project = page.locator("flow-project-shell flow-project-page")
        if (
            await project.count() == 1
            and await control(page, "home", optional=True) is not None
            and await control(page, "editor", optional=True) is not None
        ):
            return "authenticated"
    return "unverifiable"


async def require_auth(page):
    deadline = asyncio.get_running_loop().time() + 15
    while True:
        state = await auth_state(page)
        if state != "unverifiable" or asyncio.get_running_loop().time() >= deadline:
            break
        await asyncio.sleep(0.25)
    if state != "authenticated":
        raise ValueError(f"Authentication {state}; run flow.py login for human login")
