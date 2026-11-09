import io
import pytest
from PIL import Image
from flow_provider.safe_ui import download_asset


@pytest.mark.asyncio
async def test_delayed_resolution_subtitle_download_exact_asset(page, tmp_path):
    png = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(png, format="PNG")
    await page.route(
        "https://download.test/original",
        lambda route: route.fulfill(
            body=png.getvalue(),
            content_type="image/png",
            headers={"Content-Disposition": 'attachment; filename="original.png"'},
        ),
    )
    await page.set_content("""<flow-grid-tile-container><flow-tile-container>
    <img data-media-id="exact-asset"><button aria-label="Download" aria-haspopup="menu"
    onclick="setTimeout(()=>document.querySelector('[role=menu]').hidden=false,100)">Download</button>
    </flow-tile-container></flow-grid-tile-container>
    <div role="menu" hidden><a role="menuitem" href="https://download.test/original">1K <span>Tamanho original</span></a>
    <button role="menuitem" onclick="window.upscales=1">2K<span>Aprimorada</span></button></div>""")
    result = await download_asset(
        page,
        {"file": str(tmp_path / "asset.png"), "type": "image", "generation_timeout": 2},
        "exact-asset",
    )
    assert result["asset"] == "exact-asset"
    assert await page.evaluate("window.upscales || 0") == 0
    assert (tmp_path / "asset.png").is_file()
