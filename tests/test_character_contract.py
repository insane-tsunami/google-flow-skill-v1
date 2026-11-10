"""Observed character picker/chip contract, exercised in a real offline browser."""

import pytest
from flow_provider.elements import attach_character, verify_character


async def character_dom(page):
    await page.route("https://**/*", lambda route: route.abort())
    await page.set_content("""<flow-prompt-box><button aria-label="Adicionar elementos à caixa de comando" onclick="document.querySelector('flow-add-menu-popover-content').hidden=false">add</button><flow-character-ingredient-chip hidden><button aria-label="Elemento" onclick="this.parentElement.hidden=true"><img src="https://flow.google.com/asb/example"></button></flow-character-ingredient-chip></flow-prompt-box>
    <flow-add-menu-popover-content hidden><button role="option" class="asset-item-active"><span class="asset-title">Unique</span><span class="type-subtitle">Personagem</span><img src="https://flow.google.com/asb/example"></button><flow-character-preview-pane><img class="character-thumbnail-image" src="https://flow-content.google/image/example"><div class="character-voice-card"><span class="character-voice-name">Full voice</span><span class="character-voice-description">Full description</span></div><audio src="https://www.gstatic.com/aitestkitchen/voices/samples/example.wav"></audio></flow-character-preview-pane><button onclick="document.querySelector('flow-character-ingredient-chip').hidden=false;this.parentElement.hidden=true">Incluir no comando</button></flow-add-menu-popover-content>""")


async def test_character_roundtrip(page):
    await character_dom(page)
    proof = await attach_character(page, dict(character="Unique", type="video", voice="Full voice"))
    await verify_character(page, proof)
    await page.locator("flow-character-ingredient-chip img").evaluate(
        "e=>e.src='https://flow.google.com/asb/changed'"
    )
    with pytest.raises(ValueError):
        await verify_character(page, proof)


async def test_character_picker_opens_asynchronously(page):
    await character_dom(page)
    await page.get_by_role("button", name="Adicionar elementos à caixa de comando").evaluate(
        "e=>e.setAttribute('onclick', \"setTimeout(()=>document.querySelector('flow-add-menu-popover-content').hidden=false, 250)\")"
    )
    proof = await attach_character(page, dict(character="Unique", type="video", voice="Full voice"))
    await verify_character(page, proof)


async def test_character_id_is_not_preview_id(page):
    with pytest.raises(ValueError, match="not exposed"):
        await attach_character(page, dict(character_id="preview-image-id"))


async def test_no_unproved_character(page):
    await page.set_content(
        '<flow-character-ingredient-chip><button aria-label="Elemento"></button></flow-character-ingredient-chip>'
    )
    with pytest.raises(ValueError):
        await verify_character(page, None)


@pytest.mark.parametrize(
    "mutation", ["duplicate", "voice", "truncated", "placeholder", "missing_voice"]
)
async def test_invalid_saved_association_never_attaches(page, mutation):
    await character_dom(page)
    await page.evaluate(
        "window.attaches=0; document.querySelector('flow-add-menu-popover-content > button:last-child').addEventListener('click',()=>window.attaches++)"
    )
    if mutation == "duplicate":
        await page.locator("[role=option]").evaluate("e=>e.after(e.cloneNode(true))")
    elif mutation == "voice":
        await page.locator(".character-voice-name").evaluate("e=>e.textContent='Different'")
    elif mutation == "truncated":
        await page.locator(".character-voice-description").evaluate("e=>e.textContent='Truncated…'")
    elif mutation == "placeholder":
        await page.locator(".character-thumbnail-image").evaluate(
            "e=>e.src='https://flow.google.com/placeholder.svg'"
        )
    else:
        await page.locator(".character-voice-card").evaluate("e=>e.remove()")
    with pytest.raises(ValueError):
        await attach_character(page, dict(character="Unique", type="video", voice="Full voice"))
    assert await page.evaluate("window.attaches") == 0


async def test_image_ignores_voice_and_does_not_claim_body(page):
    await character_dom(page)
    await page.locator(".character-voice-card").evaluate("e=>e.remove()")
    proof = await attach_character(page, dict(character="Unique", type="image"))
    assert "voice" not in proof and "body" not in proof
    from flow_provider.safe_ui import references

    assert await references(page, proof) == []
    with pytest.raises(ValueError):
        await references(page)


@pytest.mark.parametrize("mutation", [None, "voice", "variant"])
async def test_presubmit_saved_revalidation(page, mutation):
    await character_dom(page)
    proof = await attach_character(page, dict(character="Unique", type="video"))
    if mutation == "voice":
        await page.locator(".character-voice-description").evaluate(
            "e=>e.textContent='Changed description'"
        )
    if mutation == "variant":
        await page.locator(".character-thumbnail-image").evaluate(
            "e=>e.src='https://flow-content.google/image/other'"
        )
    if mutation:
        with pytest.raises(ValueError):
            await verify_character(page, proof, saved=True)
    else:
        await verify_character(page, proof, saved=True)


async def test_presubmit_voice_drift_zero_generation(page, tmp_path, monkeypatch):
    from unittest.mock import AsyncMock
    from flow_provider.safe_ui import UIAdapter
    from flow_provider import safe_ui

    await character_dom(page)
    adapter = UIAdapter(tmp_path / "project.json", max_credits=1)
    adapter.page = page
    adapter.character = await attach_character(page, dict(character="Unique", type="video"))
    await page.locator(".character-voice-description").evaluate("e=>e.textContent='Changed'")
    monkeypatch.setattr(safe_ui, "require_auth", AsyncMock())
    monkeypatch.setattr(safe_ui, "verify_account", lambda *a: None, raising=False)
    from flow_provider import project

    monkeypatch.setattr(project, "verify_account", lambda *a: None)
    monkeypatch.setattr(adapter, "verify_project_identity", AsyncMock())
    monkeypatch.setattr(adapter, "ensure_direct_mode", AsyncMock())
    cost = AsyncMock(side_effect=AssertionError("Must stop before cost/submit"))
    monkeypatch.setattr(adapter, "verify_cost", cost)
    with pytest.raises(ValueError, match="changed"):
        await adapter.submit({})
    cost.assert_not_called()


@pytest.mark.parametrize("owned", [True, False])
async def test_configure_retained_owned_chip_not_human_chip(page, tmp_path, monkeypatch, owned):
    from unittest.mock import AsyncMock
    from flow_provider import safe_ui, project

    await character_dom(page)
    adapter = safe_ui.UIAdapter(tmp_path / "project.json", max_credits=1)
    adapter.page = page
    proof = await attach_character(page, dict(character="Unique", type="image"))
    if owned:
        adapter.character = proof
    monkeypatch.setattr(safe_ui, "require_auth", AsyncMock())
    monkeypatch.setattr(project, "verify_account", lambda *a: None)
    monkeypatch.setattr(adapter, "verify_project_identity", AsyncMock())
    monkeypatch.setattr(adapter, "ensure_project", AsyncMock())
    # Deliberately stop after the ownership boundary, before settings/prompt.
    reached = AsyncMock(side_effect=RuntimeError("ownership accepted"))
    monkeypatch.setattr(adapter, "ensure_direct_mode", reached)
    if owned:
        for _ in range(2):
            with pytest.raises(RuntimeError, match="ownership accepted"):
                await adapter.configure(dict(type="image", model="Exact"))
        assert reached.await_count == 2
        assert await page.locator("flow-character-ingredient-chip:visible").count() == 0
    else:
        with pytest.raises(ValueError):
            await adapter.configure(dict(type="image", model="Exact"))
        reached.assert_not_called()
        assert await page.locator("flow-character-ingredient-chip:visible").count() == 1
