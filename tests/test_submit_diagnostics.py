import json

import pytest

from flow_provider import safe_ui as ui
from flow_provider.batch import Runner
from flow_provider.diagnostics import ProofChanged, event, failure


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["character", "click", "lifecycle", "disk", "atomic_failure"])
async def test_real_browser_fault_boundaries(page, tmp_path, monkeypatch, fault):
    url = "https://flow.google.com/u/1/project/offline"
    await page.route(
        "**/*",
        lambda route: route.fulfill(
            body="""
      <button aria-label="settings">settings</button>
      <button aria-label="submit" onclick="window.clicks=(window.clicks||0)+1">submit</button>
      <div id="gallery"></div>""",
            content_type="text/html",
        ),
    )
    await page.goto(url)
    report = tmp_path / "report.json"

    async def noop(*args, **kwargs):
        return None

    async def refs(*args):
        return []

    async def config(*args):
        return {}

    async def cost():
        return 30

    async def control(scope, key):
        return scope.get_by_role("button", name=key, exact=True)

    async def character(*args, **kwargs):
        if fault == "character":
            raise ProofChanged(["sample", "description", "https://private.invalid/token"])

    adapter = ui.UIAdapter(tmp_path / "project.json", max_credits=30)
    adapter.account_index = "1"
    adapter.page = page
    adapter.refs = []
    adapter.expected = {}
    adapter.reference_job = None
    adapter.character = {"private": "do-not-persist"}
    adapter.cost = 30

    async def configure(job):
        return {"credits": 30}

    monkeypatch.setattr(adapter, "configure", configure)
    monkeypatch.setattr(adapter, "verify_project_identity", noop)
    monkeypatch.setattr(adapter, "ensure_direct_mode", noop)
    monkeypatch.setattr(adapter, "verify_cost", cost)
    monkeypatch.setattr(ui, "require_auth", noop)
    monkeypatch.setattr(ui, "references", refs)
    monkeypatch.setattr(ui, "verify_configuration", config)
    monkeypatch.setattr(ui, "verify_character", character)
    monkeypatch.setattr(ui, "control", control)
    real_baseline = ui.stable_asset_baseline

    async def baseline(*args):
        return await real_baseline(*args, timeout=1, quiet=0.02)

    monkeypatch.setattr(ui, "stable_asset_baseline", baseline)
    real_new = ui.new_asset

    async def lifecycle(*args, **kwargs):
        # Real browser lifecycle with no matching generated media must time out.
        return await real_new(*args, **kwargs, timeout=0.15, quiet=0.02)

    monkeypatch.setattr(ui, "new_asset", lifecycle)
    observed = []
    original_observe = adapter.observe_submit

    def observe(stage, counts=None):
        original_observe(stage, counts)
        saved = json.loads(report.read_text())["jobs"][0]
        observed.append((stage, saved["state"], saved.get("submit_evidence")))
        if fault == "disk" and stage == "before_click":
            raise OSError("private URL https://secret.invalid/?token=SECRET")
        if fault == "click" and stage == "click_returned":
            raise RuntimeError("private DOM SECRET")

    monkeypatch.setattr(adapter, "observe_submit", observe)
    jobs = [
        {"name": "video", "type": "video", "prompt": "SECRET", "file": str(tmp_path / "video.mp4")}
    ]
    runner = Runner(report, jobs, adapter, max_attempts=1)
    if fault == "atomic_failure":
        import copy
        from flow_provider import batch

        real_atomic = batch.atomic_json
        tripped = False

        def fail_before_click(path, data):
            nonlocal tripped
            if (
                not tripped
                and data["jobs"][0].get("submit_evidence", {}).get("stage") == "before_click"
            ):
                tripped = True
                # Interrupt the real production persistence boundary, not click.
                raise OSError("private SECRET")
            return real_atomic(path, copy.deepcopy(data))

        monkeypatch.setattr(batch, "atomic_json", fail_before_click)
    assert await runner.run() == 1
    row = json.loads(report.read_text())["jobs"][0]
    assert row["state"] == "uncertain" and row["attempts"] == {"configure": 1, "submit": 1}
    assert (
        row["failure"]["stage"]
        == {
            "character": "character",
            "disk": "before_click",
            "click": "click_returned",
            "lifecycle": "asset_lifecycle",
            "atomic_failure": "before_click",
        }[fault]
    )
    assert "SECRET" not in report.read_text() and "private" not in report.read_text()
    assert all(state == "uncertain" for _, state, _ in observed)
    clicks = await page.evaluate("window.clicks||0")
    assert clicks == (0 if fault in {"character", "disk", "atomic_failure"} else 1)
    if fault == "character":
        assert row["failure"]["fields"] == ["description", "sample"]
        assert row["submit_evidence"]["click_status"] == "not_reached"
    elif fault != "atomic_failure":
        assert any(
            stage == "before_click" and evidence["click_status"] == "uncertain"
            for stage, _, evidence in observed
        )
        assert row["baseline_evidence"]["counts"]["baseline_cards"] == 0
    original = report.read_bytes()
    assert await Runner(report, jobs, adapter, max_attempts=1).run() == 1
    assert report.read_bytes() == original
    assert await page.evaluate("window.clicks||0") == clicks


def test_diagnostics_never_copy_exception_values():
    error = ValueError("https://private.invalid/SECRET voice description")
    assert failure(error, "configure") == {
        "stage": "configure",
        "class": "ValueError",
        "frames": [],
    }
    with pytest.raises(ValueError):
        event("https://private.invalid")
    with pytest.raises(ValueError):
        event("baseline", {"token": 1})
    with pytest.raises(ValueError):
        event("baseline", {"bound": True})
