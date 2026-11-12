"""Observed variant-slot DOM: a declared slot can hold a placeholder for longer
than the quiet window before its image renders (live: ~0.7 s after the row click; fixtures time from the add click)."""

import pytest
from flow_provider.elements import attach_character, verify_character

SLOT = (
    '<button class="character-thumbnail-button" '
    'aria-label="Miniatura da variante do personagem {n}">{body}</button>'
)
IMG = '<img class="character-thumbnail-image" src="https://flow-content.google/image/v{n}">'
PLACEHOLDER = '<div class="character-thumbnail-placeholder"></div>'


async def observed_dom(page):
    await page.route("https://**/*", lambda route: route.abort())
    row = SLOT.format(n=1, body=IMG.format(n=1)) + SLOT.format(n=2, body=PLACEHOLDER)
    await page.set_content(
        """<flow-prompt-box><button aria-label="Adicionar elementos à caixa de comando" onclick="document.querySelector('flow-add-menu-popover-content').hidden=false">add</button><flow-character-ingredient-chip hidden><button aria-label="Elemento" onclick="this.parentElement.hidden=true"><img src="https://flow.google.com/asb/example"></button></flow-character-ingredient-chip></flow-prompt-box>
    <flow-add-menu-popover-content hidden><button role="option" class="asset-item-active"><span class="asset-title">Unique</span><span class="type-subtitle">Personagem</span><img src="https://flow.google.com/asb/example"></button><flow-character-preview-pane><div class="character-preview-container"><div class="character-hero-area"><img class="character-hero-image" src="https://flow-content.google/image/v1"></div><div class="character-thumbnail-row" role="group" aria-label="Variantes de imagem do personagem">"""
        + row
        + """</div></div></flow-character-preview-pane><button onclick="document.querySelector('flow-character-ingredient-chip').hidden=false;this.parentElement.hidden=true">Incluir no comando</button></flow-add-menu-popover-content>"""
    )


def resolve_slot_after(ms):
    return (
        "()=>{const add=document.querySelector('flow-prompt-box > button');"
        "add.addEventListener('click',()=>setTimeout(()=>{"
        "const p=document.querySelector('.character-thumbnail-placeholder');"
        "if(p)p.outerHTML='" + IMG.format(n=2) + "'}," + str(ms) + "))}"
    )


async def test_placeholder_slot_longer_than_quiet_window_is_awaited(page):
    await observed_dom(page)
    await page.evaluate(resolve_slot_after(1500))
    proof = await attach_character(page, dict(character="Unique", type="image"))
    assert proof["variants"] == ["/image/v1", "/image/v2"]


async def test_saved_roundtrip_with_late_slot_has_no_spurious_drift(page):
    await observed_dom(page)
    await page.evaluate(resolve_slot_after(1500))
    proof = await attach_character(page, dict(character="Unique", type="image"))
    # Flow re-renders the pane on reopen: placeholder again, image later.
    await (
        page.locator(".character-thumbnail-image")
        .nth(1)
        .evaluate("e=>e.outerHTML='" + PLACEHOLDER + "'")
    )
    await verify_character(page, proof, saved=True)
    assert await page.locator("flow-character-ingredient-chip:visible").count() == 1


async def test_unresolved_placeholder_slot_blocks_attachment(page):
    await observed_dom(page)
    with pytest.raises(ValueError, match="did not stabilize"):
        await attach_character(page, dict(character="Unique", type="image"))
    assert await page.locator("flow-character-ingredient-chip:visible").count() == 0


async def test_real_slot_drift_still_fails_closed(page):
    await observed_dom(page)
    await page.evaluate(resolve_slot_after(100))
    proof = await attach_character(page, dict(character="Unique", type="image"))
    await (
        page.locator(".character-thumbnail-image")
        .nth(1)
        .evaluate("e=>e.src='https://flow-content.google/image/other'")
    )
    with pytest.raises(ValueError) as error:
        await verify_character(page, proof, saved=True)
    assert "fields: variants" in str(error.value) and "https://" not in str(error.value)


async def test_wrong_character_still_rejected(page):
    await observed_dom(page)
    await page.evaluate(resolve_slot_after(100))
    with pytest.raises(ValueError):
        await attach_character(page, dict(character="Other", type="image"))
    assert await page.locator("flow-character-ingredient-chip:visible").count() == 0
