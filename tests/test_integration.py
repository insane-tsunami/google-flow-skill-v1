"""Real Chromium + intercepted synthetic Flow app. No Google traffic/credits."""

import asyncio
from io import BytesIO
import json
from pathlib import Path
import sys

from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import flow
from flow_provider import browser
from flow_provider.safe_ui import UIAdapter, download_asset

APP = r"""<!doctype html><meta charset="utf-8"><style>flow-prompt-box-settings,flow-tile-container{display:block} [hidden]{display:none!important}</style>
<button onclick="location.href='/project/project-1'">Novo projeto</button>
<button aria-label="Acionador de definições" onclick="settings.hidden=!settings.hidden">Ajustes</button>
<flow-prompt-box-settings id="settings" hidden>
<button role="radio" aria-checked="true">Imagem</button>
<button role="radio" aria-checked="true" onclick="this.setAttribute('aria-checked','true')">9:16</button>
<button role="radio" aria-checked="true" onclick="this.setAttribute('aria-checked','true')">x1</button>
<button data-testid="flow-model" onclick="models.hidden=false">Nano Banana 2.1</button>
</flow-prompt-box-settings>
<div role="menu" id="models" hidden><button role="menuitem" onclick="models.hidden=true">Nano Banana 2.1</button><button role="menuitem">Nano Banana 2</button></div>
<flow-rich-text-editor><div contenteditable="true" style="height:40px">prompt</div></flow-rich-text-editor>
<button class="add-menu-trigger" onclick="uploadPanel.hidden=false">+</button>
<div role="dialog" id="uploadPanel" hidden><div role="option" onclick="file.click()">Carregar multimédia</div><div role="tooltip">Carregar multimédia</div><input id="file" type="file" hidden onchange="attach()"><button id="confirm" onclick="finish()" hidden>Adicionar ao comando</button></div>
<div class="ingredient-bar-container" id="references"></div><div id="canvas"></div>
<flow-prompt-box style="display:block"><flow-generation-cost>Generation cost: 1 credits</flow-generation-cost></flow-prompt-box>
<button data-testid="flow-submit" onclick="generate(false)">Gerar</button>
<script>
window.submits=0;
function finish(){ references.innerHTML='<img data-media-id="reference-1" src="/reference.png">'; canvas.insertAdjacentHTML('beforeend','<flow-tile-container><flow-image-tile><img data-media-id="reference-1" src="/reference.png"></flow-image-tile></flow-tile-container>'); uploadPanel.hidden=true; }
function attach(){ if(window.requireConfirm) document.getElementById('confirm').hidden=false; else finish(); }
function generate(ready=true){
  window.submits++;
  // Download-only fixtures publish immediately; CLI clicks exercise progress.
  if(ready) canvas.innerHTML='';
  canvas.insertAdjacentHTML('beforeend','<flow-tile-container id="generated"><flow-image-tile><p></p><div role="progressbar">39%</div></flow-image-tile></flow-tile-container>');
  generated.querySelector('p').textContent=document.querySelector('[contenteditable]').innerText;
  const complete=()=>{
    generated.querySelector('[role=progressbar]').remove();
    generated.querySelector('flow-image-tile').insertAdjacentHTML('beforeend','<img data-media-id="asset-1" src="/reference.png"><button aria-label="Download" onclick="location.href=\'/download\'">Download</button>');
  };
  if(ready) complete(); else setTimeout(complete,1200);
}
</script>"""


async def app(page, payload=None):
    image = BytesIO()
    Image.new("RGB", (8, 8), "blue").save(image, "PNG")
    png = image.getvalue()

    async def route(request):
        url = request.request.url
        if url.endswith("/download"):
            await request.fulfill(
                body=payload if payload is not None else png,
                headers={
                    "Content-Type": "application/octet-stream",
                    "Content-Disposition": 'attachment; filename="same.png"',
                },
            )
        elif url.endswith("/reference.png"):
            await request.fulfill(body=png, content_type="image/png")
        else:
            await request.fulfill(body=APP, content_type="text/html")

    await page.route("**/*", route)
    await page.goto("https://labs.google/project/project-1")
    return png


@pytest.mark.asyncio
@pytest.mark.parametrize("confirmation", [False, True])
async def test_real_cli_reference_generate_download_resume(
    page, tmp_path, monkeypatch, confirmation
):
    png = await app(page)
    await page.evaluate("(v) => window.requireConfirm=v", confirmation)

    async def get_page():
        return page

    async def no_shutdown():
        pass

    monkeypatch.setattr(browser, "get_page", get_page)
    monkeypatch.setattr(browser, "shutdown", no_shutdown)
    # Existing synthetic project avoids a navigation resetting the test toggle.
    directory = tmp_path / "demo"
    directory.mkdir()
    (directory / "project.json").write_text('{"project":"project-1"}')

    async def navigate(_, *, expected):
        pass

    from flow_provider import project

    monkeypatch.setattr(project, "navigate_to_project", navigate)
    reference = tmp_path / "reference.png"
    reference.write_bytes(png)
    args = flow.build_parser().parse_args(
        [
            "image",
            "--max-credits",
            "1",
            "--prompt",
            "Offline synthetic test",
            "--model",
            "Nano Banana 2.1",
            "--name",
            "demo",
            "--image",
            str(reference),
            "--out",
            str(tmp_path),
        ]
    )
    assert await flow.execute(args) == 0
    assert await flow.execute(args) == 0
    assert await page.evaluate("window.submits") == 1
    report = json.loads((directory / "batch_report.json").read_text())["jobs"][0]
    assert report["state"] == "completed"
    assert report["result"]["asset"] == "asset-1"
    assert report["effective"]["reference_count"] == 1
    assert Path(report["result"]["file"]).read_bytes() == png


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["model", "ratio", "count", "reference", "login"])
async def test_presubmit_drift_never_clicks(page, tmp_path, mutation):
    await app(page)
    adapter = UIAdapter(tmp_path / "project.json", max_credits=1)
    adapter.page = page
    job = {
        "model": "Nano Banana 2.1",
        "ratio": "9:16",
        "count": 1,
        "type": "image",
        "prompt": "test",
    }
    await adapter.configure(job)
    if mutation == "model":
        await page.locator('[data-testid="flow-model"]').evaluate("e=>e.innerText='Nano Banana 2'")
    elif mutation in ("ratio", "count"):
        await page.get_by_role(
            "radio", name="9:16" if mutation == "ratio" else "x1", exact=True
        ).evaluate("e=>e.setAttribute('aria-checked','false')")
    elif mutation == "reference":
        adapter.refs = ["missing-reference"]
    else:
        await page.evaluate(
            "document.body.insertAdjacentHTML('beforeend','<button>Sign in</button>')"
        )
    with pytest.raises(ValueError):
        await adapter.submit(job)
    assert await page.evaluate("window.submits") == 0


@pytest.mark.asyncio
async def test_unavailable_model_never_clicks(page, tmp_path):
    await app(page)
    adapter = UIAdapter(tmp_path / "project.json", max_credits=1)
    adapter.page = page
    with pytest.raises(ValueError, match="discovered.*Nano Banana 2.1"):
        await adapter.configure({"type": "image", "model": "Nano Banana 9"})
    assert await page.evaluate("window.submits") == 0


@pytest.mark.asyncio
async def test_real_browser_download_wrong_asset_html_and_names(page, tmp_path):
    await app(page, b"<html>login</html>")
    await page.evaluate("generate()")
    job = {"file": str(tmp_path / "bad.png"), "type": "image"}
    with pytest.raises(TimeoutError):
        await download_asset(page, job | {"generation_timeout": 0.1}, "asset-2")
    with pytest.raises(ValueError):
        await download_asset(page, job, "asset-1")
    assert not Path(job["file"]).exists()
    await app(page)
    await page.evaluate("generate()")
    results = await asyncio.gather(
        download_asset(page, {"file": str(tmp_path / "a.png"), "type": "image"}, "asset-1"),
        download_asset(page, {"file": str(tmp_path / "b.png"), "type": "image"}, "asset-1"),
    )
    assert all(Path(r["file"]).is_file() for r in results)
