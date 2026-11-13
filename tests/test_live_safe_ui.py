"""Sanitized live DOM contracts, exercised only in offline ephemeral Chromium."""

from unittest.mock import AsyncMock

import pytest

from flow_provider import safe_ui as ui


COST = '<flow-credit-cost-label class="settings-credit-cost"><span class="credit-cost-label">A geração vai usar <a class="credit-cost-link">24 créditos</a></span></flow-credit-cost-label>'


async def mount(page, tmp_path, *, sidebar=False, pressed="true", cost=COST, optin=True):
    await page.set_content(f'''
    <button aria-label="Fechar" onclick="window.wrongClose=true">Other close</button>
    <flow-agent-panel {"hidden" if not sidebar else ""}><button aria-label="Fechar"
      onclick="this.parentElement.hidden=true; document.querySelector('main').hidden=false">close</button></flow-agent-panel>
    <main {"hidden" if sidebar else ""}><flow-prompt-box>
      <button class="agent-mode-chip agent-mode-chip-checked" aria-pressed="{pressed}"
        onclick="window.toggles=(window.toggles||0)+1; this.setAttribute('aria-pressed',this.getAttribute('aria-pressed')==='true'?'false':'true'); document.querySelector('#settings').hidden=this.getAttribute('aria-pressed')==='true'">
        <span class="agent-mode-chip-label">Agente</span></button>
      <button id="settings" {"hidden" if pressed == "true" else ""} aria-label="Gatilho de configurações"
        onclick="let p=document.querySelector('flow-prompt-box-settings'); p.hidden=!p.hidden">settings</button>
      <flow-prompt-box-settings hidden><div><button aria-label="Select model family">Model</button>{cost}</div></flow-prompt-box-settings>
      <button data-testid="flow-submit" onclick="window.submits=(window.submits||0)+1">submit</button>
    </flow-prompt-box></main>''')
    adapter = ui.UIAdapter(tmp_path / "p.json", direct_mode=optin, max_credits=24)
    adapter.page = page
    return adapter


@pytest.mark.asyncio
@pytest.mark.parametrize("sidebar", [False, True])
async def test_persistent_agent_toggle_is_idempotent(page, tmp_path, sidebar):
    adapter = await mount(page, tmp_path, sidebar=sidebar)
    await adapter.ensure_direct_mode()
    await adapter.ensure_direct_mode()
    assert (
        await page.get_by_role("button", name="Agente", exact=True).get_attribute("aria-pressed")
        == "false"
    )
    assert await page.evaluate("window.toggles") == 1
    assert await page.evaluate("window.wrongClose || false") is False
    assert await adapter.verify_cost() == 24


@pytest.mark.asyncio
async def test_sidebar_requires_optin(page, tmp_path):
    adapter = await mount(page, tmp_path, sidebar=True, optin=False)
    with pytest.raises(ValueError, match="opt_in"):
        await adapter.ensure_direct_mode()
    assert await page.locator("flow-agent-panel").is_visible()


@pytest.mark.asyncio
async def test_existing_direct_proof_does_not_toggle(page, tmp_path):
    adapter = await mount(page, tmp_path, pressed="false", optin=False)
    await adapter.ensure_direct_mode()
    await adapter.ensure_direct_mode()
    assert await page.evaluate("window.toggles || 0") == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cost",
    [
        "",
        COST.replace("24 créditos", "unknown créditos"),
        COST * 2,
        f'<div contenteditable="true">{COST}</div>',
        "<flow-credit-banner>24 créditos</flow-credit-banner>",
    ],
)
async def test_actual_cost_rejects_unknown_ambiguous_spoof(page, tmp_path, cost):
    adapter = await mount(page, tmp_path, pressed="false", cost=cost)
    await adapter.ensure_direct_mode()
    with pytest.raises(ValueError, match="cost_unknown"):
        await adapter.verify_cost()
    assert await page.evaluate("window.submits || 0") == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("gap", ["", " ", "\n      "])
async def test_service_cost_whitespace_boundary(page, tmp_path, gap):
    adapter = await mount(page, tmp_path, pressed="false", cost=COST.replace("usar ", "usar" + gap))
    await adapter.ensure_direct_mode()
    assert await adapter.verify_cost() == 24


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", [False, True])
async def test_submit_reads_visible_cost_before_closing(page, tmp_path, monkeypatch, drift):
    adapter = await mount(page, tmp_path, pressed="false")
    await adapter.ensure_direct_mode()
    adapter.cost = 23 if drift else 24
    adapter.expected, adapter.refs = {}, []
    monkeypatch.setattr(ui, "require_auth", AsyncMock())
    monkeypatch.setattr("flow_provider.project.verify_account", lambda *args: None)
    monkeypatch.setattr(ui, "verify_configuration", AsyncMock())
    monkeypatch.setattr(ui, "new_asset", AsyncMock(return_value="offline-asset"))
    if drift:
        with pytest.raises(ValueError, match="cost_changed"):
            await adapter.submit({})
    else:
        with pytest.raises(ValueError, match="generation invocation contract unavailable"):
            await adapter.submit({})
    assert await page.evaluate("window.submits || 0") == 0
