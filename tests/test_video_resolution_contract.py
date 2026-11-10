"""Observed original-resolution video subtitle, offline Chromium only."""

import subprocess

import pytest

from flow_provider.safe_ui import download_asset


@pytest.mark.asyncio
async def test_720p_original_subtitle_never_selects_enhanced(page, tmp_path):
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=32x32:d=0.3",
            "-an",
            "-c:v",
            "mpeg4",
            str(source),
        ],
        check=True,
    )
    await page.route(
        "https://download.test/exact-video",
        lambda route: route.fulfill(
            body=source.read_bytes(),
            content_type="video/mp4",
            headers={"Content-Disposition": 'attachment; filename="video.mp4"'},
        ),
    )
    await page.set_content("""<flow-tile-container><flow-video-tile>
      <video data-media-id="exact-video"></video>
      <button aria-label="Download" aria-haspopup="menu"
       onclick="document.querySelector('[role=menu]').hidden=false">Download</button>
    </flow-video-tile></flow-tile-container>
    <div role="menu" hidden>
     <a role="menuitem" href="https://download.test/exact-video">720p <span>Tamanho original</span></a>
     <button role="menuitem" onclick="window.enhanced=true">1080p <span>Aprimorada</span></button>
    </div>""")
    result = await download_asset(
        page,
        {
            "file": str(tmp_path / "downloaded.mp4"),
            "type": "video",
            "generation_timeout": 4,
        },
        "exact-video",
    )
    assert result["asset"] == "exact-video"
    assert result["type"] == "video"
    assert not await page.evaluate("Boolean(window.enhanced)")


@pytest.mark.asyncio
async def test_known_image_manifest_cannot_start_video_download(page, tmp_path):
    await page.set_content("""<flow-tile-container><flow-image-tile>
      <img data-media-id="uploaded-image"><button aria-label="Download"
      onclick="window.downloadClicked=true">Download</button>
    </flow-image-tile></flow-tile-container>""")
    with pytest.raises(ValueError, match="media kind mismatch"):
        await download_asset(
            page,
            {
                "file": str(tmp_path / "not-a-video.mp4"),
                "type": "video",
                "generation_timeout": 1,
            },
            "uploaded-image",
        )
    assert not await page.evaluate("Boolean(window.downloadClicked)")
