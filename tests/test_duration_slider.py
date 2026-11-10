"""Synthetic duration contracts; ephemeral offline Chromium only."""

from unittest.mock import AsyncMock

import pytest

from flow_provider import safe_ui as ui

pytestmark = pytest.mark.asyncio


async def mount(page, *, index=5, label=True, accessible=None, bounds=("0", "7"), broken=False):
    await page.set_content(f'''<flow-prompt-box>
    <button aria-label="Settings trigger">settings</button>
    <flow-prompt-box-settings><button aria-label="Select model family">Omni</button>
    <button role="radio" aria-checked="true">9:16</button>
    <button role="radio" aria-checked="true">x1</button>
    <div role="group" aria-label="Duration"><span id="value">{"8s" if label else ""}</span>
    <input id="duration" type="range" min="{bounds[0]}" max="{bounds[1]}" value="{index}"
      aria-label="Duration" aria-valuetext="{accessible or index}"
      onkeydown="window.keys=(window.keys||0)+1"
      oninput="{"return" if broken else "render()"}"></div>
    <div><flow-credit-cost-label class="settings-credit-cost">A geração vai usar 24 créditos</flow-credit-cost-label></div>
    </flow-prompt-box-settings><button data-testid="flow-submit" onclick="window.submits=(window.submits||0)+1">submit</button>
    </flow-prompt-box><script>
    function render() {{ let e=document.querySelector('#duration');
      let text=[3,4,5,6,7,8,10,12][Number(e.value)]+'s';
      document.querySelector('#value').textContent=text;
      e.setAttribute('aria-valuetext',e.value); }}
    </script>''')
    if index != 5 and label:
        await page.evaluate("render()")
    return page.locator("flow-prompt-box-settings")


@pytest.mark.parametrize(
    "attribute,value", [("aria-valuenow", "6"), ("aria-valuemin", "-1"), ("aria-valuemax", "8")]
)
async def test_native_aria_contradictions(page, attribute, value):
    panel = await mount(page)
    await page.locator("#duration").evaluate(
        "(e,args)=>e.setAttribute(...args)", [attribute, value]
    )
    with pytest.raises(ValueError):
        await ui.verify_duration(panel, "8s")


async def test_current_rendered_semantic_ignores_numeric_valuetext(page):
    panel = await mount(page)
    await ui.configure_duration(panel, "8s")
    await ui.verify_duration(panel, "8s")
    assert await page.evaluate("window.keys || 0") == 0
    assert await page.locator("#duration").input_value() == "5"


async def test_accessible_semantic_duration(page):
    panel = await mount(page, label=False, accessible="8 seconds")
    await ui.configure_duration(panel, "8s")
    assert await page.evaluate("window.keys || 0") == 0


async def test_keyboard_observes_nonidentity_mapping(page):
    panel = await mount(page, index=1)
    await ui.configure_duration(panel, "8s")
    assert await page.locator("#duration").input_value() == "5"
    assert 1 <= await page.evaluate("window.keys") <= 32
    await ui.verify_duration(panel, "8s")


@pytest.mark.parametrize("text", ["unknown", "8s 10s"])
async def test_unknown_conflicting_rendered_labels(page, text):
    panel = await mount(page)
    await page.locator("#value").evaluate("(e,t)=>e.textContent=t", text)
    with pytest.raises(ValueError):
        await ui.configure_duration(panel, "8s")
    assert await page.evaluate("window.keys || 0") == 0


async def test_conflicting_accessible_semantics(page):
    panel = await mount(page, accessible="10 seconds")
    with pytest.raises(ValueError):
        await ui.verify_duration(panel, "8s")


async def test_disabled_duplicate_slider_ignored(page):
    panel = await mount(page)
    await page.locator("#duration").evaluate(
        "(e)=>{let c=e.cloneNode(); c.disabled=true; e.parentElement.append(c)}"
    )
    await ui.verify_duration(panel, "8s")


@pytest.mark.parametrize("bounds", [("NaN", "7"), ("0", "Infinity"), ("9", "1"), ("0", "32")])
async def test_invalid_or_excessive_bounds(page, bounds):
    panel = await mount(page, bounds=bounds)
    with pytest.raises(ValueError):
        await ui.configure_duration(panel, "8s")
    assert await page.evaluate("window.keys || 0") == 0


async def test_readback_failure(page):
    panel = await mount(page, index=1, broken=True)
    with pytest.raises(ValueError):
        await ui.configure_duration(panel, "8s")
    assert await page.evaluate("window.keys || 0") <= 32


async def test_radio_fallback(page):
    await page.set_content(
        '<div><button role="radio" aria-checked="false" onclick="this.setAttribute(\'aria-checked\',\'true\')">8 s</button></div>'
    )
    panel = page.locator("div")
    await ui.configure_duration(panel, "8s")
    await ui.verify_duration(panel, "8s")


@pytest.mark.parametrize("drift", ["duration", "cost", "position_aria", "min_aria", "max_aria"])
async def test_pre_submit_drift_zero_clicks(page, tmp_path, monkeypatch, drift):
    await mount(page)
    adapter = ui.UIAdapter(tmp_path / "project.json", max_credits=24)
    adapter.page = page
    adapter.expected = {"model": "Omni", "ratio": "9:16", "count": 1, "duration": "8s"}
    adapter.refs = []
    adapter.cost = 24
    monkeypatch.setattr(ui, "require_auth", AsyncMock())
    monkeypatch.setattr("flow_provider.project.verify_account", lambda *args: None)
    monkeypatch.setattr(adapter, "verify_project_identity", AsyncMock())
    monkeypatch.setattr(adapter, "ensure_direct_mode", AsyncMock())
    await ui.verify_configuration(page, adapter.expected, [])
    assert await adapter.verify_cost() == 24
    if drift == "duration":
        await page.locator("#duration").evaluate("(e)=>{e.value=6;render()}")
    elif drift == "position_aria":
        await page.locator("#duration").evaluate(
            '(e)=>{e.value=6;e.setAttribute("aria-valuenow","5")}'
        )
    elif drift in ("min_aria", "max_aria"):
        attribute, value = (
            ("aria-valuemin", "-1") if drift == "min_aria" else ("aria-valuemax", "8")
        )
        await page.locator("#duration").evaluate(
            "(e,args)=>e.setAttribute(...args)", [attribute, value]
        )
    else:
        await page.locator("flow-credit-cost-label").evaluate(
            '(e)=>e.textContent="A geração vai usar 23 créditos"'
        )
    with pytest.raises(ValueError):
        await adapter.submit({})
    assert await page.evaluate("window.submits || 0") == 0


async def test_accessible_semantic_name(page):
    panel = await mount(page, label=False)
    await page.locator("#duration").evaluate('(e)=>e.setAttribute("aria-label", "Duration: 8s")')
    await ui.verify_duration(panel, "8s")


async def test_numeric_index_alone_is_not_duration(page):
    panel = await mount(page, label=False)
    with pytest.raises(ValueError):
        await ui.configure_duration(panel, "5s")
    assert await page.evaluate("window.keys || 0") == 0


async def test_enabled_duplicate_slider_is_ambiguous(page):
    panel = await mount(page)
    await page.locator("#duration").evaluate("(e)=>e.parentElement.append(e.cloneNode())")
    with pytest.raises(ValueError):
        await ui.configure_duration(panel, "8s")
    assert await page.evaluate("window.keys || 0") == 0


async def test_unavailable_duration_stops_at_last_observed_position(page):
    panel = await mount(page, index=1)
    with pytest.raises(ValueError, match="unavailable"):
        await ui.configure_duration(panel, "9s")
    assert await page.evaluate("window.keys") == 8
