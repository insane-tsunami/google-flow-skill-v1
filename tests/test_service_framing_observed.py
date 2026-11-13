"""Framing derived from real read-only browser byte/count observations."""

import json
import pytest
from flow_provider.service_records import parse_records
from test_service_records import record


def framed(payload):
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    units = len(text.encode("utf-16-le")) // 2
    return str(units + 2) + "\n" + text + "\n"


@pytest.mark.parametrize("prompt", ["ASCII", "informação", "🍌 ensolarada"])
def test_observed_decimal_frames_count_utf16_and_newlines(prompt):
    payload = [["wrb.fr", "observed", json.dumps([record(prompt=prompt)], ensure_ascii=False)]]
    body = ")]}'\n\n" + framed(payload) + framed([["di", 0]])
    rows = parse_records(body, "project-1")
    assert len(rows) == 1
    assert rows[0].prompt == prompt


def test_observed_frame_requires_ending_delimiter():
    body = ")]}'\n" + framed([["wrb.fr", "observed", json.dumps([record()])]])
    with pytest.raises(ValueError):
        parse_records(body.rstrip("\n"), "project-1")


def test_user_authored_record_shaped_json_is_not_an_owning_record():
    injected = json.dumps(record(asset="spoofed"))
    rows = parse_records(json.dumps([record(prompt=injected)]), "project-1")
    assert [r.asset for r in rows] == ["record-1"]
