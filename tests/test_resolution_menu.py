import io
import pytest
from PIL import Image
from flow_provider.safe_ui import download_asset


@pytest.mark.asyncio
@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
@pytest.mark.parametrize("interrupted", [False, True])
async def test_delayed_resolution_subtitle_download_exact_asset(
    page, tmp_path, fmt, interrupted, monkeypatch
):
    png = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(png, format=fmt)
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

    async def run():
        return await download_asset(
            page,
            {"file": str(tmp_path / "asset.png"), "type": "image", "generation_timeout": 2},
            "exact-asset",
        )

    from flow_provider import safe_ui
    from flow_provider.media import recover_output
    import hashlib

    if interrupted:
        real_publish = safe_ui.publish

        def crash(*args):
            result = real_publish(*args)
            assert recover_output(tmp_path / "asset.png", "exact-asset", "image") == result
            raise RuntimeError("simulated crash after publication")

        monkeypatch.setattr(safe_ui, "publish", crash)
        with pytest.raises(RuntimeError, match="simulated crash"):
            await run()
        monkeypatch.setattr(safe_ui, "publish", real_publish)
    result = await run()
    assert result["asset"] == "exact-asset"
    assert result["format"] == "PNG"
    assert result["sha256"] == hashlib.sha256((tmp_path / "asset.png").read_bytes()).hexdigest()
    assert recover_output(tmp_path / "asset.png", "exact-asset", "image") == result
    assert await page.evaluate("window.upscales || 0") == 0
    assert (tmp_path / "asset.png").is_file()
