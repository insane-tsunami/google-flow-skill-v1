"""Explicit job inputs and fail-closed saved Element identity boundary.

Read-only observation found exact names and character previews, but no stable
saved-entry ID or attached-character identity mapping. One body variant was a
placeholder. Labels alone cannot prove the full Portrait/Body/Voice association.
Do not implement guessed selectors or accept synthetic identity attributes.
"""

import hashlib
from pathlib import Path

from .media import identifier, validate


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def exact_label(value):
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or len(value) > 200
        or any(c in value for c in ("…", "...", "\n", "\r", "\x00"))
    ):
        raise ValueError("An exact full label is required; truncated labels are not identities")
    return value


def validate_inputs(job):
    """Pure preflight, also used by the adapter before any browser startup."""
    kind = job.get("type", "image")
    character = job.get("character")
    character_id = job.get("character_id")
    if character is not None:
        exact_label(character)
    if character_id is not None:
        identifier(character_id)
    if character and character_id:
        raise ValueError("Choose character ID or exact unique name")
    if job.get("voice") is not None:
        exact_label(job["voice"])
        if kind == "image":
            raise ValueError("Explicit voice is unsupported for image jobs")
        if not (character or character_id):
            raise ValueError("Voice requires a saved character with verifiable association")
    frames = bool(job.get("start") or job.get("end"))
    elements = bool(job.get("images") or job.get("image") or character or character_id)
    mode = job.get("mode")
    if mode not in (None, "frames", "elements"):
        raise ValueError("Mode must be frames or elements")
    if frames and (elements or mode == "elements"):
        raise ValueError("Start/end frames cannot be combined with characters or Elements")
    if mode == "frames" and (kind != "video" or elements):
        raise ValueError("Frames mode requires video without Elements")
    if kind == "image" and frames:
        raise ValueError("Images do not support start/end frames")
    images = job.get("images", [])
    if not isinstance(images, list) or any(not isinstance(p, str) or not p for p in images):
        raise ValueError("images must be a list of local reference paths")
    if job.get("image") and images:
        raise ValueError("Use image or images, not both")
    if kind == "video" and elements and mode != "elements":
        raise ValueError("Video Elements require explicit mode=elements")


def seal_references(job):
    paths = [job[k] for k in ("image", "start", "end") if job.get(k)] + job.get("images", [])
    hashes = {}
    for path in paths:
        validate(path, "image")
        hashes[path] = digest(path)
    if hashes:
        job["reference_hashes"] = hashes


def verify_reference_bytes(job):
    for path, expected in job.get("reference_hashes", {}).items():
        if digest(path) != expected:
            raise ValueError("Reference content changed")


def require_observed_character_contract(job):
    # Deliberately no first-name match, generated identity or guessed voice row.
    # Image jobs skip associated voice entirely; explicit image voice fails preflight.
    from .safe_ui import ConfigurationError

    if job.get("character") or job.get("character_id"):
        raise ConfigurationError("saved_element_identity_dom_unverified", {})
