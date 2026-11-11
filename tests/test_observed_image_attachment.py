"""Observed image attachment contract; intercepted, ephemeral offline Chromium only."""

from unittest.mock import AsyncMock

import pytest
from PIL import Image

from flow_provider import safe_ui, project
from flow_provider.safe_ui import references, upload_reference, UIAdapter

ID = "12345678-1234-4567-89ab-123456789abc"
OTHER = "87654321-1234-4567-89ab-123456789abc"
SRC = f"https://flow-content.google/image/{ID}?Expires=1&KeyName=test&Signature=synthetic"


def chip(src=SRC, attrs=""):
    return (
        f'<div class="ingredient-bar-container"><flow-image-ingredient-chip><button class="chip-container" aria-label="Elemento" '
        f'aria-busy="false"><div class="chip-image-wrapper"><img class="chip-image" '
        f'alt="Imagem do elemento" src="{src}" {attrs}></div></button></flow-image-ingredient-chip></div>'
    )


@pytest.mark.parametrize("busy", [False, True, "placeholder"])
async def test_observed_filechooser_ready_preserves_previous(page, tmp_path, busy):
    await page.route("**/*", lambda route: route.fulfill(body="", content_type="image/png"))
    await page.set_content("""<flow-prompt-box><div class="ingredient-bar-container">
      <img data-media-id="earlier" width="4" height="4"></div>
      <button onclick="document.querySelector('[role=dialog]').hidden=false">Adicionar elementos</button>
      <div role="dialog" hidden><div role="option" onclick="document.querySelector('input').click()">Enviar mídia</div>
      <input type="file" hidden onchange="window.chosen=this.files[0].name; document.querySelector('#ready').hidden=false">
      <button id="ready" hidden onclick="document.querySelector('.ingredient-bar-container').insertAdjacentHTML('beforeend',window.attachment);this.parentElement.hidden=true">Incluir no comando</button>
      </div></flow-prompt-box>""")
    await page.evaluate("(html)=>window.attachment=html", chip())
    if busy:
        await page.evaluate("(p)=>window.placeholder=p", busy == "placeholder")
        await page.locator("#ready").evaluate("""e=>e.onclick=()=>{
          document.querySelector('.ingredient-bar-container').insertAdjacentHTML('beforeend',window.attachment);
          let c=document.querySelector('flow-image-ingredient-chip');
          let b=c.querySelector('button'); let i=c.querySelector('img');
          b.setAttribute('aria-busy',window.placeholder?'false':'true');i.remove();
          if(window.placeholder)b.querySelector('div').innerHTML='<div class="chip-placeholder"><span>image</span></div>';
          setTimeout(()=>{b.querySelector('div').replaceChildren(i);b.setAttribute('aria-busy','false')},500);
          e.parentElement.hidden=true;
        }""")
    source = tmp_path / "reference.png"
    Image.new("RGB", (4, 4)).save(source)
    assert await upload_reference(page, source) == ID
    assert await page.evaluate("window.chosen") == source.name
    assert await references(page) == ["earlier", ID]


@pytest.mark.parametrize(
    "src",
    [
        SRC.replace("https:", "http:"),
        SRC.replace("flow-content.google", "evil.test"),
        SRC.replace("flow-content.google", "flow-content.google.evil.test"),
        SRC.replace("/image/", "/video/"),
        SRC.replace(ID, "filename.png"),
        SRC.replace(ID, ID + "/extra"),
        SRC.replace("https://", "//"),
        SRC.replace("flow-content.google", "user@flow-content.google"),
        SRC.replace("flow-content.google", "flow-content.google:443"),
        "https://[invalid/image/" + ID,
    ],
)
async def test_invalid_url_rejected_without_signed_diagnostics(page, src):
    await page.set_content(chip(src))
    with pytest.raises(ValueError) as error:
        await references(page)
    assert "Signature" not in str(error.value)
    assert src not in str(error.value)


@pytest.mark.parametrize(
    "mutation", ["busy", "duplicate_image", "duplicate_chip", "media", "mention", "scope", "alt"]
)
async def test_ambiguous_or_unready_chip_rejected(page, mutation):
    html = chip()
    if mutation == "busy":
        html = html.replace('aria-busy="false"', 'aria-busy="true"')
    elif mutation == "duplicate_image":
        html = html.replace("</div>", f'<img src="{SRC}"></div>')
    elif mutation == "duplicate_chip":
        html += chip()
    elif mutation in ("media", "mention"):
        html = chip(attrs=f'data-{mutation}-id="wrong"')
    elif mutation == "scope":
        html = html.replace("chip-image-wrapper", "unknown-wrapper")
    else:
        html = html.replace("Imagem do elemento", "unknown")
    await page.set_content(html)
    with pytest.raises(ValueError):
        await references(page)


async def test_legacy_ids_and_generic_images(page):
    await page.set_content(
        f'<img src="{SRC}"><flow-tile-container><img src="{SRC}"></flow-tile-container>'
    )
    assert await references(page) == []
    await page.set_content(
        '<div class="ingredient-bar-container"><img data-media-id="legacy" src="/legacy.png" width="4" height="4"><span class="mention-chip" data-mention-id="mention"></span></div>'
    )
    assert await references(page) == ["legacy"]
    await page.set_content(chip(attrs=f'data-media-id="{ID}" data-mention-id="{ID}"'))
    assert await references(page) == [ID]


@pytest.mark.parametrize("state", ["identity", "placeholder"])
async def test_presubmit_identity_drift_zero_clicks(page, tmp_path, monkeypatch, state):
    await page.set_content(
        "<flow-prompt-box>"
        + chip()
        + '</flow-prompt-box><button data-testid="flow-submit" onclick="window.clicks++">Gerar</button>'
    )
    await page.evaluate("window.clicks=0")
    adapter = UIAdapter(tmp_path / "project.json", max_credits=1)
    adapter.page = page
    adapter.refs = await references(page)
    adapter.expected = {}
    adapter.cost = 1
    monkeypatch.setattr(safe_ui, "require_auth", AsyncMock())
    monkeypatch.setattr(project, "verify_account", lambda *args: None)
    monkeypatch.setattr(adapter, "verify_project_identity", AsyncMock())
    monkeypatch.setattr(adapter, "ensure_direct_mode", AsyncMock())
    monkeypatch.setattr(safe_ui, "verify_configuration", AsyncMock())

    async def drift():
        if state == "placeholder":
            await page.locator(".chip-image-wrapper").evaluate(
                "e=>e.innerHTML='<div class=\"chip-placeholder\">image</div>'"
            )
        else:
            await page.locator("img").evaluate("(e, src)=>e.src=src", SRC.replace(ID, OTHER))
        return 1

    monkeypatch.setattr(adapter, "verify_cost", drift)
    await page.locator("body").evaluate(
        "e=>e.insertAdjacentHTML('beforeend','<button aria-label=\"Acionador de definições\">Ajustes</button>')"
    )
    expected_error = "placeholder not ready" if state == "placeholder" else "reference_mismatch"
    with pytest.raises(ValueError, match=expected_error):
        await adapter.submit({})
    assert await page.evaluate("window.clicks") == 0


async def test_configuration_reference_mismatch(page):
    from test_integration import app

    await app(page)
    await page.locator(".ingredient-bar-container").evaluate("(e, html)=>e.innerHTML=html", chip())
    request = dict(model="Nano Banana 2.1", ratio="9:16", count=1)
    await safe_ui.verify_configuration(page, request, [ID])
    with pytest.raises(ValueError, match="reference_mismatch"):
        await safe_ui.verify_configuration(page, request, [OTHER])
