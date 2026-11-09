"""Authenticated project navigation using the shared selector layer."""

from .browser import get_page
from .media import identifier
from .security import require_auth
from .selectors import control

FLOW_BASE_URL = "https://labs.google/fx/tools/flow"


async def create_project():
    page = await get_page()
    await page.goto(FLOW_BASE_URL, wait_until="domcontentloaded", timeout=60000)
    await require_auth(page)
    await (await control(page, "new_project")).click()
    await page.wait_for_url("**/project/**", timeout=15000)
    value = identifier(page.url.split("/project/", 1)[1].split("?", 1)[0].strip("/"))
    await control(page, "settings")
    return value, page.url


async def navigate_to_project(project_uuid):
    page = await get_page()
    value = identifier(project_uuid)
    await page.goto(
        f"https://flow.google.com/project/{value}", wait_until="domcontentloaded", timeout=60000
    )
    await require_auth(page)
    await control(page, "settings")
