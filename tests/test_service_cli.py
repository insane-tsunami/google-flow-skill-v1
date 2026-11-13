"""Public CLI + offline Chromium; no real account/profile or service requests.

Run outside the restricted worker sandbox. Image tests cover automatic submit
attribution; video tests cover known-asset original download through public CLI.
"""

import hashlib
import json
from pathlib import Path
import subprocess
import time

import pytest

import flow
from flow_provider import browser
from flow_provider.batch import Runner
from flow_provider.service_records import digest
from test_integration import APP
from test_service_records import record

ENDPOINT = "/u/1/_/AiSandboxAngularFrontend/data/batchexecute"
ORIGIN = "https://flow.google.com"


@pytest.mark.asyncio
@pytest.mark.parametrize("grouped", [False, True])
@pytest.mark.parametrize("kind", ["image", "video"])
@pytest.mark.parametrize("interrupted", [False, True])
async def test_public_automatic_original_download(
    page, tmp_path, monkeypatch, grouped, kind, interrupted
):
    from io import BytesIO
    from PIL import Image

    image = BytesIO()
    Image.new("RGB", (16, 24), "green").save(image, "PNG")
    thumbnail = image.getvalue()
    payload = thumbnail
    if kind == "video":
        clip = tmp_path / "synthetic-source.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=32x32:d=0.2",
                "-an",
                "-c:v",
                "mpeg4",
                str(clip),
            ],
            check=True,
        )
        payload = clip.read_bytes()
    model = "Nano Banana 2.1" if kind == "image" else "Omni 1.2 Flash"
    suffix = ".png" if kind == "image" else ".mp4"
    state = {"submitted": 0, "original": 0}
    prompt = "independent exact full synthetic prompt"
    old = record(asset="old-record")
    old[5][5] = "https://lh3.googleusercontent.com/opaque/old"
    new = record(kind=kind, prompt=prompt, asset="new-record")
    new[2] = "history-group"
    new[5][5] = "https://lh3.googleusercontent.com/opaque/new"
    cover = record(kind=kind, prompt="different cover", asset="cover-record")
    cover[2] = "history-group"
    cover[5][5] = "https://lh3.googleusercontent.com/opaque/cover"
    script = r"""
<script>
const endpoint=ENDPOINT;
fetch(endpoint, {method:'POST',body:new URLSearchParams({'f.req':JSON.stringify([[['listProject','[]',null,'generic']]])})});
function openEditor(){
 editorView.hidden=false;
 canvas.hidden=true;
}
function generate(){
 window.submits++;
 document.querySelector('[data-testid="flow-model"]').textContent="Unrelated composer model";
 // Rematerialize an old physical card, defeating DOM node baselines.
 canvas.innerHTML='<flow-tile-container><flow-image-tile><img class="image" src="https://lh3.googleusercontent.com/opaque/old=s512-rw"></flow-image-tile></flow-tile-container>';
 const prompt=document.querySelector('[contenteditable]').innerText;
 fetch(endpoint,{method:'POST',body:new URLSearchParams({'f.req':JSON.stringify([[['generate',JSON.stringify([prompt,{model:WIRE_MODEL,type:WIRE_KIND,ratio:'9:16',count:1,duration:null,reference_ids:[...document.querySelectorAll('#references img')].map(e=>e.getAttribute('data-media-id')),character:null,voice:null}]),null,'generic']]])})}).then(()=>{
 canvas.insertAdjacentHTML('beforeend','<flow-tile-container onclick="openEditor()"><flow-image-tile><img class="image" src="https://lh3.googleusercontent.com/opaque/TARGET=s512-rw"></flow-image-tile></flow-tile-container>');
 });
}
</script>
<div id="editorView" hidden>
<flow-image-editor><img class="image" src="https://lh3.googleusercontent.com/opaque/new=s1600-rw"><flow-image-ingredient-chip><img class="image" src="https://lh3.googleusercontent.com/opaque/new=s1600-rw"></flow-image-ingredient-chip></flow-image-editor>
<flow-editor-header>
<button aria-label="Mostrar informações do recurso" onclick="info.hidden=false">Info</button>
<button aria-label="Baixar mídia" aria-haspopup="menu" onclick="menu.hidden=false">Baixar</button>
</flow-editor-header>
HISTORY
<aside id="info" class="info-panel-overlay" hidden><flow-info-panel><div class="container">
<div class="metadata"><div class="metadata-row">🍌 Nano Banana 2.1</div></div>
<flow-expandable-prompt><div class="prompt-text"><span class="text-part">PROMPT</span></div></flow-expandable-prompt>
</div></flow-info-panel></aside>
</div>
<div id="menu" role="menu" hidden><a role="menuitem" href="/original">1K <span>Tamanho original</span></a>
<button role="menuitem" onclick="window.upscales=1">2K Aprimorada</button></div>
"""
    history = """<flow-editor-history-step-image><div class="history-step">
<flow-image-ingredient-chip><img class="image" src="https://lh3.googleusercontent.com/opaque/new=s1600-rw"></flow-image-ingredient-chip>
<flow-tile-container onclick="window.historySelected=true"><flow-image-tile><img class="image" src="https://lh3.googleusercontent.com/opaque/new=s1600-rw"></flow-image-tile></flow-tile-container>
<flow-expandable-prompt><div class="prompt-text"><span class="text-part">PROMPT</span></div></flow-expandable-prompt>
</div></flow-editor-history-step-image>"""
    if kind == "video":
        history = history.replace(
            "</flow-image-tile>",
            '<button aria-label="Fazer o download" aria-haspopup="menu" onclick="event.stopPropagation();menu.hidden=false">Clip download</button></flow-image-tile>',
        )
    script = script.replace("ENDPOINT", json.dumps(ENDPOINT)).replace("HISTORY", history)
    script = script.replace("WIRE_MODEL", json.dumps(model)).replace("WIRE_KIND", json.dumps(kind))
    script = script.replace("PROMPT", prompt).replace("TARGET", "cover" if grouped else "new")
    if kind == "video":
        script = script.replace("flow-image-tile", "flow-video-tile").replace(
            "flow-editor-history-step-image", "flow-editor-history-step-video"
        )
        script = script.replace(
            '<div id="editorView" hidden>',
            '<flow-scene-builder id="editorView" hidden style="display:block">',
        )
        script = script.replace('</div>\n<div id="menu"', '</flow-scene-builder>\n<div id="menu"')
        script = script.replace(
            'onclick="menu.hidden=false">Baixar',
            'onclick="window.sceneDownloads=1;menu.hidden=false">Baixar',
        )
        script = script.replace(">1K <span>", ">720p <span>")
    base = (
        APP if kind == "image" else APP.replace("Imagem", "Vídeo").replace("Nano Banana 2.1", model)
    )
    html = (
        base
        + script
        + """<script>canvas.innerHTML='<flow-tile-container><flow-image-tile><img class="image" src="https://lh3.googleusercontent.com/opaque/old=s512-rw"></flow-image-tile></flow-tile-container>';</script>"""
    )
    if kind == "video":
        html = html.replace("<flow-image-tile>", "<flow-video-tile>").replace(
            "</flow-image-tile>", "</flow-video-tile>"
        )

    from test_service_framing_observed import framed

    async def route(route):
        request = route.request
        if ENDPOINT in request.url:
            from urllib.parse import parse_qs

            body = parse_qs(request.post_data)["f.req"][0]
            generating = '"generate"' in body
            if generating:
                state["submitted"] += 1
                now = time.time_ns()
                new[5][0] = [now // 10**9, now % 10**9]
            rows = [old] + ([new, cover] if state["submitted"] else [])
            rpc = "generate" if generating else "listProject"
            await route.fulfill(
                body=")]}'" + "\n\n" + framed([["wrb.fr", rpc, json.dumps(rows)]]),
                content_type="application/json",
            )
        elif request.url.endswith("/original"):
            state["original"] += 1
            await route.fulfill(
                body=payload,
                headers={
                    "Content-Type": "image/png",
                    "Content-Disposition": 'attachment; filename="original.png"',
                },
            )
        elif "googleusercontent.com" in request.url:
            await route.fulfill(body=thumbnail, content_type="image/png")
        else:
            # Reload materializes the same records, with a reordered old card.
            current = html
            if state["submitted"]:
                # Stable record ownership survives a freshly signed location.
                new[5][5] = "https://lh3.googleusercontent.com/opaque/rotated"
                current = current.replace("/opaque/new", "/opaque/rotated")
                target = "cover" if grouped else "rotated"
                tile_kind = kind
                current += f'<script>canvas.innerHTML=\'<flow-tile-container onclick="openEditor()"><flow-{tile_kind}-tile><img class="image" src="https://lh3.googleusercontent.com/opaque/{target}=s512-rw"></flow-{tile_kind}-tile></flow-tile-container>\';</script>'
            await route.fulfill(body=current, content_type="text/html")

    await page.route("**/*", route)
    monkeypatch.setenv("FLOW_ACCOUNT_INDEX", "1")

    async def get_page():
        return page

    async def shutdown():
        pass

    from flow_provider import project

    monkeypatch.setattr(project, "get_page", get_page)
    monkeypatch.setattr(browser, "get_page", get_page)
    monkeypatch.setattr(browser, "shutdown", shutdown)
    directory = tmp_path / "automatic"
    directory.mkdir()
    (directory / "project.json").write_text(
        json.dumps({"project": "project-1", "account_index": "1"})
    )
    from flow_provider import safe_ui
    from flow_provider.service_records import GenerationInvocationContract

    # Explicit test-only wire contract; no live RPC is inferred from its name.
    monkeypatch.setattr(
        safe_ui, "GENERATION_CONTRACT", GenerationInvocationContract("generate", (0,), (1,))
    )
    args = flow.build_parser().parse_args(
        [
            kind,
            "--name",
            "automatic",
            "--prompt",
            prompt,
            "--model",
            model,
            "--max-credits",
            "1",
            "--max-attempts",
            "1",
            "--out",
            str(tmp_path),
        ]
    )
    if interrupted:
        from flow_provider import safe_ui

        class PublicationCrash(BaseException):
            pass

        real_publish = safe_ui.publish

        def crash_after_publication(*args):
            real_publish(*args)
            raise PublicationCrash()

        with monkeypatch.context() as patch:
            patch.setattr(safe_ui, "publish", crash_after_publication)
            with pytest.raises(PublicationCrash):
                await flow.execute(args)
        interrupted_row = json.loads((directory / "batch_report.json").read_text())["jobs"][0]
        assert interrupted_row["state"] == "downloading"
        assert interrupted_row["attempts"]["download"] == 1
    assert await flow.execute(args) == 0
    receipt = json.loads((directory / ("automatic" + suffix + ".receipt.json")).read_text())
    assert receipt["asset"] == "service-" + digest("new-record")
    assert receipt["sha256"] == hashlib.sha256(payload).hexdigest()
    report_path = directory / "batch_report.json"
    row = json.loads(report_path.read_text())["jobs"][0]
    assert row["state"] == "completed"
    assert row["asset"] == "service-" + digest("new-record")
    assert row["service_intent"]["proof"]["record"]["group_hash"] == digest("history-group")
    assert Path(row["result"]["file"]).read_bytes() == payload
    assert row["result"]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert await flow.execute(args) == 0
    assert state == {"submitted": 1, "original": 1}
    assert "opaque/new" not in report_path.read_text()
    assert prompt not in report_path.read_text()
    assert not await page.evaluate("window.upscales || 0")
    if kind == "video":
        assert not await page.evaluate("window.sceneDownloads || 0")


@pytest.mark.asyncio
async def test_public_video_known_asset_original_download(page, tmp_path, monkeypatch):
    """No fabricated video detail schema: resume known legacy asset via CLI."""
    clip = tmp_path / "fixture.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=32x32:d=0.2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(clip),
        ],
        check=True,
    )
    payload = clip.read_bytes()
    calls = []
    html = """<button>Novo projeto</button><button aria-label="Acionador de definições">Settings</button><flow-project-shell><flow-tile-container><flow-video-tile>
<video data-media-id="known-video"></video><button aria-label="Download" aria-haspopup="menu" onclick="menu.hidden=false">Download</button>
</flow-video-tile></flow-tile-container></flow-project-shell>
<div id="menu" role="menu" hidden><a role="menuitem" href="/original">720p <span>Tamanho original</span></a>
<button role="menuitem" onclick="window.upscales=1">1080p</button></div>"""

    async def route(route):
        if route.request.url.endswith("/original"):
            calls.append("720p")
            await route.fulfill(
                body=payload,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Disposition": 'attachment; filename="original.mp4"',
                },
            )
        else:
            await route.fulfill(body=html, content_type="text/html")

    await page.route("**/*", route)
    monkeypatch.setenv("FLOW_ACCOUNT_INDEX", "1")

    async def get_page():
        return page

    async def shutdown():
        pass

    from flow_provider import project

    monkeypatch.setattr(project, "get_page", get_page)
    monkeypatch.setattr(browser, "get_page", get_page)
    monkeypatch.setattr(browser, "shutdown", shutdown)
    args = flow.build_parser().parse_args(
        [
            "video",
            "--name",
            "known",
            "--prompt",
            "synthetic video",
            "--model",
            "Observed video label",
            "--max-attempts",
            "1",
            "--out",
            str(tmp_path),
        ]
    )
    directory, jobs = flow.prepare_jobs(
        {
            "project": "known",
            "jobs": [
                {
                    "type": "video",
                    "name": "known",
                    "prompt": "synthetic video",
                    "model": "Observed video label",
                    "ratio": "9:16",
                    "count": 1,
                }
            ],
        },
        tmp_path,
    )
    runner = Runner(directory / "batch_report.json", jobs, object(), max_attempts=1)
    row = runner.data["jobs"][0]
    row.update(state="submitted", asset="known-video", attempts={"submit": 1})
    runner.checkpoint(row, "submitted")
    (directory / "project.json").write_text(
        json.dumps({"project": "project-1", "account_index": "1"})
    )
    assert await flow.execute(args) == 0
    assert await flow.execute(args) == 0
    receipt = json.loads((directory / "known.mp4.receipt.json").read_text())
    assert receipt["asset"] == "known-video"
    assert receipt["sha256"] == hashlib.sha256(payload).hexdigest()
    assert calls == ["720p"]
    assert (directory / "known.mp4").read_bytes() == payload
    assert not await page.evaluate("window.upscales || 0")
