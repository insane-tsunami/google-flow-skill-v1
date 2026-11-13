import hashlib
import json

import pytest

import flow
from flow_provider.service_records import digest


@pytest.mark.asyncio
async def test_public_readonly_reconcile_preserves_exhausted_original(tmp_path):
    report = tmp_path / "batch_report.json"
    raw = (
        b'{"jobs":[{"name":"historical","state":"uncertain","attempts":{"submit":1,"download":3}}]}'
    )
    report.write_bytes(raw)
    evidence = tmp_path / "independent.json"
    evidence.write_text(
        json.dumps(
            {
                "report_sha256": hashlib.sha256(raw).hexdigest(),
                "job": "historical",
                "proof": {
                    "post_body_hash": digest("post"),
                    "response_body_hash": digest("response"),
                    "record": {"asset_hash": digest("record"), "prompt_hash": digest("prompt")},
                },
            }
        )
    )
    out = tmp_path / "audit.json"
    args = flow.build_parser().parse_args(
        ["reconcile", "--report", str(report), "--evidence", str(evidence), "--output", str(out)]
    )
    assert await flow.execute(args) == 0
    assert report.read_bytes() == raw
    result = json.loads(out.read_text())
    assert result["state_changed"] is False
    assert result["historical_state"] == "uncertain"
    with pytest.raises(ValueError, match="must be new"):
        await flow.execute(args)
    assert report.read_bytes() == raw
