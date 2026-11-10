"""Explicit inputs and observed saved-character UI association.

A unique exact picker row, its active detail pane and the resulting character
chip establish association; preview image IDs are never character IDs.
"""

import hashlib
import re
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
    if job.get("character_id"):
        from .safe_ui import ConfigurationError

        raise ConfigurationError("saved_character_id_not_exposed_use_exact_name", {})


async def picker_character(page, name, kind, voice=None):
    """Read only the uniquely active saved-character detail, never a global name."""
    from .safe_ui import unique

    picker = await unique(page.locator("flow-add-menu-popover-content:visible"))
    rows = (
        picker.get_by_role("option")
        .filter(has=page.locator(".asset-title", has_text=re.compile("^" + re.escape(name) + "$")))
        .filter(
            has=page.locator(
                ".type-subtitle", has_text=re.compile(r"^(?:Personagem|Character|Personaje)$")
            )
        )
    )
    search = await unique(picker.locator("input.search-input"), optional=True)
    if search is not None:
        await search.fill(name)
        await page.wait_for_timeout(500)
    viewport = picker.locator("cdk-virtual-scroll-viewport")
    if await viewport.count() and await viewport.evaluate("e=>e.scrollHeight>e.clientHeight+1"):
        raise ValueError("Character search results incomplete; uniqueness unverified")
    row = await unique(rows)
    # Clicking an already active option includes it immediately in current Flow.
    # Read its detail instead; only an inactive row needs a selection click.
    if "asset-item-active" not in (await row.get_attribute("class") or "").split():
        await row.click()
    await row.locator(
        'xpath=self::*[contains(concat(" ",normalize-space(@class)," ")," asset-item-active ")]'
    ).wait_for(state="visible", timeout=3000)
    if "asset-item-active" not in (await row.get_attribute("class") or "").split():
        raise ValueError("Character detail association unconfirmed")
    await picker.locator("flow-character-preview-pane:visible").wait_for(timeout=3000)
    preview = await unique(picker.locator("flow-character-preview-pane:visible"))
    thumbnail = await unique(row.locator("img"))
    source = await thumbnail.get_attribute("src")
    if not source or not source.startswith("https://flow.google.com/asb/"):
        raise ValueError("Character thumbnail missing")
    variants = await preview.locator(".character-thumbnail-image").evaluate_all(
        "es=>es.map(e=>({src:e.getAttribute('src'),loaded:e.complete&&e.naturalWidth>0}))"
    )
    if not variants or any(not v["src"] for v in variants):
        raise ValueError("Character variants missing or placeholder")
    # URLs are compared in memory only, never persisted or treated as saved IDs.
    from urllib.parse import urlsplit

    images = [urlsplit(v["src"]).path for v in variants]
    if any(not p.startswith("/image/") for p in images):
        raise ValueError("Character variants missing or placeholder")
    proof = {"name": name, "kind": kind, "thumbnail": source, "variants": images}
    if kind == "video":
        card = await unique(preview.locator(".character-voice-card:visible"))
        full = exact_label(await (await unique(card.locator(".character-voice-name"))).inner_text())
        description = exact_label(
            await (await unique(card.locator(".character-voice-description"))).inner_text()
        )
        audio = preview.locator("audio")
        if await audio.count() != 1:
            raise ValueError("Associated voice sample ambiguous")
        sample = await audio.get_attribute("src")
        if not sample or not sample.startswith(
            "https://www.gstatic.com/aitestkitchen/voices/samples/"
        ):
            raise ValueError("Associated voice sample unverified")
        if voice is not None and full != voice:
            raise ValueError("Explicit voice does not match saved character association")
        proof.update(voice=full, description=description, sample=sample)
    return proof


async def attach_character(page, job):
    from .safe_ui import control, unique

    if job.get("character_id"):
        raise ValueError("Saved character ID not exposed; use exact unique name")
    name = exact_label(job["character"])
    if await page.locator("flow-character-ingredient-chip:visible").count():
        raise ValueError("Preexisting character attachment; refusing to replace it")
    await (await control(page, "add")).click()
    proof = await picker_character(page, name, job.get("type", "image"), job.get("voice"))
    picker = await unique(page.locator("flow-add-menu-popover-content:visible"))
    await (await control(picker, "confirm")).click()
    await page.locator("flow-character-ingredient-chip:visible").wait_for(timeout=3000)
    await verify_character(page, proof)
    return proof


async def verify_character(page, proof, *, saved=False):
    from .safe_ui import unique

    chips = page.locator("flow-character-ingredient-chip:visible")
    if proof is None:
        if await chips.count():
            raise ValueError("Unverified attached character")
        return
    chip = await unique(chips)
    image = await unique(chip.locator("img"))
    if await image.get_attribute("src") != proof["thumbnail"]:
        raise ValueError("Attached character changed")
    if saved:
        # Flow omits already attached entries from its picker. Remove ONLY the
        # chip whose in-memory attachment proof was just checked, then reread
        # the saved association and reattach it without touching prompt/media.
        await (await unique(chip.locator("button"))).click()
        current = await attach_character(
            page,
            {
                "character": proof["name"],
                "type": proof["kind"],
                **({"voice": proof["voice"]} if "voice" in proof else {}),
            },
        )
        if current != proof:
            raise ValueError("Saved character or associated voice changed")
