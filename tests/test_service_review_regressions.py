"""Independent review blockers: bounded reads, exact wire contract and identity."""

import asyncio
from dataclasses import replace
import json
from urllib.parse import urlencode

import pytest

from flow_provider.project import explicit_project, verify_project
from flow_provider.service_records import (
    GenerationInvocationContract,
    ServiceObserver,
    linked_response_records,
    parse_records,
    selected_image_source,
    stable_record_proof,
)
from test_service_records import Page, Response, record


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["headers", "body"])
async def test_stalled_response_reads_cancel_with_absolute_flush_deadline(stage):
    class Stalled(Response):
        async def all_headers(self):
            if stage == "headers":
                await asyncio.Event().wait()
            return await super().all_headers()

        async def text(self):
            await asyncio.Event().wait()

    observer = ServiceObserver(Page(), "1")
    observer.scope("project-1")
    observer.receive(Stalled("[]"))
    with pytest.raises(TimeoutError, match="deadline"):
        await asyncio.wait_for(observer.flush(timeout=0.05), timeout=1)
    assert observer.error
    await asyncio.sleep(0)
    assert not observer.tasks


@pytest.mark.asyncio
async def test_flush_does_not_follow_continuously_added_tasks():
    observer = ServiceObserver(Page(), "1")
    observer.scope("project-1")

    async def first():
        task = asyncio.create_task(asyncio.Event().wait())
        observer.tasks.add(task)
        task.add_done_callback(observer.tasks.discard)

    task = asyncio.create_task(first())
    observer.tasks.add(task)
    task.add_done_callback(observer.tasks.discard)
    await asyncio.wait_for(observer.flush(timeout=0.1), timeout=1)
    pending = list(observer.tasks)
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)


@pytest.mark.parametrize("rpc", ["search", "listProject", "unknown"])
def test_prompt_bearing_unknown_rpc_is_not_generation(rpc):
    contract = GenerationInvocationContract("verified-generation", (0,), (1,))
    post = urlencode({"f.req": json.dumps([[[rpc, json.dumps(["exact prompt", {}])]]])})
    body = json.dumps([["wrb.fr", rpc, json.dumps([record()])]])
    assert (
        linked_response_records(
            post, body, "project-1", "exact prompt", contract=contract, configuration={}
        )
        == []
    )


def test_known_rpc_still_requires_exact_configuration_slots():
    contract = GenerationInvocationContract("verified-generation", (0,), (1,))
    post = urlencode(
        {"f.req": json.dumps([[[contract.rpc, json.dumps(["exact prompt", {"model": "wrong"}])]]])}
    )
    body = json.dumps([["wrb.fr", contract.rpc, json.dumps([record()])]])
    assert (
        linked_response_records(
            post,
            body,
            "project-1",
            "exact prompt",
            contract=contract,
            configuration={"model": "expected"},
        )
        == []
    )
    assert linked_response_records(post, body, "project-1", "exact prompt") == []


def test_stable_record_proof_allows_location_rotation_not_ownership_changes():
    row = parse_records(json.dumps(record()), "project-1")[0]
    fresh = replace(row, thumbnail="/rotated/full/path")
    assert fresh.proof() != row.proof()
    assert stable_record_proof(fresh.proof()) == stable_record_proof(row.proof())
    for changed in [
        replace(row, model=37),
        replace(row, prompt="foreign"),
        replace(row, group_id="foreign"),
        replace(row, project="foreign"),
    ]:
        assert stable_record_proof(changed.proof()) != stable_record_proof(row.proof())


def test_observed_signed_main_image_uses_owning_record_id_not_group():
    row = replace(
        parse_records(json.dumps(record()), "project-1")[0],
        asset="11111111-1111-4111-8111-111111111111",
        group_id="22222222-2222-4222-8222-222222222222",
    )
    suffix = "?Expires=1&KeyName=synthetic&Signature=synthetic"
    assert selected_image_source(
        "https://flow-content.google/image/" + row.asset + suffix, row, "1"
    )
    assert not selected_image_source(
        "https://flow-content.google/image/" + row.group_id + suffix, row, "1"
    )
    with pytest.raises(ValueError):
        selected_image_source(
            "https://flow-content.google/image/" + row.asset + suffix + "&other=1", row, "1"
        )


def test_observed_editor_route_does_not_relax_explicit_project_input():
    url = "https://flow.google.com/u/1/project/project-1/edit/11111111-1111-4111-8111-111111111111"
    verify_project(url, "project-1", "1")
    for bad in [
        url.replace("/u/1/", "/u/2/"),
        url.replace("project-1", "foreign"),
        url + "/other",
        url + "?x=1",
    ]:
        with pytest.raises(ValueError):
            verify_project(bad, "project-1", "1")
    with pytest.raises(ValueError):
        explicit_project(url, "1")
