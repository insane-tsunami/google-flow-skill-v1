"""Observed attached image-chip identity; synthetic offline DOM only."""

import pytest
from flow_provider.safe_ui import references


@pytest.mark.asyncio
async def test_observed_image_chip_service_identity(page):
    await page.set_content("""<flow-prompt-box><flow-image-ingredient-chip>
    <button class="chip-container" aria-label="Elemento" aria-busy="false"><div class="chip-image-wrapper">
    <img class="chip-image" alt="Imagem do elemento" src="https://flow-content.google/image/11111111-2222-4333-8444-555555555555?Expires=1&amp;Signature=fake"></div></button>
    </flow-image-ingredient-chip></flow-prompt-box>""")
    assert await references(page) == ["11111111-2222-4333-8444-555555555555"]
