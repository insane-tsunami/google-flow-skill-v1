"""Real native range input with asynchronous semantic rendering, offline only."""

import asyncio
from types import SimpleNamespace

import pytest

from flow_provider import safe_ui as ui

pytestmark = pytest.mark.asyncio


async def mount(page, *, index=5, delay=100, frozen=False):
    await page.set_content(f"""<flow-prompt-box-settings>
      <div class="duration-slider-section">
        <div class="duration-slider-header"><span class="duration-slider-title">Duração</span>
          <span class="duration-slider-value">{index + 3}s</span></div>
        <mat-slider><input type="range" aria-label="Duração" aria-valuetext="{index}"
          min="0" max="12" step="1" value="{index}"
          onkeydown="window.keys=(window.keys||0)+1"
          oninput="observe(this)"></mat-slider>
      </div></flow-prompt-box-settings><script>
      window.events=[];
      function observe(e) {{
        const value=e.value;
        e.setAttribute('aria-valuetext',value);
        events.push([value,document.querySelector('.duration-slider-value').textContent]);
        if ({str(not frozen).lower()}) setTimeout(()=>{{
          document.querySelector('.duration-slider-value').textContent=(Number(value)+3)+'s';
        }}, {delay});
      }}
      </script>""")
    return page.locator("flow-prompt-box-settings")


async def test_delayed_native_render_reaches_10s(page):
    panel = await mount(page)
    await ui.configure_duration(panel, "10s")
    await ui.verify_duration(panel, "10s")
    assert await page.locator("input").input_value() == "7"
    events = await page.evaluate("events")
    # Native keyboard mutates the position before the semantic label renders.
    assert events[0] == ["0", "8s"]
    assert ["1", "3s"] in events
    assert await page.evaluate("window.keys") == 8


async def test_already_10s_does_not_press_keys(page):
    panel = await mount(page, index=7)
    await ui.configure_duration(panel, "10s")
    await ui.verify_duration(panel, "10s")
    assert await page.evaluate("window.keys||0") == 0


async def test_frozen_render_fails_bounded_without_more_keys(page):
    panel = await mount(page, frozen=True)
    with pytest.raises(ValueError, match="Duration keyboard readback failed"):
        await ui.configure_duration(panel, "10s")
    assert await page.evaluate("window.keys") == 1


async def test_successful_read_after_total_deadline_is_rejected(page, monkeypatch):
    panel = await mount(page, delay=0)
    clock = SimpleNamespace(now=0)
    real_read = ui.read_duration_slider
    reads = 0

    async def late_success(state):
        nonlocal reads
        reads += 1
        observed = await real_read(state)
        if reads == 2:
            # Simulate a read that completed successfully after the total budget.
            clock.now = 11
            return 0, 3
        return observed

    monkeypatch.setattr(ui, "read_duration_slider", late_success)
    monkeypatch.setattr(
        ui,
        "asyncio",
        SimpleNamespace(
            get_running_loop=lambda: SimpleNamespace(time=lambda: clock.now),
            wait_for=asyncio.wait_for,
            sleep=asyncio.sleep,
            TimeoutError=asyncio.TimeoutError,
        ),
    )
    with pytest.raises(ValueError, match="Duration keyboard readback failed"):
        await ui.configure_duration(panel, "10s")
    assert await page.evaluate("window.keys") == 1


async def test_delayed_render_does_not_mask_aria_conflict(page):
    panel = await mount(page)
    await page.locator("input").evaluate('(e)=>e.setAttribute("aria-valuenow","5")')
    with pytest.raises(ValueError, match="conflicting"):
        await ui.configure_duration(panel, "10s")
    assert await page.evaluate("window.keys") == 1
