from pathlib import Path
import sys

from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_safety import FakeAdapter
from test_integration import app


@pytest.mark.asyncio
async def test_existing_destination_blocks_before_configure_or_paid_submit(tmp_path):
    from flow_provider.batch import Runner

    path = tmp_path / "one.png"
    Image.new("RGB", (8, 8)).save(path)
    a = FakeAdapter(tmp_path)
    jobs = [{"name": "one", "type": "image", "file": str(path)}]
    assert await Runner(tmp_path / "manifest.json", jobs, a, backoff=0).run() == 1
    assert a.submits == 0 and a.downloads == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_card", [False, True])
async def test_delayed_known_asset_and_download_action_waits(page, tmp_path, initial_card):
    from flow_provider.safe_ui import download_asset

    await app(page)
    if initial_card:
        await page.evaluate(
            "canvas.innerHTML='<flow-tile-container><img data-media-id=asset-1 src=/reference.png></flow-tile-container>'"
        )
    await page.evaluate("setTimeout(generate, 1000)")
    result = await download_asset(
        page,
        {"file": str(tmp_path / "one.png"), "type": "image", "generation_timeout": 2},
        "asset-1",
    )
    assert result["asset"] == "asset-1"
    assert Path(result["file"]).is_file()


@pytest.mark.asyncio
async def test_known_asset_timeout_is_retryable_and_bounded(page, tmp_path):
    from flow_provider.safe_ui import download_asset

    await app(page)
    with pytest.raises(TimeoutError):
        await download_asset(
            page,
            {"file": str(tmp_path / "one.png"), "type": "image", "generation_timeout": 0.1},
            "asset-1",
        )
    assert not (tmp_path / "one.png").exists()
