"""Read-only historical reconciliation audit. Never changes recovery state."""

import hashlib
import json
import os
from pathlib import Path

from .service_records import digest
from .media import lexical_output, identifier


def audit(report_path, evidence_path, output_path):
    report_path, evidence_path, output_path = map(Path, (report_path, evidence_path, output_path))
    output_path = lexical_output(output_path)
    if output_path.is_symlink() or output_path.exists():
        raise ValueError("Audit output must be new")
    raw, independent = report_path.read_bytes(), evidence_path.read_bytes()
    if len(raw) > 8_000_000 or len(independent) > 8_000_000:
        raise ValueError("Audit inputs too large")
    report, evidence = json.loads(raw), json.loads(independent)
    if (
        not isinstance(report, dict)
        or not isinstance(report.get("jobs"), list)
        or not all(isinstance(row, dict) for row in report["jobs"])
        or not isinstance(evidence, dict)
    ):
        raise ValueError("Invalid audit input schema")
    report_hash = hashlib.sha256(raw).hexdigest()
    if evidence.get("report_sha256") != report_hash:
        raise ValueError("Evidence must bind exact historical report bytes")
    matches = [r for r in report["jobs"] if r.get("name") == evidence.get("job")]
    if len(matches) != 1 or matches[0].get("state") != "uncertain":
        raise ValueError("One historical uncertain job required")
    row = matches[0]
    proof = evidence.get("proof", {})
    required = {"post_body_hash", "response_body_hash", "record"}
    if (
        not isinstance(proof, dict)
        or set(proof) != required
        or not isinstance(proof["record"], dict)
    ):
        raise ValueError("Independent invocation proof required")
    hashes = [
        proof["post_body_hash"],
        proof["response_body_hash"],
        proof["record"].get("asset_hash"),
        proof["record"].get("prompt_sha256", proof["record"].get("prompt_hash")),
    ]
    if any(
        not isinstance(h, str) or len(h) != 64 or any(c not in "0123456789abcdef" for c in h)
        for h in hashes
    ):
        raise ValueError("Invalid independent proof hashes")
    if evidence.get("expected_prompt_sha256") is not None and (
        evidence["expected_prompt_sha256"] != proof["record"].get("prompt_sha256")
    ):
        raise ValueError("Independent raw UTF-8 prompt hash mismatch")
    identifier(row["name"])
    result = {
        "version": 1,
        "mode": "readonly_independent_evidence_audit",
        "report_sha256": report_hash,
        "evidence_sha256": hashlib.sha256(independent).hexdigest(),
        "job": row["name"],
        "proof_hash": digest(proof),
        "candidate_asset": "service-" + proof["record"]["asset_hash"],
        "historical_state": "uncertain",
        "state_changed": False,
        "limit": "Evidence assertions are not authenticated by this offline audit; no download or resubmit authorized",
    }
    # Exclusive creation prevents overwriting historical evidence, even by race.
    fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(result, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    if os.name != "nt":
        parent_fd = os.open(output_path.parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    if report_path.read_bytes() != raw:
        raise ValueError("Historical report changed concurrently")
    return result
