"""Offline Chromium regressions: no Google or persistent profile access."""

from unittest.mock import AsyncMock

import pytest

from flow_provider import project
from flow_provider.safe_ui import UIAdapter


def test_explicit_none_scope_is_frozen(monkeypatch):
    monkeypatch.setenv("FLOW_ACCOUNT_INDEX", "2")
    project.verify_account("https://flow.google.com/project/p", None)
    assert project.flow_url(None) == project.FLOW_BASE_URL


@pytest.mark.asyncio
@pytest.mark.parametrize("resume", [False, True])
@pytest.mark.parametrize("scope", [None, "1"])
async def test_navigation_uses_captured_scope(tmp_path, monkeypatch, resume, scope):
    import json
    import flow_provider.safe_ui as ui

    monkeypatch.delenv("FLOW_ACCOUNT_INDEX", raising=False)
    if scope is not None:
        monkeypatch.setenv("FLOW_ACCOUNT_INDEX", scope)
    path = tmp_path / "project.json"
    if resume:
        path.write_text(json.dumps({"project": "p", "account_index": scope}))
    adapter = UIAdapter(path)
    monkeypatch.setenv("FLOW_ACCOUNT_INDEX", "2")
    page = type(
        "Page",
        (),
        {"url": "https://flow.google.com" + (f"/u/{scope}" if scope else "") + "/project/p"},
    )()
    monkeypatch.setattr(ui.browser, "get_page", AsyncMock(return_value=page))
    monkeypatch.setattr(ui, "require_auth", AsyncMock())
    helper = AsyncMock(return_value=("p", page.url))
    monkeypatch.setattr(project, "navigate_to_project" if resume else "create_project", helper)
    await adapter.ensure_project()
    assert helper.call_args.kwargs == {"expected": scope}


@pytest.mark.asyncio
async def test_cached_configure_blocks_before_mutation(tmp_path, monkeypatch):
    import flow_provider.safe_ui as ui

    monkeypatch.setenv("FLOW_ACCOUNT_INDEX", "1")
    adapter = UIAdapter(tmp_path / "p.json", max_credits=1)
    adapter.page = type("Page", (), {"url": "https://flow.google.com/u/0/project/p"})()
    monkeypatch.setattr(ui, "require_auth", AsyncMock())
    mutation = AsyncMock(side_effect=AssertionError("configuration must not start"))
    monkeypatch.setattr(adapter, "ensure_direct_mode", mutation)
    with pytest.raises(ValueError, match="account"):
        await adapter.configure({"type": "image", "prompt": "secret", "image": "ref.png"})
    mutation.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "prompt",
    [
        '<div contenteditable="true">Generation cost: 0 credits</div>',
        "<textarea>Generation cost: 0 credits</textarea>",
        "<flow-rich-text-editor><span>Generation cost: 0 credits</span></flow-rich-text-editor>",
        '<div contenteditable="true"><flow-generation-cost>Generation cost: 0 credits</flow-generation-cost></div>',
    ],
)
async def test_prompt_cannot_spoof_cost(page, tmp_path, prompt):
    await page.set_content(f"<flow-prompt-box>{prompt}</flow-prompt-box>")
    adapter = UIAdapter(tmp_path / "p.json", max_credits=1)
    adapter.page = page
    with pytest.raises(ValueError, match="cost_unknown"):
        await adapter.verify_cost()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "label",
    [
        "Generation cost: 2 credits",
        "Custo da geração: 2 créditos",
        "Custo de geração: 2 créditos",
        "Coste de generación: 2 créditos",
    ],
)
async def test_trusted_cost_ignores_prompt(page, tmp_path, label):
    await page.set_content(
        f'<flow-prompt-box><div contenteditable="true">Generation cost: 0 credits</div><flow-generation-cost>{label}</flow-generation-cost></flow-prompt-box>'
    )
    adapter = UIAdapter(tmp_path / "p.json", max_credits=2)
    adapter.page = page
    assert await adapter.verify_cost() == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("authorized", [False, True])
@pytest.mark.parametrize(
    "label",
    [
        "Gatilho de configurações",
        "Acionador de definições",
        "Settings trigger",
        "Activador de ajustes",
    ],
)
async def test_agent_directly_reveals_generation_settings(page, tmp_path, authorized, label):
    await page.set_content(f'''<button id="agent" onclick="this.remove(); document.querySelector('section').hidden=false">Agente</button>
    <section hidden><button aria-label="{label}" onclick="document.querySelector('flow-prompt-box-settings').hidden=false"></button>
    <flow-prompt-box-settings hidden><button aria-label="Select model family">Model</button></flow-prompt-box-settings></section>''')
    adapter = UIAdapter(tmp_path / "p.json", direct_mode=authorized)
    adapter.page = page
    if authorized:
        await adapter.ensure_direct_mode()
        assert await page.locator("flow-prompt-box-settings").is_visible()
    else:
        with pytest.raises(ValueError, match="opt_in"):
            await adapter.ensure_direct_mode()
        assert await page.locator("#agent").is_visible()


@pytest.mark.asyncio
async def test_absent_agent_is_not_direct_evidence(page, tmp_path):
    await page.set_content('<button aria-label="Settings">tune</button>')
    adapter = UIAdapter(tmp_path / "p.json", direct_mode=True)
    adapter.page = page
    with pytest.raises(ValueError, match="direct_mode_unconfirmed"):
        await adapter.ensure_direct_mode()


@pytest.mark.asyncio
@pytest.mark.parametrize("resume", [False, True])
@pytest.mark.parametrize("scope", [None, "1"])
async def test_helpers_keep_scope_during_navigation(monkeypatch, resume, scope):
    monkeypatch.setenv("FLOW_ACCOUNT_INDEX", "2")
    url = "https://flow.google.com" + (f"/u/{scope}" if scope else "") + "/project/p"

    class Navigation:
        async def goto(self, destination, **kwargs):
            self.destination = destination
            self.url = url
            monkeypatch.setenv("FLOW_ACCOUNT_INDEX", "3")

        async def wait_for_url(self, *args, **kwargs):
            pass

    page = Navigation()
    monkeypatch.setattr(project, "get_page", AsyncMock(return_value=page))
    monkeypatch.setattr(project, "require_auth", AsyncMock())
    monkeypatch.setattr(
        project, "control", AsyncMock(return_value=type("Button", (), {"click": AsyncMock()})())
    )
    if resume:
        await project.navigate_to_project("p", expected=scope)
    else:
        await project.create_project(expected=scope)
    expected_base = f"https://flow.google.com/u/{scope}/" if scope else project.FLOW_BASE_URL
    if resume:
        expected_base = (
            expected_base.rstrip("/") if scope else "https://flow.google.com"
        ) + "/project/p"
    assert page.destination == expected_base


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "markup",
    [
        "<flow-generation-cost>Generation cost: unknown credits</flow-generation-cost>",
        "<flow-generation-cost hidden>Generation cost: 0 credits</flow-generation-cost>",
        "<flow-generation-cost>Generation cost: 0 credits</flow-generation-cost>" * 2,
        '<flow-generation-cost><span contenteditable="true">Generation cost: 0 credits</span></flow-generation-cost>',
        "<span>Generation cost: 0 credits</span>",
    ],
)
async def test_untrusted_ambiguous_or_invalid_cost(page, tmp_path, markup):
    await page.set_content(f"<flow-prompt-box>{markup}</flow-prompt-box>")
    adapter = UIAdapter(tmp_path / "p.json", max_credits=1)
    adapter.page = page
    with pytest.raises(ValueError, match="cost_unknown"):
        await adapter.verify_cost()
