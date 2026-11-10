"""Account-scoped navigation; authentication never selects a requested account."""

import os
import re
from urllib.parse import urlsplit

from .browser import get_page
from .media import identifier
from .security import require_auth
from .selectors import control

FLOW_BASE_URL = "https://labs.google/fx/tools/flow"


def account_index():
    value = os.environ.get("FLOW_ACCOUNT_INDEX")
    if value is not None and not re.fullmatch(r"0|[1-9][0-9]*", value):
        raise ValueError("Invalid explicit account index")
    return value


_UNSET = object()


def flow_url(expected=_UNSET):
    account = account_index() if expected is _UNSET else expected
    return f"https://flow.google.com/u/{account}/" if account is not None else FLOW_BASE_URL


def verify_account(url, expected=_UNSET):
    requested = account_index() if expected is _UNSET else expected
    parsed = urlsplit(url)
    prefixes = {
        "labs.google": "/fx/tools/flow/u/",
        "flow.google.com": "/u/",
    }
    prefix = prefixes.get(parsed.netloc)
    if requested is not None and (
        parsed.scheme != "https"
        or prefix is None
        or not re.match(rf"^{prefix}{re.escape(requested)}(?:/|$)", parsed.path)
    ):
        raise ValueError("Requested account scope unconfirmed")


async def create_project(*, expected=_UNSET):
    expected = account_index() if expected is _UNSET else expected
    page = await get_page()
    await page.goto(flow_url(expected), wait_until="domcontentloaded", timeout=60000)
    await require_auth(page)
    verify_account(page.url, expected)
    await (await control(page, "new_project")).click()
    await page.wait_for_url("**/project/**", timeout=15000)
    verify_account(page.url, expected)
    value = identifier(page.url.split("/project/", 1)[1].split("?", 1)[0].strip("/"))
    return value, page.url


async def navigate_to_project(project_uuid, *, expected=_UNSET):
    expected = account_index() if expected is _UNSET else expected
    page = await get_page()
    value = identifier(project_uuid)
    url = (
        f"{flow_url(expected).rstrip('/')}/project/{value}"
        if expected is not None
        else f"https://flow.google.com/project/{value}"
    )
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await require_auth(page)
    verify_account(page.url, expected)


def explicit_project(value, expected):
    """Parse only an explicit ID or canonical account-scoped project URL."""
    if expected is None:
        raise ValueError("Existing project requires explicit FLOW_ACCOUNT_INDEX")
    if not isinstance(value, str):
        raise ValueError("Project must be a URL or ID")
    if "://" not in value:
        return identifier(value)
    parsed = urlsplit(value)
    verify_account(value, expected)
    prefix = "/fx/tools/flow" if parsed.netloc == "labs.google" else ""
    match = re.fullmatch(
        rf"{prefix}/u/{re.escape(expected)}/project/([A-Za-z0-9_-]+)/?", parsed.path
    )
    if not match or parsed.query or parsed.fragment:
        raise ValueError("Expected canonical account-scoped project URL")
    return identifier(match.group(1))


def verify_project(url, project, expected):
    if expected is not None:
        if explicit_project(url, expected) != project:
            raise ValueError("Project identity changed")
    else:
        verify_account(url, expected)
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc not in ("flow.google.com", "labs.google"):
            raise ValueError("Project origin unconfirmed")
        match = re.fullmatch(r"(?:/fx/tools/flow)?/project/([A-Za-z0-9_-]+)/?", parsed.path)
        if not match or match.group(1) != project:
            raise ValueError("Project identity changed")
