import os
import shutil
import pytest_asyncio
from playwright.async_api import async_playwright


@pytest_asyncio.fixture
async def page():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=os.getenv("TEST_CHROMIUM") or shutil.which("chromium"), headless=True
        )
        context = await browser.new_context(offline=True)
        page = await context.new_page()
        yield page
        await browser.close()
