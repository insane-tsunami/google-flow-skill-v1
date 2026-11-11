import asyncio

import pytest

from flow_provider.safe_ui import new_asset, stable_asset_baseline


@pytest.mark.asyncio
async def test_preexisting_no_id_card_is_not_new_when_it_gets_media(page):
    await page.set_content("""<flow-tile-container><flow-video-tile>
      <p>authorized prompt</p><div class="unidentified-placeholder">pending</div>
    </flow-video-tile></flow-tile-container>""")
    before = await stable_asset_baseline(page, [], timeout=1, quiet=0.05)
    await page.evaluate("""() => {
      const tile=document.querySelector('flow-video-tile');
      tile.querySelector('.unidentified-placeholder').remove();
      tile.insertAdjacentHTML('beforeend','<video data-media-id="old-generation"></video>');
    }""")
    with pytest.raises(TimeoutError):
        await new_asset(page, before, timeout=0.1, kind="video", prompt="authorized prompt")


@pytest.mark.asyncio
async def test_image_id_inside_generated_video_card_is_not_video_identity(page):
    await page.set_content('<div id="gallery"></div>')
    before = await stable_asset_baseline(page, [], timeout=1, quiet=0.05)
    await page.evaluate(
        """() => gallery.innerHTML='<flow-tile-container><flow-video-tile><p>authorized prompt</p><div role="progressbar">39%</div><img data-media-id="reference-not-video"></flow-video-tile></flow-tile-container>' """
    )

    async def finish():
        await asyncio.sleep(0.8)
        await page.locator("[role=progressbar]").evaluate("(e)=>e.remove()")

    task = asyncio.create_task(finish())
    try:
        with pytest.raises(TimeoutError):
            await new_asset(
                page, before, timeout=1.3, kind="video", prompt="authorized prompt", quiet=0.05
            )
    finally:
        await task


@pytest.mark.asyncio
async def test_prior_progress_blocks_baseline_before_payment(page):
    await page.set_content(
        '<flow-tile-container><div role="progressbar">39%</div></flow-tile-container>'
    )
    with pytest.raises(TimeoutError):
        await stable_asset_baseline(page, [], timeout=0.1, quiet=0.05)
