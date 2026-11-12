"""Image references are direct inputs, not video Elements/Frames tabs.

Real ephemeral offline Chromium only; never an authenticated/paid smoke.
"""

from unittest.mock import AsyncMock

from PIL import Image
import pytest

import flow
from flow_provider import safe_ui
from flow_provider.elements import validate_inputs
from test_character_contract import character_dom
from test_integration import app


@pytest.mark.parametrize("mode", ["elements", "frames"])
@pytest.mark.parametrize("inputs", [{}, {"character": "Unique"}, {"images": ["missing.png"]}])
async def test_image_modes_rejected_before_browser(tmp_path, monkeypatch, mode, inputs):
    job = dict(type="image", model="Nano Banana 2.1", mode=mode, **inputs)
    browser = AsyncMock(side_effect=AssertionError("No browser startup allowed"))
    monkeypatch.setattr(safe_ui.browser, "get_page", browser)
    with pytest.raises(ValueError, match="video-only.*without --mode"):
        flow.prepare_jobs({"jobs": [job]}, tmp_path)
    adapter = safe_ui.UIAdapter(tmp_path / "project.json")
    with pytest.raises(ValueError, match="video-only.*without --mode"):
        await adapter.configure(job)
    browser.assert_not_called()
    assert not (tmp_path / "project.json").exists()


@pytest.mark.parametrize("kind", ["image", "video"])
def test_reference_mode_preflight(kind):
    validate_inputs(dict(type="image", character="Unique", images=["reference.png"]))
    with pytest.raises(ValueError, match="voice.*image"):
        validate_inputs(dict(type="image", character="Unique", voice="Full voice"))
    if kind == "video":
        with pytest.raises(ValueError, match="explicit mode=elements"):
            validate_inputs(dict(type=kind, character="Unique"))
        validate_inputs(dict(type=kind, character="Unique", mode="elements"))


@pytest.mark.parametrize("singular", [False, True])
@pytest.mark.parametrize("drift", ["reference", "character", "cost", "model"])
async def test_image_reference_and_character_without_video_tabs(page, tmp_path, singular, drift):
    # Reuse independently tested observed character and upload DOM contracts.
    await character_dom(page)
    await page.locator(".character-voice-card, audio").evaluate_all(
        "nodes=>nodes.forEach(n=>n.remove())"
    )
    await page.locator("flow-prompt-box").evaluate("e=>e.replaceWith(...e.childNodes)")
    character_html = await page.locator("body").inner_html()
    png = await app(page)
    from test_observed_upload_sidebar import SIDEBAR

    # Real sidebar upload contract, exercised together with saved-character,
    # exact model/cost proof and pre-submit drift protection (never submit).
    await page.locator('#uploadPanel [role="option"]').evaluate("e=>e.remove()")
    await page.locator("#uploadPanel").evaluate(
        "(e, html)=>e.insertAdjacentHTML('afterbegin',html)", SIDEBAR
    )
    await page.evaluate("window.uploadClicks=0")
    await page.evaluate("html=>document.body.insertAdjacentHTML('beforeend',html)", character_html)
    await page.get_by_role("button", name="Adicionar elementos à caixa de comando").evaluate(
        "e=>e.remove()"
    )
    await page.evaluate("""() => {
      const original = window.finish;
      window.finish = () => { original(); window.uploadFinished = true; };
      document.querySelector('.add-menu-trigger').onclick = () => {
        if (!window.uploadFinished) uploadPanel.hidden = false;
        else document.querySelector('flow-add-menu-popover-content').hidden = false;
      };
    }""")
    source = tmp_path / "reference.png"
    source.write_bytes(png)
    _, jobs = flow.prepare_jobs(
        {
            "jobs": [
                dict(
                    type="image",
                    name="still",
                    model="Nano Banana 2.1",
                    prompt="Offline",
                    character="Unique",
                    **({"image": str(source)} if singular else {"images": [str(source)]}),
                )
            ]
        },
        tmp_path,
    )
    adapter = safe_ui.UIAdapter(tmp_path / "project.json", max_credits=1)
    adapter.page = page
    effective = await adapter.configure(jobs[0])
    assert effective["reference_count"] == 1
    assert effective["credits"] == 1
    assert adapter.expected is not None
    assert "reference_mode" not in adapter.expected
    assert adapter.character is not None
    assert adapter.character["name"] == "Unique"
    assert "voice" not in adapter.character
    assert await page.get_by_role("button", name="Elements", exact=True).count() == 0
    assert await page.evaluate("window.submits") == 0
    if drift == "reference":
        Image.new("RGB", (8, 8), "red").save(source)
        message = "Reference content changed"
    elif drift == "character":
        await page.locator("flow-character-ingredient-chip img").evaluate(
            "e=>e.src='https://flow.google.com/asb/changed'"
        )
        message = "Attached character changed"
    elif drift == "model":
        await page.locator('[data-testid="flow-model"]').evaluate("e=>e.textContent='Wrong model'")
        message = "configuration_mismatch"
    else:
        await page.locator("flow-generation-cost").evaluate(
            "e=>e.textContent='Generation cost: 2 credits'"
        )
        message = "cost_exceeds_approval"
    with pytest.raises(ValueError, match=message):
        await adapter.submit(jobs[0])
    assert await page.evaluate("window.submits") == 0


async def test_video_elements_still_requires_real_control(page, tmp_path):
    await app(page)
    await page.locator('flow-prompt-box-settings [role="radio"]').first.evaluate(
        "e=>e.textContent='Vídeo'"
    )
    adapter = safe_ui.UIAdapter(tmp_path / "project.json", max_credits=1)
    adapter.page = page
    with pytest.raises(ValueError):
        await adapter.configure(dict(type="video", mode="elements", model="Nano Banana 2.1"))
    assert await page.evaluate("window.submits") == 0


def test_image_cli_help_explains_direct_references(capsys):
    with pytest.raises(SystemExit) as error:
        flow.build_parser().parse_args(["image", "--help"])
    assert error.value.code == 0
    help_text = " ".join(capsys.readouterr().out.split())
    assert "video-only" in help_text
    assert "without --mode" in help_text


@pytest.mark.parametrize("mode", ["elements", "frames"])
@pytest.mark.parametrize("batch", [False, True])
def test_public_cli_rejects_with_static_guidance(tmp_path, monkeypatch, capsys, mode, batch):
    import json
    import sys

    private_prompt = "PRIVATE_PROMPT_SENTINEL"
    args = ["--out", str(tmp_path / "untouched")]
    if batch:
        source = tmp_path / "jobs.json"
        source.write_text(
            json.dumps(
                {"jobs": [dict(type="image", model="Exact", mode=mode, prompt=private_prompt)]}
            )
        )
        args = ["batch", str(source), *args]
    else:
        args = [
            "image",
            "--name",
            "still",
            "--model",
            "Exact",
            "--prompt",
            private_prompt,
            "--mode",
            mode,
            *args,
        ]
    monkeypatch.setattr(sys, "argv", ["flow.py", *args])
    assert flow.main() == 1
    output = capsys.readouterr()
    assert "video-only" in output.err and "without --mode" in output.err
    assert private_prompt not in output.err
    assert not (tmp_path / "untouched").exists()
