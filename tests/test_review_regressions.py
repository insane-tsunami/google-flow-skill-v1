"""Independent-review regressions; keep these failing against the reviewed code."""

import hashlib
from pathlib import Path
import sys

from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_image_validation_without_python311_file_digest(tmp_path, monkeypatch):
    from flow_provider.media import validate

    path = tmp_path / "image.png"
    Image.new("RGB", (8, 8)).save(path)
    monkeypatch.delattr(hashlib, "file_digest", raising=False)
    assert len(validate(path, "image")["sha256"]) == 64


@pytest.mark.asyncio
async def test_video_tools_preflight_before_project(tmp_path, monkeypatch):
    import shutil
    from flow_provider.safe_ui import UIAdapter

    monkeypatch.setattr(shutil, "which", lambda _: None)
    adapter = UIAdapter(tmp_path / "project.json")
    calls = []

    async def forbidden():
        calls.append("project")
        raise AssertionError("Must fail before opening a browser/project")

    monkeypatch.setattr(adapter, "ensure_project", forbidden)
    with pytest.raises(ValueError, match="video_decoder"):
        await adapter.configure({"type": "video", "model": "Omni 1.2 Flash"})
    assert calls == []


@pytest.mark.asyncio
async def test_failed_initialization_does_not_poison_next_job(tmp_path, monkeypatch):
    from flow_provider.safe_ui import UIAdapter
    from flow_provider import browser, project
    import flow_provider.safe_ui as ui

    calls = []
    fake_page = type("Page", (), {"url": "https://flow.google.com/project/project-1"})()

    async def page():
        return fake_page

    async def create(*, expected):
        calls.append("create")
        if len(calls) == 1:
            raise OSError("synthetic failure")
        return "project-1", "https://labs.google/project/project-1"

    async def auth(_):
        pass

    monkeypatch.setattr(browser, "get_page", page)
    monkeypatch.setattr(project, "create_project", create)
    monkeypatch.setattr(ui, "require_auth", auth)
    adapter = UIAdapter(tmp_path / "project.json")
    with pytest.raises(OSError):
        await adapter.ensure_project()
    assert adapter.page is None
    await adapter.ensure_project()
    assert calls == ["create", "create"]
    assert (tmp_path / "project.json").exists()
