"""Sanitized observed response contracts; no network or private fixtures."""

import json
import pytest
from flow_provider.service_records import (
    canonical_thumbnail,
    parse_records,
    GenerationInvocationContract,
)

SYNTHETIC_CONTRACT = GenerationInvocationContract("generate", (0,), (1,))


def record(kind="image", prompt="exact prompt", asset="record-1"):
    q = [
        [1700000000, 123],
        None,
        None,
        None,
        None,
        "https://lh3.googleusercontent.com/opaque/path=s512-rw",
        None,
    ]
    v = [asset, "project-1", None, None, None, q, None]
    if kind == "image":
        q[6] = [None, None, [[prompt]], None, 1]
        v[6] = [[None] * 8 + [36]]
    else:
        q[1] = prompt
        q[6] = [None, [["internal-video-model"]]]
    return v


@pytest.mark.parametrize("kind", ["image", "video"])
def test_observed_embedded_framing(kind):
    payload = json.dumps([["wrb.fr", "rpc", json.dumps([record(kind)])]])
    body = ")]}'\n" + str(len(payload.encode("utf-16-le")) // 2 + 2) + "\n" + payload + "\n"
    rows = parse_records(body, "project-1")
    assert len(rows) == 1
    assert rows[0].kind == kind
    assert rows[0].prompt == "exact prompt"
    assert rows[0].asset == "record-1"
    assert "opaque" not in json.dumps(rows[0].proof())


def test_project_and_unknown_schema_fail_closed():
    assert parse_records(json.dumps(record()), "other-project") == []
    v = record()
    v[6][0][8] = "invented"
    assert parse_records(json.dumps(v), "project-1") == []


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.test/opaque/path",
        "https://lh3.googleusercontent.com/p?token=x",
        "https://lh3.googleusercontent.com/p=s999-rw",
        "http://lh3.googleusercontent.com/p",
        "https://lh3.googleusercontent.com/p#x",
        "https://lh3.googleusercontent.com/%2fp",
    ],
)
def test_unknown_url_refused(url):
    with pytest.raises(ValueError):
        canonical_thumbnail(url)


def test_entire_path_not_token():
    assert canonical_thumbnail("https://lh3.googleusercontent.com/a/b=s512-rw") == "/a/b"
    assert canonical_thumbnail("https://flow.google.com/a/b=s1600-rw") == "/a/b"
    assert canonical_thumbnail("https://lh3.googleusercontent.com/x/b") != "/a/b"


def test_duplicate_record_and_conflicting_owner():
    v = record()
    assert len(parse_records(json.dumps([v, v]), "project-1")) == 1
    changed = record(prompt="different")
    with pytest.raises(ValueError, match="Conflicting"):
        parse_records(json.dumps([v, changed]), "project-1")


def test_missing_and_ambiguous_records():
    from flow_provider.service_records import select_record

    rows = parse_records(json.dumps([record(), record(asset="record-2")]), "project-1")
    arguments = dict(
        baseline=set(),
        project="project-1",
        kind="image",
        prompt="exact prompt",
        start_ns=1700000000 * 10**9,
        end_ns=1700000001 * 10**9,
    )
    with pytest.raises(ValueError):
        select_record(rows, **arguments)
    with pytest.raises(ValueError):
        select_record([], **arguments)
    assert select_record(rows[:1], **arguments).asset == "record-1"
    for change in [
        dict(baseline={"record-1"}),
        dict(kind="video"),
        dict(project="other"),
        dict(prompt="partial"),
        dict(start_ns=1700000002 * 10**9),
    ]:
        with pytest.raises(ValueError):
            select_record(rows[:1], **(arguments | change))


def test_bad_frames_and_nesting():
    for body in ["100\n[]", ")]}'\nno JSON", "[" * 40 + "0" + "]" * 40]:
        with pytest.raises(ValueError):
            parse_records(body, "project-1")


def test_physical_mapping_survives_reorder_and_rejects_duplicates():
    from flow_provider.service_records import match_physical_tile

    rows = parse_records(json.dumps(record()), "project-1")
    old = ["https://lh3.googleusercontent.com/old/path=s512-rw"]
    target = ["https://flow.google.com/opaque/path=s1600-rw"]
    assert match_physical_tile(rows, [old, target]) == 1
    assert match_physical_tile(rows, [target, old]) == 0
    for tiles in [[old], [target, target], [["https://unknown.test/opaque/path"], target]]:
        with pytest.raises(ValueError):
            match_physical_tile(rows, tiles)


class Response:
    url = "https://flow.google.com/u/1/_/AiSandboxAngularFrontend/data/batchexecute?rpcids=observed"
    status = 200
    request = type("Request", (), {"method": "GET", "post_data": None})()

    def __init__(self, body):
        self.body = body

    async def all_headers(self):
        return {"content-type": "application/json; charset=utf-8"}

    async def text(self):
        return self.body


class Page:
    def on(self, name, callback):
        if name == "response":
            self.callback = callback


@pytest.mark.asyncio
async def test_passive_observer_account_baseline_and_reload_identity():
    from flow_provider.service_records import ServiceObserver, digest

    page = Page()
    observer = ServiceObserver(page, "1")
    observer.scope("project-1")
    with pytest.raises(ValueError, match="Known owning"):
        await observer.baseline()
    # An arbitrary successful empty frame cannot establish an empty project.
    page.callback(Response("[]"))
    with pytest.raises(ValueError, match="Known owning"):
        await observer.baseline()
    foreign = Response(json.dumps([record()]))
    foreign.url = foreign.url.replace("/u/1/", "/u/2/")
    page.callback(foreign)
    with pytest.raises(ValueError):
        await observer.baseline()
    page.callback(Response(json.dumps([record()])))
    assert await observer.baseline() == {"record-1"}
    assert observer.known(digest("record-1")).asset == "record-1"
    # Same stable record survives a rotated URL; no historical URL is required.
    fresh = record()
    fresh[5][5] = "https://flow.google.com/current/thumbnail=s1600-rw"
    page.callback(Response(json.dumps([fresh])))
    await observer.flush()
    assert observer.known(digest("record-1")).thumbnail == "/current/thumbnail"
    observer.scope("different-project")
    with pytest.raises(ValueError):
        await observer.baseline()


@pytest.mark.parametrize(
    "mutation", ["other_rpc", "missing_prompt", "multiple_invocations", "other_response"]
)
def test_exact_invocation_link_refuses_unrelated_records(mutation):
    from urllib.parse import urlencode
    from flow_provider.service_records import linked_response_records

    calls = [["generate", json.dumps(["exact prompt", {}]), None, "generic"]]
    rpc = "generate"
    if mutation == "other_rpc":
        rpc = "listProject"
    elif mutation == "missing_prompt":
        calls[0][1] = json.dumps(["other prompt"])
    elif mutation == "multiple_invocations":
        calls.append(["listProject", "[]", None, "generic"])
    body = json.dumps([["wrb.fr", rpc, json.dumps([record()])]])
    if mutation == "other_response":
        body = json.dumps([record()])
    post = urlencode({"f.req": json.dumps([calls])})
    assert (
        linked_response_records(
            post, body, "project-1", "exact prompt", contract=SYNTHETIC_CONTRACT, configuration={}
        )
        == []
    )


def test_exact_invocation_link_hashes_only_and_explicit_group():
    from urllib.parse import urlencode
    from flow_provider.service_records import linked_response_records, digest

    value = record()
    value[2] = "group-1"
    post = urlencode(
        {"f.req": json.dumps([[["generate", json.dumps(["exact prompt", {}]), None, "generic"]]])}
    )
    body = json.dumps([["wrb.fr", "generate", json.dumps([value])]])
    rows = linked_response_records(
        post, body, "project-1", "exact prompt", contract=SYNTHETIC_CONTRACT, configuration={}
    )
    assert len(rows) == 1
    assert rows[0].group_id == "group-1"
    assert rows[0].proof()["group_hash"] == digest("group-1")
    assert "group-1" not in json.dumps(rows[0].proof())


def test_frozen_account_query_only():
    assert (
        canonical_thumbnail("https://flow.google.com/opaque/path=s512-rw?authuser=1", "1")
        == "/opaque/path"
    )
    for url in [
        "https://flow.google.com/opaque/path?authuser=2",
        "https://flow.google.com/opaque/path?authuser=1&authuser=1",
        "https://flow.google.com/opaque/path?authuser=1&token=secret",
    ]:
        with pytest.raises(ValueError):
            canonical_thumbnail(url, "1")
