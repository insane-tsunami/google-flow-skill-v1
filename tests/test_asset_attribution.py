"""Offline regression: delayed reference gallery publication is not generation."""

import pytest

from flow_provider.safe_ui import asset_ids, new_asset, stable_asset_baseline


@pytest.mark.asyncio
async def test_delayed_upload_is_not_video_submission(page):
    await page.set_content('<div id="gallery"></div>')
    before = await stable_asset_baseline(page, [], timeout=1, quiet=0.05)
    await page.evaluate("""() => {
      gallery.innerHTML = '<flow-tile-container><flow-image-tile><img data-media-id="late-upload"></flow-image-tile></flow-tile-container>';
      setTimeout(() => gallery.insertAdjacentHTML('beforeend', '<flow-tile-container><flow-video-tile><p>authorized prompt</p><div role="progressbar">39%</div></flow-video-tile></flow-tile-container>'), 40);
      setTimeout(() => {const t=document.querySelector('flow-video-tile'); t.querySelector('[role=progressbar]').remove(); t.insertAdjacentHTML('beforeend','<video data-media-id="submitted-video"></video>')}, 1200);
    }""")
    assert (
        await new_asset(
            page, before, timeout=4, kind="video", prompt="authorized prompt", quiet=0.05
        )
        == "submitted-video"
    )


@pytest.mark.asyncio
async def test_same_kind_ambiguity_fails_closed(page):
    await page.set_content('<div id="gallery"></div>')
    before = await stable_asset_baseline(page, [], timeout=1, quiet=0.05)
    await page.evaluate("""() => {
      for (let i=0;i<2;i++) gallery.insertAdjacentHTML('beforeend','<flow-tile-container><flow-video-tile><p>authorized prompt</p><div role="progressbar">39%</div></flow-video-tile></flow-tile-container>');
    }""")
    with pytest.raises(ValueError, match="attribution uncertain"):
        await new_asset(page, before, timeout=0.2, kind="video", prompt="authorized prompt")


@pytest.mark.asyncio
async def test_same_kind_ready_card_without_submission_lifecycle_rejected(page):
    await page.set_content('<div id="gallery"></div>')
    before = await stable_asset_baseline(page, [], timeout=1, quiet=0.05)
    await page.evaluate(
        """() => gallery.innerHTML='<flow-tile-container><flow-video-tile><p>authorized prompt</p><video data-media-id="unbound"></video></flow-video-tile></flow-tile-container>'"""
    )
    with pytest.raises(TimeoutError):
        await new_asset(page, before, timeout=0.1, kind="video", prompt="authorized prompt")


@pytest.mark.asyncio
async def test_baseline_waits_for_uploaded_gallery_reference(page):
    await page.set_content('<div id="gallery"></div>')
    await page.evaluate(
        """() => setTimeout(() => gallery.innerHTML='<flow-tile-container><flow-image-tile><img data-media-id="reference"></flow-image-tile></flow-tile-container>', 100)"""
    )
    baseline = await stable_asset_baseline(page, ["reference"], timeout=1, quiet=0.05)
    assert baseline["ids"] == await asset_ids(page) == {"reference"}


@pytest.mark.asyncio
async def test_baseline_missing_reference_blocks_before_submit(page):
    await page.set_content("<div></div>")
    with pytest.raises(TimeoutError):
        await stable_asset_baseline(page, ["missing"], timeout=0.1, quiet=0.05)
