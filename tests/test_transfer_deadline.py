import asyncio
from pathlib import Path
import sys

import pytest
from playwright.async_api import Download

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_integration import app


@pytest.mark.asyncio
async def test_browser_transfer_is_bounded_after_download_event(page, tmp_path, monkeypatch):
    from flow_provider.safe_ui import download_asset

    await app(page)
    await page.evaluate("generate()")

    async def delayed_failure(self):
        await asyncio.sleep(1.5)
        return None

    monkeypatch.setattr(Download, "failure", delayed_failure)
    with pytest.raises((TimeoutError, asyncio.TimeoutError)):
        await download_asset(
            page,
            {"type": "image", "file": str(tmp_path / "one.png"), "generation_timeout": 1},
            "asset-1",
        )
    assert not (tmp_path / "one.png").exists()
