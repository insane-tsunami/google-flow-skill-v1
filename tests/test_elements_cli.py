"""Offline issue #7 contracts; synthetic DOM is not live acceptance evidence."""

import pytest
from PIL import Image
import flow
from flow_provider import project
from flow_provider.batch import Runner


def data(**kw):
    return {
        "project": "offline",
        "jobs": [dict(type="image", name="one", model="Exact", prompt="x", **kw)],
    }


def test_explicit_project_parser(monkeypatch):
    monkeypatch.setenv("FLOW_ACCOUNT_INDEX", "2")
    assert (
        project.explicit_project("https://flow.google.com/u/2/project/example-id", "2")
        == "example-id"
    )
    for value in [
        "https://flow.google.com/u/1/project/example-id",
        "https://evil.test/u/2/project/example-id",
        "example-id?x=1",
    ]:
        with pytest.raises(ValueError):
            project.explicit_project(value, "2")
    with pytest.raises(ValueError):
        project.explicit_project("example-id", None)


def test_multiple_reference_content_fingerprint(tmp_path):
    ref = tmp_path / "ref.png"
    Image.new("RGB", (4, 4), "red").save(ref)
    _, jobs = flow.prepare_jobs(data(images=[str(ref)]), tmp_path)
    first = Runner(tmp_path / "report.json", jobs, None).fingerprint
    Image.new("RGB", (4, 4), "blue").save(ref)
    _, jobs = flow.prepare_jobs(data(images=[str(ref)]), tmp_path)
    assert Runner(tmp_path / "report.json", jobs, None).fingerprint != first


@pytest.mark.parametrize(
    "kw",
    [
        dict(voice="Exact voice"),
        dict(character="Saved", start="missing.png"),
        dict(mode="frames", images=["missing.png"]),
    ],
)
def test_incompatibility_before_browser(tmp_path, kw):
    with pytest.raises(ValueError):
        flow.prepare_jobs(data(**kw), tmp_path)


def test_cli_elements_options():
    args = flow.build_parser().parse_args(
        [
            "video",
            "--model",
            "Exact",
            "--name",
            "x",
            "--prompt",
            "x",
            "--project-id",
            "example-id",
            "--project-title",
            "Exact title",
            "--image",
            "a.png",
            "--image",
            "b.png",
            "--mode",
            "elements",
            "--character-id",
            "saved-id",
            "--voice",
            "Full voice",
        ]
    )
    assert args.images == ["a.png", "b.png"]


@pytest.mark.parametrize("label", ["Voice…", "Voice...", "", " Voice", "Voice\nOther"])
def test_truncated_voice_rejected(tmp_path, label):
    from flow_provider.elements import validate_inputs

    with pytest.raises(ValueError):
        validate_inputs(dict(type="video", mode="elements", character_id="saved", voice=label))


@pytest.mark.parametrize("kind", ["image", "video"])
async def test_saved_character_stops_before_browser(tmp_path, monkeypatch, kind):
    from unittest.mock import AsyncMock
    from flow_provider import safe_ui

    launch = AsyncMock(side_effect=AssertionError("Must not open a browser"))
    monkeypatch.setattr(safe_ui.browser, "get_page", launch)
    adapter = safe_ui.UIAdapter(tmp_path / "project.json", max_credits=1)
    job = dict(type=kind, character_id="saved")
    if kind == "video":
        job["mode"] = "elements"
    with pytest.raises(
        safe_ui.ConfigurationError, match="saved_character_id_not_exposed_use_exact_name"
    ):
        await adapter.configure(job)
    launch.assert_not_called()
    assert not (tmp_path / "project.json").exists()


@pytest.mark.parametrize("kind", ["image", "video"])
def test_project_scope_changes_fingerprint(tmp_path, monkeypatch, kind):
    monkeypatch.setenv("FLOW_ACCOUNT_INDEX", "2")
    source = data()
    source["jobs"][0]["type"] = kind
    source["project_id"] = "example-one"
    _, first = flow.prepare_jobs(source, tmp_path)
    source["project_id"] = "example-two"
    _, second = flow.prepare_jobs(source, tmp_path)
    assert (
        Runner(tmp_path / "r.json", first, None).fingerprint
        != Runner(tmp_path / "r.json", second, None).fingerprint
    )
    source["project_title"] = "Exact title"
    _, third = flow.prepare_jobs(source, tmp_path)
    assert (
        Runner(tmp_path / "r.json", third, None).fingerprint
        != Runner(tmp_path / "r.json", second, None).fingerprint
    )


def test_replaced_local_reference_blocks_resume(tmp_path):
    from flow_provider.elements import verify_reference_bytes

    ref = tmp_path / "ref.png"
    Image.new("RGB", (4, 4), "red").save(ref)
    _, jobs = flow.prepare_jobs(data(images=[str(ref)]), tmp_path)
    runner = Runner(tmp_path / "r.json", jobs, None)
    runner.checkpoint(runner.data["jobs"][0], "uncertain")
    assert Runner(tmp_path / "r.json", jobs, None).data["jobs"][0]["state"] == "uncertain"
    Image.new("RGB", (4, 4), "blue").save(ref)
    with pytest.raises(ValueError, match="content changed"):
        verify_reference_bytes(jobs[0])
    _, changed = flow.prepare_jobs(data(images=[str(ref)]), tmp_path)
    with pytest.raises(ValueError, match="Manifest does not match"):
        Runner(tmp_path / "r.json", changed, None)


@pytest.mark.parametrize(
    "url",
    [
        "https://flow.google.com/u/2/project/other",
        "https://flow.google.com/u/1/project/example",
        "https://evil.test/u/2/project/example",
    ],
)
def test_project_redirect_mismatch(url):
    with pytest.raises(ValueError):
        project.verify_project(url, "example", "2")


@pytest.mark.parametrize(
    "labels",
    [
        ("Adicionar elementos", "Enviar mídia", "Incluir no comando"),
        ("Adicionar elementos", "Carregar multimédia", "Adicionar ao comando"),
        ("Añadir elementos", "Cargar medios", "Agregar a la instrucción"),
        ("Add elements", "Upload media", "Include in prompt"),
    ],
)
async def test_multiple_filechooser_uploads_offline(page, tmp_path, labels):
    from flow_provider.safe_ui import upload_reference, references

    add, upload, confirm = labels
    await page.set_content(f"""<flow-prompt-box>
      <button onclick="document.querySelector('[role=dialog]').hidden=false">{add}</button>
      <div class="ingredient-bar-container"></div>
      <div role="dialog" hidden><div role="option" onclick="document.querySelector('input').click()">{upload}</div>
      <input hidden type="file" onchange="window.chosen=this.files[0].name; document.querySelector('#confirm').hidden=false">
      <button id="confirm" hidden onclick="let img=document.createElement('img'); img.dataset.mediaId='ref-'+(++window.serial); img.src=window.pic; document.querySelector('.ingredient-bar-container').append(img); this.hidden=true; this.parentElement.hidden=true">{confirm}</button></div>
      </flow-prompt-box>""")
    await page.evaluate(
        "window.serial=0; window.pic='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='"
    )
    for i in range(2):
        ref = tmp_path / f"ref-{i}.png"
        Image.new("RGB", (4, 4), "red").save(ref)
        assert await upload_reference(page, ref) == f"ref-{i + 1}"
        assert await page.evaluate("window.chosen") == ref.name
    assert await references(page) == ["ref-1", "ref-2"]


async def test_exact_project_title_missing_or_ambiguous(page, tmp_path, monkeypatch):
    from flow_provider.safe_ui import UIAdapter

    monkeypatch.setenv("FLOW_ACCOUNT_INDEX", "2")
    adapter = UIAdapter(
        tmp_path / "p.json",
        project_scope=dict(project="example", account_index="2", title="Full title"),
    )
    adapter.page = page
    # No URL identity bypass in production; this test isolates the heading proof.
    adapter.project_id = None
    for html in ["", "<h1>Full title…</h1>", "<h1>Full title</h1><h2>Full title</h2>"]:
        await page.set_content(html)
        with pytest.raises(ValueError):
            await adapter.verify_project_identity()
    await page.set_content("<h1>Full title</h1>")
    await adapter.verify_project_identity()


@pytest.mark.parametrize("redirect", [False, True])
async def test_explicit_project_never_creates(tmp_path, monkeypatch, redirect):
    from unittest.mock import AsyncMock
    from flow_provider import safe_ui

    monkeypatch.setenv("FLOW_ACCOUNT_INDEX", "2")
    page = type(
        "Page",
        (),
        {
            "url": "https://flow.google.com/u/2/project/" + ("other" if redirect else "example"),
            "on": lambda *args: None,
        },
    )()
    monkeypatch.setattr(safe_ui.browser, "get_page", AsyncMock(return_value=page))
    monkeypatch.setattr(safe_ui, "require_auth", AsyncMock())
    navigate = AsyncMock()
    create = AsyncMock(side_effect=AssertionError("Must never create"))
    monkeypatch.setattr(project, "navigate_to_project", navigate)
    monkeypatch.setattr(project, "create_project", create)
    adapter = safe_ui.UIAdapter(
        tmp_path / "p.json", project_scope=dict(project="example", account_index="2", title=None)
    )
    if redirect:
        with pytest.raises(ValueError, match="Project identity changed"):
            await adapter.ensure_project()
        assert not (tmp_path / "p.json").exists()
    else:
        await adapter.ensure_project()
        await adapter.ensure_project()
        assert adapter.project_id == "example"
    navigate.assert_awaited_once_with("example", expected="2")
    create.assert_not_called()


async def test_persisted_project_conflict_before_browser(tmp_path, monkeypatch):
    import json
    from unittest.mock import AsyncMock
    from flow_provider import safe_ui

    monkeypatch.setenv("FLOW_ACCOUNT_INDEX", "2")
    target = tmp_path / "p.json"
    target.write_text(json.dumps(dict(project="other", account_index="2")))
    open_page = AsyncMock(side_effect=AssertionError("Must not open"))
    monkeypatch.setattr(safe_ui.browser, "get_page", open_page)
    adapter = safe_ui.UIAdapter(
        target, project_scope=dict(project="example", account_index="2", title=None)
    )
    with pytest.raises(ValueError, match="target mismatch"):
        await adapter.ensure_project()
    open_page.assert_not_called()


@pytest.mark.parametrize(
    "html",
    [
        '<div class="ingredient-bar-container"><img src="data:image/png;base64,eA=="></div>',
        '<flow-rich-text-editor><span class="mention-chip">Unverified</span></flow-rich-text-editor>',
        '<div class="ingredient-bar-container"><img data-media-id="same" src="data:image/png;base64,eA=="><img data-media-id="same" src="data:image/png;base64,eA=="></div>',
    ],
)
async def test_unverified_or_ambiguous_attachment_blocks(page, html):
    from flow_provider.safe_ui import references

    await page.set_content(html)
    with pytest.raises(ValueError):
        await references(page)


@pytest.mark.parametrize("target", ["", None, False])
def test_empty_explicit_project_never_falls_back_to_create(tmp_path, monkeypatch, target):
    monkeypatch.setenv("FLOW_ACCOUNT_INDEX", "2")
    source = data()
    source["project_id"] = target
    with pytest.raises(ValueError):
        flow.prepare_jobs(source, tmp_path)


def test_job_project_cannot_silently_override_scope(tmp_path):
    with pytest.raises(ValueError, match="top level"):
        flow.prepare_jobs(data(project_id="example"), tmp_path)


@pytest.mark.parametrize("mutation", ["account", "project", "reference"])
async def test_presubmit_identity_drift_zero_submits(tmp_path, monkeypatch, mutation):
    from unittest.mock import AsyncMock
    from flow_provider import safe_ui
    from flow_provider.elements import seal_references

    monkeypatch.setenv("FLOW_ACCOUNT_INDEX", "2")
    adapter = safe_ui.UIAdapter(tmp_path / "p.json", max_credits=1)
    adapter.project_id = "example"
    url = "https://flow.google.com/u/2/project/example"
    if mutation == "account":
        url = url.replace("/u/2/", "/u/1/")
    if mutation == "project":
        url = url.replace("/example", "/other")
    adapter.page = type("Page", (), {"url": url})()
    monkeypatch.setattr(safe_ui, "require_auth", AsyncMock())
    touch = AsyncMock(side_effect=AssertionError("No UI mutation or submit allowed"))
    monkeypatch.setattr(adapter, "ensure_direct_mode", touch)
    ref = tmp_path / "ref.png"
    Image.new("RGB", (4, 4), "red").save(ref)
    adapter.reference_job = {"images": [str(ref)]}
    seal_references(adapter.reference_job)
    if mutation == "reference":
        Image.new("RGB", (4, 4), "blue").save(ref)
    with pytest.raises(ValueError):
        await adapter.submit({})
    touch.assert_not_called()


async def test_uncertain_resume_never_reconfigures(tmp_path):
    from unittest.mock import AsyncMock

    _, jobs = flow.prepare_jobs(data(), tmp_path)
    adapter = type("Adapter", (), dict(configure=AsyncMock(), submit=AsyncMock()))()
    first = Runner(tmp_path / "r.json", jobs, adapter)
    first.checkpoint(first.data["jobs"][0], "uncertain")
    resumed = Runner(tmp_path / "r.json", jobs, adapter)
    assert await resumed.run() == 1
    adapter.configure.assert_not_called()
    adapter.submit.assert_not_called()
    text = (tmp_path / "r.json").read_text()
    assert "prompt" not in text


def test_character_voice_and_mode_fingerprinted(tmp_path):
    source = data()
    source["jobs"][0].update(
        type="video", mode="elements", character_id="saved-one", voice="Full voice one"
    )

    def fingerprint():
        _, jobs = flow.prepare_jobs(source, tmp_path)
        return Runner(tmp_path / "r.json", jobs, None).fingerprint

    first = fingerprint()
    source["jobs"][0]["voice"] = "Full voice two"
    second = fingerprint()
    source["jobs"][0]["character_id"] = "saved-two"
    assert first != second != fingerprint()
