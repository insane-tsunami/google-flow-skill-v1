import pytest
from flow_provider import project
from flow_provider.safe_ui import UIAdapter
from flow import build_parser


def test_explicit_account_route(monkeypatch):
    monkeypatch.setenv("FLOW_ACCOUNT_INDEX", "1")
    assert project.flow_url() == "https://flow.google.com/u/1/"
    project.verify_account("https://labs.google/fx/tools/flow/u/1/project/p")
    for url in [
        "https://labs.google/fx/tools/flow/project/p",
        "https://labs.google/fx/tools/flow/u/0/project/p",
        "https://evil.test/fx/tools/flow/u/1/project/p",
    ]:
        with pytest.raises(ValueError):
            project.verify_account(url)


def test_invalid_account(monkeypatch):
    for value in ["", "-1", "1/../0", "01"]:
        monkeypatch.setenv("FLOW_ACCOUNT_INDEX", value)
        with pytest.raises(ValueError):
            project.flow_url()


def test_cli_authorization():
    args = build_parser().parse_args(
        [
            "image",
            "--model",
            "M",
            "--prompt",
            "P",
            "--name",
            "n",
            "--direct-mode",
            "--max-credits",
            "2",
        ]
    )
    assert args.direct_mode and args.max_credits == 2


def test_approval_validation(tmp_path):
    for value in [None, -1, float("nan"), float("inf"), True]:
        adapter = UIAdapter(tmp_path / "project.json", max_credits=value)
        with pytest.raises(ValueError):
            adapter.require_credit_approval()


@pytest.mark.asyncio
async def test_foreign_project_blocked_before_browser(tmp_path, monkeypatch):
    async def forbidden():
        raise AssertionError("browser access forbidden")

    monkeypatch.setattr("flow_provider.browser.get_page", forbidden)
    monkeypatch.setenv("FLOW_ACCOUNT_INDEX", "1")
    path = tmp_path / "project.json"
    path.write_text('{"project":"p","account_index":"0"}')
    with pytest.raises(ValueError, match="account"):
        await UIAdapter(path).ensure_project()


class Element:
    def __init__(self, text="", visible=True):
        self.text, self.visible, self.clicks = text, visible, 0

    async def all(self):
        return [self] if self.visible else []

    async def is_visible(self):
        return self.visible

    async def is_enabled(self):
        return True

    async def inner_text(self):
        return self.text

    async def click(self):
        self.clicks += 1
        self.visible = False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "label,maximum,ok",
    [
        ("Generation cost: 2 credits", 2, True),
        ("Custo da geração: 0 créditos", 0, True),
        ("Generation cost: 3 credits", 2, False),
        ("Generation cost: unknown credits", 2, False),
        ("Balance: 200 credits", 2, False),
        ("Generation cost: 1.5 credits", 2, False),
    ],
)
async def test_cost_fail_closed(page, tmp_path, label, maximum, ok):
    adapter = UIAdapter(tmp_path / "p.json", max_credits=maximum)
    await page.set_content(
        f"<flow-prompt-box><flow-generation-cost>{label}</flow-generation-cost></flow-prompt-box>"
    )
    adapter.page = page
    if ok:
        assert await adapter.verify_cost() <= maximum
    else:
        with pytest.raises(ValueError):
            await adapter.verify_cost()


@pytest.mark.asyncio
@pytest.mark.parametrize("authorized", [False, True])
async def test_exact_direct_transition(page, tmp_path, authorized):
    adapter = UIAdapter(tmp_path / "p.json", direct_mode=authorized)
    await page.set_content(
        '<button onclick="this.remove(); document.querySelector(\'#direct\').hidden=false">Agent</button>\n    <button id="direct" hidden onclick="this.remove(); document.querySelector(\'section\').hidden=false">Direct</button>\n    <section hidden><button aria-label="Settings trigger" onclick="document.querySelector(\'flow-prompt-box-settings\').hidden=false"></button>\n    <flow-prompt-box-settings hidden><button aria-label="Select model family">M</button></flow-prompt-box-settings></section>'
    )
    adapter.page = page
    if authorized:
        await adapter.ensure_direct_mode()
        assert await page.locator("flow-prompt-box-settings").is_visible()
    else:
        with pytest.raises(ValueError, match="opt_in"):
            await adapter.ensure_direct_mode()
        assert await page.get_by_role("button", name="Agent", exact=True).is_visible()


@pytest.mark.asyncio
async def test_account_redirect_blocks_before_create(monkeypatch):
    from unittest.mock import AsyncMock

    from types import SimpleNamespace

    page = SimpleNamespace()
    page.url = "https://labs.google/fx/tools/flow/u/0"
    page.goto = AsyncMock()
    control = AsyncMock(side_effect=AssertionError("no create control allowed"))
    monkeypatch.setenv("FLOW_ACCOUNT_INDEX", "1")
    monkeypatch.setattr(project, "get_page", AsyncMock(return_value=page))
    monkeypatch.setattr(project, "require_auth", AsyncMock())
    monkeypatch.setattr(project, "control", control)
    with pytest.raises(ValueError, match="account"):
        await project.create_project()
    control.assert_not_called()
    assert page.goto.call_args.args[0] == "https://flow.google.com/u/1/"


@pytest.mark.asyncio
async def test_account_drift_blocks_before_submit(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock
    import flow_provider.safe_ui as ui

    monkeypatch.setenv("FLOW_ACCOUNT_INDEX", "1")
    adapter = UIAdapter(tmp_path / "p.json", max_credits=1)
    from types import SimpleNamespace

    adapter.page = SimpleNamespace()
    adapter.page.url = "https://labs.google/fx/tools/flow/u/0/project/p"
    monkeypatch.setattr(ui, "require_auth", AsyncMock())
    with pytest.raises(ValueError, match="account"):
        await adapter.submit({})


@pytest.mark.asyncio
async def test_cost_drift_blocks_submit(page, tmp_path, monkeypatch):
    from unittest.mock import AsyncMock
    import flow_provider.safe_ui as ui

    monkeypatch.delenv("FLOW_ACCOUNT_INDEX", raising=False)
    adapter = UIAdapter(tmp_path / "p.json", max_credits=3)
    await page.set_content(
        "<flow-prompt-box><flow-generation-cost>Generation cost: 2 credits</flow-generation-cost></flow-prompt-box>"
    )
    adapter.page = page
    monkeypatch.setattr(adapter, "ensure_direct_mode", AsyncMock())
    adapter.cost = 1
    monkeypatch.setattr(ui, "require_auth", AsyncMock())
    monkeypatch.setattr(ui, "verify_configuration", AsyncMock())
    monkeypatch.setattr(ui, "asset_ids", AsyncMock(return_value=set()))
    submit = Element()

    async def control(_, key):
        assert key == "settings", "submit control must never be requested"
        return submit

    monkeypatch.setattr(ui, "control", control)
    with pytest.raises(ValueError, match="cost_changed"):
        await adapter.submit({})


@pytest.mark.asyncio
async def test_missing_approval_blocks_before_project(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    adapter = UIAdapter(tmp_path / "p.json")
    project_call = AsyncMock(side_effect=AssertionError("project forbidden"))
    monkeypatch.setattr(adapter, "ensure_project", project_call)
    with pytest.raises(ValueError, match="max_credits_required"):
        await adapter.configure({"type": "image"})
    project_call.assert_not_called()
