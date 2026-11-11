"""Observed navigation-header title contract, without private identifiers."""

import pytest

from flow_provider.safe_ui import UIAdapter


async def test_observed_editable_title(page, tmp_path, monkeypatch):
    monkeypatch.setenv("FLOW_ACCOUNT_INDEX", "2")
    adapter = UIAdapter(
        tmp_path / "project.json",
        project_scope=dict(project="example", account_index="2", title="Exact project"),
    )
    adapter.page = page
    # URL/account identity is exercised separately; isolate the title readback.
    await page.set_content(
        "<flow-navigation-header><flow-editable-text>"
        '<input value="Exact project">'
        "</flow-editable-text></flow-navigation-header>"
    )
    await adapter.verify_project_identity()
    await page.locator("input").fill("Other project")
    with pytest.raises(ValueError, match="title mismatch"):
        await adapter.verify_project_identity()
    await page.set_content(
        "<flow-navigation-header><flow-editable-text>"
        '<input value="Exact project"><input value="Exact project">'
        "</flow-editable-text></flow-navigation-header>"
    )
    with pytest.raises(ValueError, match="ambiguous"):
        await adapter.verify_project_identity()
