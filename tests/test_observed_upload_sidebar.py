"""Sanitized real Flow PT-BR picker DOM, observed 2026-11-12.

No live profile/network. Preserve the actual owner, button classes, icon/name.
"""

import pytest
from PIL import Image

from flow_provider.selectors import control
from flow_provider.safe_ui import upload_reference
from test_observed_image_attachment import chip, ID

# Angular generated attrs, describedby IDs and ripple-only spans omitted.
SIDEBAR = """<flow-add-menu-side-nav>
<button mat-button flow-button type="button"
 class="mdc-button mat-mdc-button-base mat-mdc-tooltip-trigger sidebar-upload-btn mat-mdc-button mat-unthemed flow-button-transparent flow-button-medium flow-button-no-touch-target"
 onclick="window.uploadClicks++;document.querySelector('input[type=file]').click()">
 <span class="mdc-button__label"><span class="upload-container">
 <mat-icon role="img" class="mat-icon notranslate upload-icon google-symbols mat-icon-no-color" aria-hidden="true" data-mat-icon-type="font">upload</mat-icon>
 <span class="upload-text">Fazer upload de mídia</span></span></span>
</button></flow-add-menu-side-nav>"""


async def observed_picker(page, extra=""):
    await page.set_content(
        """<style>flow-add-menu-side-nav{display:block;min-height:20px}[hidden]{display:none!important}</style>
        <flow-prompt-box><div class="ingredient-bar-container"></div>
        <button class="add-menu-trigger" onclick="document.querySelector('flow-add-menu-popover-content').hidden=false">Adicionar elementos à caixa de comando</button>
        <flow-add-menu-popover-content hidden><div class="add-menu-popover-container flow-menu-panel">"""
        + SIDEBAR
        + extra
        + """<flow-media-upload><input type="file" hidden onchange="window.chosen=this.files[0].name;document.querySelector('.ingredient-bar-container').innerHTML=window.attachment;document.querySelector('flow-add-menu-popover-content').hidden=true"></flow-media-upload>
        </div></flow-add-menu-popover-content></flow-prompt-box>
        <button onclick="window.submits++">Gerar</button>"""
    )
    await page.evaluate(
        "html=>{window.attachment=html;window.uploadClicks=0;window.wrong=0;window.submits=0}",
        chip(),
    )


@pytest.mark.parametrize("slot", [None, "initial", "final"])
async def test_observed_sidebar_upload_filechooser(page, tmp_path, slot):
    await observed_picker(
        page,
        '<button onclick="window.wrong++">Fazer upload de mídia</button><div role="tooltip">Fazer upload de mídia</div>',
    )
    if slot:
        await page.locator(".add-menu-trigger").evaluate(
            "(e,slot)=>e.setAttribute('data-testid','flow-'+slot)", slot
        )
    source = tmp_path / "reference.png"
    Image.new("RGB", (4, 4)).save(source)
    assert await upload_reference(page, source, slot) == ID
    assert await page.evaluate("[window.uploadClicks,window.wrong,window.submits]") == [1, 0, 0]
    assert await page.evaluate("window.chosen") == source.name


@pytest.mark.parametrize(
    "mutation", ["duplicate_button", "duplicate_owner", "missing", "unknown", "disabled"]
)
async def test_sidebar_ambiguity_fails_closed_without_wrong_click(page, mutation):
    await observed_picker(page, '<button onclick="window.wrong++">Enviar mídia</button>')
    await page.locator(".add-menu-trigger").click()
    button = page.locator("flow-add-menu-side-nav button")
    if mutation == "duplicate_button":
        await button.evaluate("e=>e.after(e.cloneNode(true))")
    elif mutation == "duplicate_owner":
        await button.evaluate("e=>e.parentElement.after(e.parentElement.cloneNode(true))")
    elif mutation == "missing":
        await button.evaluate("e=>e.remove()")
    elif mutation == "unknown":
        await button.locator(".upload-text").evaluate("e=>e.textContent='Unknown action'")
    else:
        await button.evaluate("e=>e.disabled=true")
    with pytest.raises(ValueError, match="unresolved or ambiguous"):
        await control(page.locator("flow-add-menu-popover-content"), "upload")
    assert await page.evaluate("[window.uploadClicks,window.wrong,window.submits]") == [0, 0, 0]
