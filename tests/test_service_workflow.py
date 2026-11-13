"""Exercise real submit orchestration against passive synthetic responses."""

import json
import time
from types import SimpleNamespace


from unittest.mock import AsyncMock

import pytest

from flow_provider import safe_ui as ui
from flow_provider.service_records import ServiceObserver, digest
from test_service_records import Page, Response, record


class Request:
    method = "POST"

    def __init__(self, post_data):
        self.post_data = post_data


@pytest.mark.asyncio
async def test_submit_ignores_rerendered_old_record_and_checkpoints_before_click(
    monkeypatch, tmp_path
):
    page = Page()
    page.url = "https://flow.google.com/u/1/project/project-1"
    observer = ServiceObserver(page, "1")
    observer.scope("project-1")
    page.callback(Response(json.dumps([record(asset="old-record")])))
    await observer.flush()
    adapter = ui.UIAdapter(tmp_path / "project.json")
    adapter.page, adapter.project_id, adapter.account_index = page, "project-1", "1"
    adapter.service = observer
    adapter.service_contract = object()
    from flow_provider.service_records import GenerationInvocationContract

    adapter.generation_contract = GenerationInvocationContract("generate", (0,), (1,))
    adapter.expected, adapter.cost = {}, 0
    adapter.reference_job = None
    adapter.ensure_direct_mode = AsyncMock()
    adapter.verify_project_identity = AsyncMock()
    adapter.verify_cost = AsyncMock(return_value=0)
    adapter.verify_service_result = AsyncMock()
    monkeypatch.setattr(ui, "require_auth", AsyncMock())
    monkeypatch.setattr(ui, "verify_configuration", AsyncMock())
    monkeypatch.setattr(ui, "references", AsyncMock(return_value=[]))
    # Legacy physical-card diff must never be consulted, even on old rerender.
    monkeypatch.setattr(
        ui, "stable_asset_baseline", AsyncMock(side_effect=AssertionError("legacy"))
    )
    monkeypatch.setattr(ui, "new_asset", AsyncMock(side_effect=AssertionError("legacy")))
    checkpoints = []
    adapter.set_job_intent("sealed-request", lambda value: checkpoints.append(value))
    events = []
    adapter.set_submit_observer(lambda stage, counts=None: events.append(stage))

    async def click():
        assert checkpoints and events[-1] == "before_click"
        # A re-rendered old result remains baseline, irrespective of DOM identity.
        old = record(asset="old-record")
        new = record(asset="new-record")
        now = time.time_ns()
        new[5][0] = [now // 10**9, now % 10**9]
        from urllib.parse import urlencode

        response = Response(json.dumps([["wrb.fr", "generate", json.dumps([old, new])]]))
        response.request = Request(
            urlencode(
                {
                    "f.req": json.dumps(
                        [
                            [
                                [
                                    "generate",
                                    json.dumps(
                                        [
                                            "exact prompt",
                                            {"reference_ids": [], "character": None, "voice": None},
                                        ]
                                    ),
                                    None,
                                    "generic",
                                ]
                            ]
                        ]
                    )
                }
            ),
        )
        observer.capture_request(response.request)
        page.callback(response)

    async def control(page, name):
        return SimpleNamespace(click=click if name == "submit" else AsyncMock())

    monkeypatch.setattr(ui, "control", control)
    result = await adapter.submit({"type": "image", "prompt": "exact prompt"})
    assert result == "service-" + digest("new-record")
    assert checkpoints[0]["baseline"] == [digest("old-record")]
    assert "exact prompt" not in json.dumps(checkpoints)
    adapter.verify_service_result.assert_awaited_once()


@pytest.mark.asyncio
async def test_unknown_detail_contract_blocks_before_submit(monkeypatch, tmp_path):
    adapter = ui.UIAdapter(tmp_path / "project.json")
    adapter.service_contract = None
    with pytest.raises(ValueError, match="contract unavailable"):
        await adapter.verify_service_result({}, None)


@pytest.mark.asyncio
async def test_exact_target_unique_even_with_group_peers_but_duplicate_target_rejects(tmp_path):
    from flow_provider.service_records import parse_records

    target = record(asset="target")
    cover = record(asset="cover")
    target[2] = cover[2] = "same-group"
    target[5][5] = "https://lh3.googleusercontent.com/output/target"
    cover[5][5] = "https://lh3.googleusercontent.com/output/cover"
    rows = parse_records(json.dumps([target, cover]), "project-1")

    class Items:
        def __init__(self, items):
            self.items = items

        async def all(self):
            return self.items

        async def count(self):
            return len(self.items)

    def card(url):
        media = SimpleNamespace(get_attribute=AsyncMock(return_value=url))
        return SimpleNamespace(
            locator=lambda selector: Items([] if selector == "flow-video-tile" else [media])
        )

    cards = [card(target[5][5]), card(cover[5][5])]
    adapter = ui.UIAdapter(tmp_path / "project.json")
    adapter.page = SimpleNamespace(locator=lambda selector: Items(cards))
    adapter.service = SimpleNamespace(records={row.asset: row for row in rows})
    assert await adapter.physical_service_card({"type": "image"}, rows[0]) is cards[0]
    cards.append(card(target[5][5]))
    with pytest.raises(ValueError, match="Ambiguous physical service target"):
        await adapter.physical_service_card({"type": "image"}, rows[0])
    cards.pop()
    cards.pop(0)
    assert await adapter.physical_service_card({"type": "image"}, rows[0]) is cards[0]
