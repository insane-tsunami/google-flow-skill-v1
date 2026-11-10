"""Observed Material duration component structure; no live service access."""

import pytest
from flow_provider.safe_ui import configure_duration, verify_duration


@pytest.mark.asyncio
async def test_observed_nested_header_numeric_index(page):
    await page.set_content("""<flow-prompt-box-settings>
      <div class="duration-slider-section">
        <div class="duration-slider-header"><span class="duration-slider-title">Duração</span>
          <span class="duration-slider-value">8s</span></div>
        <mat-slider class="duration-slider"><input type="range" aria-label="Duração"
          aria-valuetext="5" min="0" max="12" step="1" value="5"
          onkeydown="window.keys=(window.keys||0)+1"></mat-slider>
      </div></flow-prompt-box-settings>""")
    panel = page.locator("flow-prompt-box-settings")
    await configure_duration(panel, "8s")
    await verify_duration(panel, "8s")
    assert await page.locator("input").input_value() == "5"
    assert await page.evaluate("window.keys||0") == 0
