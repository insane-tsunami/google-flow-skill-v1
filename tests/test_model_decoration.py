import pytest
from flow_provider.safe_ui import choose_model


@pytest.mark.asyncio
async def test_exact_public_model_label_with_banana(page):
    await page.set_content(
        """<div role="menu"><button role="menuitem" onclick="window.chosen='pro'">🍌 Nano Banana Pro</button><button role="menuitem" onclick="window.chosen='requested'">🍌 Nano Banana 2.1</button></div>"""
    )
    await choose_model(page.get_by_role("menu"), "Nano Banana 2.1")
    assert await page.evaluate("window.chosen") == "requested"


@pytest.mark.asyncio
async def test_normalized_model_label_ambiguity_blocks(page):
    await page.set_content(
        """<div role="menu"><button role="menuitem" onclick="window.submits=1">🍌 Nano Banana 2.1</button><button role="option" onclick="window.submits=1">Nano Banana 2.1</button></div>"""
    )
    with pytest.raises(ValueError, match="ambiguous"):
        await choose_model(page.get_by_role("menu"), "Nano Banana 2.1")
    assert await page.evaluate("window.submits || 0") == 0
