import pytest
from flow_provider.safe_ui import asset_map


@pytest.mark.asyncio
async def test_nested_tile_wrappers_are_one_physical_asset(page):
    await page.set_content(
        """<flow-grid-tile-container><flow-tile-container id="physical-card"><img data-media-id="same-asset"><button>Download</button></flow-tile-container></flow-grid-tile-container>"""
    )
    cards = await asset_map(page)
    assert set(cards) == {"same-asset"}
    assert await cards["same-asset"].get_attribute("id") == "physical-card"
    assert await cards["same-asset"].get_by_role("button", name="Download").count() == 1


@pytest.mark.asyncio
async def test_duplicate_asset_in_distinct_cards_still_blocks(page):
    await page.set_content(
        """<flow-grid-tile-container><flow-tile-container><img data-media-id="same-asset"></flow-tile-container></flow-grid-tile-container><flow-grid-tile-container><flow-tile-container><img data-media-id="same-asset"></flow-tile-container></flow-grid-tile-container>"""
    )
    with pytest.raises(ValueError, match="Duplicate asset"):
        await asset_map(page)
