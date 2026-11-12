"""Conservative Flow UI adapter. Unknown DOM means stop, not substitution."""

import asyncio
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import parse_qs, urlsplit

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from . import browser
from .elements import (
    attach_character,
    verify_character,
    require_observed_character_contract,
    seal_references,
    validate_inputs,
    verify_reference_bytes,
)
from .media import (
    atomic_json,
    identifier,
    lexical_output,
    prepare_media,
    publish,
    recover_output,
    validate,
)
from .security import require_auth
from .selectors import control, unique

PANEL = "flow-prompt-box-settings:visible"
CARDS = 'flow-grid-tile-container, flow-tile-container, [aria-roledescription="draggable"]'
ATTACHED = (
    ".ingredient-bar-container img, flow-prompt-box button img, flow-rich-text-editor .mention-chip"
)


class ConfigurationError(ValueError):
    """Only explicitly allowlisted public configuration evidence is persisted."""

    def __init__(self, code, evidence):
        def sanitize(value):
            if isinstance(value, dict):
                if any(
                    k
                    not in {
                        "available",
                        "missing_tools",
                        "requested",
                        "effective",
                        "model",
                        "ratio",
                        "count",
                        "reference_count",
                        "reference_mode",
                        "duration",
                        "selected",
                        "type",
                    }
                    for k in value
                ):
                    raise ValueError("Unsafe diagnostic field")
                return {k: sanitize(v) for k, v in value.items()}
            if isinstance(value, list):
                return [sanitize(v) for v in value]
            if isinstance(value, str):
                if (
                    len(value) > 100
                    or not re.fullmatch(r"[\w .:()×x/+-]+", value)
                    or "://" in value
                ):
                    raise ValueError("Unsafe public label")
                return value
            if value is None or isinstance(value, (int, bool)):
                return value
            raise ValueError("Unsafe diagnostic value")

        self.evidence = sanitize(evidence)
        self.code = identifier(code)
        super().__init__(f"{code}; discovered {self.evidence.get('available', [])}")


async def configuration_snapshot(panel):
    active = []
    for item in await panel.locator(
        '[aria-checked="true"], [aria-selected="true"], [aria-pressed="true"], [data-state="active"], [data-state="on"]'
    ).all():
        if await item.is_visible():
            active.append(clean(await item.inner_text()))
    return {"model": clean(await (await control(panel, "model")).inner_text()), "selected": active}


def clean(text):
    return " ".join(text.replace("arrow_drop_down", "").replace("🍌", "").split())


async def panel_for(page):
    panel = await unique(page.locator(PANEL), optional=True)
    if panel is None:
        await (await control(page, "settings")).click()
        await page.locator(PANEL).wait_for(state="visible", timeout=5000)
        panel = await unique(page.locator(PANEL))
    return panel


async def discover_models(page):
    menu = await unique(
        page.locator('[role="menu"]:visible, [role="listbox"][data-model-menu]:visible')
    )
    items = menu.locator('[role="menuitem"], [role="option"]')
    names = [
        clean(await i.inner_text())
        for i in await items.all()
        if await i.is_visible() and await i.is_enabled()
    ]
    if not names or len(names) != len(set(names)):
        raise ValueError("Model discovery empty or ambiguous")
    return names


async def choose_model(menu, model):
    matches = [
        item
        for item in await menu.locator('[role="menuitem"], [role="option"]').all()
        if await item.is_visible()
        and await item.is_enabled()
        and clean(await item.inner_text()) == model
    ]
    if len(matches) != 1:
        raise ValueError("Model selection unresolved or ambiguous")
    await matches[0].click()


async def selected(panel, text):
    locator = (
        panel.get_by_role("radio", name=text, exact=True)
        .or_(panel.get_by_role("button", name=text, exact=True))
        .or_(panel.get_by_role("tab", name=text, exact=True))
    )
    item = await unique(locator)
    active = [
        await item.get_attribute(a)
        for a in ("aria-checked", "aria-selected", "aria-pressed", "data-state")
    ]
    return any(value in ("true", "on", "active", "checked") for value in active)


async def choose(panel, text):
    item = await unique(
        panel.get_by_role("radio", name=text, exact=True)
        .or_(panel.get_by_role("button", name=text, exact=True))
        .or_(panel.get_by_role("tab", name=text, exact=True))
    )
    await item.click()
    if not await selected(panel, text):
        raise ValueError("Selection did not persist")


def duration_seconds(text):
    match = re.fullmatch(r"(\d+)\s*(?:s|seconds?|segundos?)", clean(text), re.I)
    return int(match.group(1)) if match else None


async def duration_slider(panel):
    sliders = [
        item
        for item in await panel.locator('input[type="range"], [role="slider"]').all()
        if await item.is_visible() and await item.is_enabled()
    ]
    candidates = []
    for slider in sliders:
        # A duration label must belong to this component, never the whole panel.
        component = slider.locator(
            'xpath=ancestor::*[contains(concat(" ", normalize-space(@class), " "), " duration-slider-section ") '
            'or @aria-label="Duration" or @aria-label="Duração" '
            'or @aria-label="Duración" or *[normalize-space(text())="Duration" '
            'or normalize-space(text())="Duração" or normalize-space(text())="Duración"]][1]'
        )
        if await component.count() and await component.evaluate(
            "(element, panel) => element !== panel && panel.contains(element)",
            await panel.element_handle(),
        ):
            candidates.append((slider, component))
    if not candidates:
        if sliders:
            raise ValueError("Duration slider scope unknown")
        return None
    if len(candidates) != 1:
        raise ValueError("Duration slider ambiguous")
    slider, component = candidates[0]
    native_range = await slider.evaluate('e => e.matches("input[type=range]")')
    bounds = []
    for native, aria in (("min", "aria-valuemin"), ("max", "aria-valuemax")):
        raw = await slider.get_attribute(native if native_range else aria)
        if raw is None and not native_range:
            raw = await slider.get_attribute(native)
        try:
            value = float(raw)
            aria_raw = await slider.get_attribute(aria) if native_range else None
            if aria_raw is not None and float(aria_raw) != value:
                raise ValueError("Duration native and ARIA bounds conflict")
        except (TypeError, ValueError):
            raise ValueError("Duration slider bounds unknown or conflicting") from None
        if not math.isfinite(value):
            raise ValueError("Duration slider bounds invalid")
        bounds.append(value)
    step = await slider.get_attribute("step") or "1"
    try:
        step = float(step)
    except ValueError:
        raise ValueError("Duration slider step unknown") from None
    if not math.isfinite(step) or step <= 0 or bounds[1] < bounds[0]:
        raise ValueError("Duration slider bounds invalid")
    intervals = (bounds[1] - bounds[0]) / step
    if not math.isfinite(intervals) or not intervals.is_integer() or intervals > 31:
        raise ValueError("Duration slider exceeds bounded positions")
    return slider, component, bounds, int(intervals) + 1


async def read_duration_slider(state):
    slider, component, bounds, _ = state
    native_range = await slider.evaluate('e => e.matches("input[type=range]")')
    aria_raw = await slider.get_attribute("aria-valuenow")
    raw = await slider.input_value() if native_range else aria_raw
    if raw is None:
        raise ValueError("Duration slider readback unknown")
    try:
        position = float(raw)
        if native_range and aria_raw is not None and float(aria_raw) != position:
            raise ValueError("Duration native and ARIA position conflict")
    except (TypeError, ValueError):
        raise ValueError("Duration slider readback unknown or conflicting") from None
    if not math.isfinite(position) or not bounds[0] <= position <= bounds[1]:
        raise ValueError("Duration slider readback invalid")
    semantics = []
    # Rendered text is local to the duration component. Bare numbers in
    # valuetext are indices, not seconds, and cannot establish duration.
    text = clean(await component.inner_text())
    text = re.sub(r"^(?:Duration|Duração|Duración)\s*:?\s*", "", text, flags=re.I)
    if text:
        semantic = duration_seconds(text)
        if semantic is None:
            raise ValueError("Duration label unknown or ambiguous")
        semantics.append(semantic)
    for attribute in ("aria-valuetext", "aria-label"):
        value = await slider.get_attribute(attribute) or ""
        value = re.sub(r"^(?:Duration|Duração|Duración)\s*:?\s*", "", value, flags=re.I)
        semantic = duration_seconds(value)
        if semantic is not None:
            semantics.append(semantic)
        elif value and not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", value):
            raise ValueError("Duration accessible label unknown")
    if not semantics or len(set(semantics)) != 1:
        raise ValueError("Duration label unknown or ambiguous")
    return position, semantics[0]


async def verify_duration(panel, duration):
    wanted = duration_seconds(duration)
    if wanted is None:
        raise ValueError("Invalid duration")
    state = await duration_slider(panel)
    if state is not None:
        if (await read_duration_slider(state))[1] != wanted:
            raise ValueError("Duration not confirmed")
    elif not await selected(panel, f"{wanted} s"):
        raise ValueError("Duration not confirmed")


async def configure_duration(panel, duration):
    wanted = duration_seconds(duration)
    if wanted is None:
        raise ValueError("Invalid duration")
    state = await duration_slider(panel)
    if state is None:
        await choose(panel, f"{wanted} s")
        return
    current = await read_duration_slider(state)
    if current[1] == wanted:
        await verify_duration(panel, duration)
        return
    slider, _, bounds, positions = state
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 10

    async def bounded(operation, until):
        remaining = until - loop.time()
        if remaining <= 0:
            raise ValueError("Duration keyboard readback failed")
        try:
            result = await asyncio.wait_for(operation(), timeout=remaining)
        except asyncio.TimeoutError:
            raise ValueError("Duration keyboard readback failed") from None
        if loop.time() >= until:
            raise ValueError("Duration keyboard readback failed")
        return result

    async def settled_readback(before, expected):
        # Native range values change synchronously; rendered seconds may lag.
        # Never send another key while that transition remains unconfirmed.
        transition_deadline = min(deadline, loop.time() + 2)
        while True:
            observed = await bounded(lambda: read_duration_slider(state), transition_deadline)
            if observed[0] == expected and (expected == before[0] or observed[1] != before[1]):
                return observed
            await bounded(lambda: asyncio.sleep(0.025), transition_deadline)

    await bounded(lambda: slider.press("Home"), deadline)
    observed = await settled_readback(current, bounds[0])
    previous = None
    seen = set()
    for index in range(positions):
        position, semantic = observed
        if (
            (index == 0 and position != bounds[0])
            or (previous is not None and (position <= previous[0] or semantic == previous[1]))
            or semantic in seen
        ):
            raise ValueError("Duration keyboard readback failed")
        seen.add(semantic)
        if semantic == wanted:
            await bounded(lambda: verify_duration(panel, duration), deadline)
            return
        previous = position, semantic
        if index + 1 < positions:
            await bounded(lambda: slider.press("ArrowRight"), deadline)
            step = (bounds[1] - bounds[0]) / (positions - 1)
            observed = await settled_readback(previous, bounds[0] + (index + 1) * step)
    raise ValueError("Duration unavailable")


def _attached_image_id(src):
    # Only the observed service URL is evidence. Never include signed URLs in
    # diagnostics or durable state; return just the path UUID.
    match = re.fullmatch(
        r"https://flow-content\.google/image/"
        r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
        r"(?:\?[^\s#]*)?",
        src or "",
    )
    if match is None:
        raise ValueError("Attached reference source unverified")
    return identifier(match.group(1))


class ReferenceNotReady(ValueError):
    """Only the observed busy image chip may wait during an owned upload."""


async def references(page, character=None):
    await verify_character(page, character)
    values = []
    attached = (
        ATTACHED + ", :is(.ingredient-bar-container, flow-prompt-box) flow-image-ingredient-chip"
    )
    for element in await page.locator(attached).all():
        if not await element.is_visible():
            continue
        if await element.evaluate("e=>e.localName === 'flow-image-ingredient-chip'"):
            chip = element
            busy = chip.locator(
                ':scope > button.chip-container[aria-label="Elemento"][aria-busy="true"]'
            )
            if await busy.count() == 1:
                raise ReferenceNotReady("Attached image upload not ready")
            placeholder = chip.locator(
                ':scope > button.chip-container[aria-label="Elemento"][aria-busy="false"]'
                " > div.chip-image-wrapper > div.chip-placeholder"
            )
            if await chip.locator("img").count() == 0 and await placeholder.count() == 1:
                raise ReferenceNotReady("Attached image placeholder not ready")
            image = chip.locator(
                ':scope > button.chip-container[aria-label="Elemento"][aria-busy="false"]'
                ' > div.chip-image-wrapper > img.chip-image[alt="Imagem do elemento"]'
            )
            if await chip.locator("img").count() != 1 or await image.count() != 1:
                raise ValueError("Ambiguous or unready attached image")
            if not await image.is_visible():
                raise ValueError("Attached reference identity unverified")
            value = _attached_image_id(await image.get_attribute("src"))
            for attr in ("data-media-id", "data-mention-id"):
                explicit = await image.get_attribute(attr)
                if explicit is not None and explicit != value:
                    raise ValueError("Conflicting attached reference identity")
            values.append(value)
            continue
        if await element.evaluate(
            "e=>!!e.closest('flow-character-ingredient-chip, flow-image-ingredient-chip')"
        ):
            continue
        value = await element.get_attribute("data-media-id") or await element.get_attribute(
            "data-mention-id"
        )
        if not value:
            raise ValueError("Attached reference identity unverified")
        values.append(identifier(value))
    if len(values) != len(set(values)):
        raise ValueError("Ambiguous attached references")
    return values


async def verify_configuration(page, request, refs, character=None):
    panel = await panel_for(page)
    actual = clean(await (await control(panel, "model")).inner_text())
    evidence = {"requested": request, "effective": await configuration_snapshot(panel)}
    if (
        actual != request["model"]
        or not await selected(panel, request["ratio"])
        or not await selected(panel, f"x{request['count']}")
    ):
        raise ConfigurationError("configuration_mismatch", evidence)
    if request.get("type"):
        mode = await control(panel, request["type"])
        if not any(
            [
                await mode.get_attribute(a) in ("true", "on", "active")
                for a in ("aria-checked", "aria-selected", "aria-pressed", "data-state")
            ]
        ):
            raise ConfigurationError("mode_unconfirmed", evidence)
    if request.get("reference_mode"):
        mode = await control(panel, request["reference_mode"])
        if not any(
            [
                await mode.get_attribute(a) in ("true", "on", "active")
                for a in ("aria-checked", "aria-selected", "aria-pressed", "data-state")
            ]
        ):
            raise ConfigurationError("reference_mode_unconfirmed", {})
    if sorted(await references(page, character)) != sorted(refs):
        raise ConfigurationError("reference_mismatch", evidence)
    duration = request.get("duration")
    if duration:
        await verify_duration(panel, duration)
    return {
        "model": actual,
        "ratio": request["ratio"],
        "count": request["count"],
        "reference_count": len(refs),
        "duration": duration,
    }


async def asset_map(page):
    found = {}
    # The service nests grid wrappers around physical tiles after rendering.
    # Attribute the innermost card once, while keeping distinct duplicate cards
    # ambiguous. Do not deduplicate merely by asset ID or choose the newest card.
    physical_cards = f":is({CARDS}):not(:has(:is({CARDS})))"
    for card in await page.locator(physical_cards).all():
        ids = set()
        for media in await card.locator("img, video").all():
            value = await media.get_attribute("data-media-id")
            if not value:
                src = urlsplit(await media.get_attribute("src") or "")
                value = parse_qs(src.query).get("name", [None])[0]
                if not value:
                    match = re.search(r"/(?:image|video)/([A-Za-z0-9_-]+)", src.path)
                    value = match.group(1) if match else None
            if value:
                ids.add(identifier(value))
        for value in ids:
            if value in found:
                raise ValueError("Duplicate asset identity")
            found[value] = card
    return found


async def asset_ids(page):
    return set(await asset_map(page))


async def stable_asset_baseline(page, refs, *, timeout=30, quiet=1.0):
    """Wait for owned uploads to reach the gallery, then seal physical cards.

    An unchanged ID set alone misses a pending generation card with no media ID.
    Keep DOM node identity as well; a quiet window is readiness, not attribution.
    """
    deadline = asyncio.get_running_loop().time() + timeout
    previous = None
    unchanged = asyncio.get_running_loop().time()
    while True:
        cards = await page.evaluate_handle(
            "selector => Array.from(document.querySelectorAll(selector))",
            f":is({CARDS}):not(:has(:is({CARDS})))",
        )
        ids = await asset_ids(page)
        progressing = await page.locator(f":is({CARDS}) [role=progressbar]").count()
        now = asyncio.get_running_loop().time()
        same = (
            previous is not None
            and ids == previous["ids"]
            and progressing == previous["progressing"]
            and await cards.evaluate(
                "(els, old) => els.length === old.length && els.every((e, i) => e === old[i])",
                previous["cards"],
            )
        )
        if not same:
            unchanged = now
        if previous is not None:
            await previous["cards"].dispose()
        previous = {"ids": ids, "cards": cards, "progressing": progressing}
        if not progressing and set(refs).issubset(ids) and now - unchanged >= quiet:
            return previous
        if now >= deadline:
            await cards.dispose()
            raise TimeoutError("Pre-submit gallery and uploaded references not stable")
        await asyncio.sleep(0.1)


async def new_asset(page, before, timeout=180, *, kind=None, prompt=None, quiet=1.0, observer=None):
    """Bind a newly created generated card through its observed progress lifecycle.

    Never use a unique new ID, latest card, prompt match alone, or media signature
    as submission proof. Missing lifecycle/type evidence remains uncertain.
    """
    if not isinstance(before, dict) or kind not in ("image", "video") or not prompt:
        raise ValueError("Submission lifecycle baseline and media kind required")
    deadline = asyncio.get_running_loop().time() + timeout
    bound = None
    candidate_ids = set()
    ready_since = None
    last_evidence = None
    try:
        while True:
            candidates = []
            for card in await page.locator(f":is({CARDS}):not(:has(:is({CARDS})))").all():
                if await card.evaluate("(e, old) => old.includes(e)", before["cards"]):
                    continue
                if not await card.locator(f"flow-{kind}-tile").count():
                    continue
                if await card.locator(
                    f"flow-{'image' if kind == 'video' else 'video'}-tile"
                ).count():
                    raise ValueError("Conflicting media kind: attribution uncertain")
                candidates.append(card)
            if len(candidates) > 1:
                raise ValueError("Multiple generated cards: attribution uncertain")
            evidence = {
                "candidate_cards": len(candidates),
                "candidate_ids": len(candidate_ids),
                "bound": int(bound is not None),
            }
            if observer is not None and evidence != last_evidence:
                observer("asset_lifecycle", evidence)
                last_evidence = evidence
            if candidates:
                card = candidates[0]
                if bound is None:
                    # Progress is structural service evidence, not text authored
                    # in a prompt. Require exact prompt in a separate text node.
                    progress = card.locator('[role="progressbar"]')
                    if (
                        await progress.count() == 1
                        and await card.get_by_text(prompt, exact=True).count() == 1
                    ):
                        bound = await card.element_handle()
                elif not await card.evaluate("(e, original) => e === original", bound):
                    raise ValueError("Generated card replaced: attribution uncertain")
                if bound is not None:
                    if not await card.locator('[role="progressbar"]').count():
                        await card.hover(
                            timeout=max(1, (deadline - asyncio.get_running_loop().time()) * 1000)
                        )
                    current = await asset_map(page)
                    ids = set()
                    for media in await card.locator("video" if kind == "video" else "img").all():
                        value = await media.get_attribute("data-media-id")
                        src = urlsplit(await media.get_attribute("src") or "")
                        if not value:
                            value = parse_qs(src.query).get("name", [None])[0]
                        if not value:
                            match = re.search(rf"/{kind}/([A-Za-z0-9_-]+)", src.path)
                            value = match.group(1) if match else None
                        if value:
                            value = identifier(value)
                            owner = current.get(value)
                            if owner is not None and await owner.evaluate(
                                "(e, original) => e === original", bound
                            ):
                                ids.add(value)
                    if ids & before["ids"]:
                        raise ValueError("Preexisting generated identity: attribution uncertain")
                    candidate_ids.update(ids)
                    if len(candidate_ids) > 1:
                        raise ValueError("Multiple generated identities: attribution uncertain")
                    if len(ids) == 1 and not await card.locator('[role="progressbar"]').count():
                        now = asyncio.get_running_loop().time()
                        if ready_since is None:
                            ready_since = now
                        if now - ready_since >= quiet:
                            return next(iter(ids))
                    else:
                        ready_since = None
            else:
                ready_since = None
                if bound is not None:
                    raise ValueError("Generated card disappeared: attribution uncertain")
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError("Submission-bound asset identity not confirmed")
            await asyncio.sleep(0.1)
    except PlaywrightTimeoutError:
        raise TimeoutError("Submission-bound asset identity not confirmed") from None
    finally:
        await before["cards"].dispose()
        if bound is not None:
            await bound.dispose()


async def upload_reference(page, path, slot=None):
    path = Path(path)
    validate(path, "image")
    before = set(await references(page))
    await (await control(page, slot or "add")).click()
    panel = await unique(
        page.locator('flow-add-menu-popover-content:visible, [role="dialog"]:visible')
    )
    async with page.expect_file_chooser(timeout=8000) as event:
        await (await control(panel, "upload")).click()
    await (await event.value).set_files(str(path.resolve()))
    # No automatic acceptance of rights, policy or agent approvals. Human must
    # resolve them; only the specific attachment confirmation is automated.
    deadline = asyncio.get_running_loop().time() + 60
    confirmed = False
    while asyncio.get_running_loop().time() < deadline:
        try:
            current = set(await references(page))
        except ReferenceNotReady:
            # Only while this invocation owns an in-flight upload. Never treat
            # ambiguous/unknown chips or pre-submit busy state as valid proof.
            await asyncio.sleep(0.25)
            continue
        if not before.issubset(current):
            raise ValueError("An existing reference was replaced during upload")
        added = current - before
        if len(added) == 1:
            return added.pop()
        if len(added) > 1:
            raise ValueError("Ambiguous reference attachment")
        if not confirmed and await panel.is_visible():
            confirm = await control(panel, "confirm", optional=True)
            if confirm is not None:
                await confirm.click()
                confirmed = True
        await asyncio.sleep(0.25)
    raise ValueError("Reference attachment unconfirmed; resolve human notices")


class UIAdapter:
    def __init__(self, project_file, *, direct_mode=False, max_credits=None, project_scope=None):
        from .project import account_index

        self.account_index = account_index()
        self.project_scope = project_scope
        self.project_id = None
        self.reference_job = None
        if project_scope:
            from .project import explicit_project

            explicit_project(project_scope["project"], self.account_index)
            if project_scope["account_index"] != self.account_index:
                raise ValueError("Explicit project account mismatch")
        self.direct_mode = direct_mode
        self.max_credits = max_credits
        self.cost = None
        self.project_file = Path(project_file)
        self.page = None
        self.expected = None
        self.refs = []

    async def ensure_project(self):
        if self.page is not None:
            from .project import verify_account

            verify_account(self.page.url, self.account_index)
            await require_auth(self.page)
            await self.verify_project_identity()
            return
        from .project import create_project, navigate_to_project

        data = None
        if self.project_file.exists():
            data = json.loads(self.project_file.read_text())
            if data.get("account_index") != self.account_index:
                raise ValueError("Persisted project account mismatch")
        if data and self.project_scope and data.get("project") != self.project_scope["project"]:
            raise ValueError("Persisted project target mismatch")
        page = await browser.get_page()
        new_project = None
        if self.project_file.exists():
            data = json.loads(self.project_file.read_text())
            await navigate_to_project(identifier(data["project"]), expected=self.account_index)
        elif self.project_scope:
            new_project = self.project_scope["project"]
            await navigate_to_project(new_project, expected=self.account_index)
        else:
            project, _ = await create_project(expected=self.account_index)
            new_project = identifier(project)
        await require_auth(page)
        from .project import verify_account

        verify_account(page.url, self.account_index)
        self.project_id = new_project if new_project is not None else identifier(data["project"])
        self.page = page
        await self.verify_project_identity()
        if new_project is not None:
            atomic_json(
                self.project_file, {"project": new_project, "account_index": self.account_index}
            )
        self.page = page

    async def verify_project_identity(self):
        from .project import verify_project

        if self.project_id is not None:
            verify_project(self.page.url, self.project_id, self.account_index)
        title = self.project_scope.get("title") if self.project_scope else None
        if title is not None:
            # Observed Flow title is a navigation-header editable input; a
            # unique exact heading remains supported for older layouts.
            field = await unique(
                self.page.locator("flow-navigation-header flow-editable-text input:visible"),
                optional=True,
            )
            if field is not None:
                if await field.input_value() != title:
                    raise ValueError("Explicit project title mismatch")
            else:
                await unique(self.page.get_by_role("heading", name=title, exact=True))

    async def configure(self, job):
        validate_inputs(job)
        verify_reference_bytes(job)
        if job.get("character") or job.get("character_id"):
            require_observed_character_contract(job)
        if self.page is not None:
            from .project import verify_account

            verify_account(self.page.url, self.account_index)
            await self.verify_project_identity()
        self.reference_job = dict(job)
        seal_references(self.reference_job)
        if job.get("type") == "video":
            missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
            if missing:
                raise ConfigurationError(
                    "video_decoder_install_ffmpeg_and_ffprobe_on_PATH", {"missing_tools": missing}
                )
        self.require_credit_approval()
        await self.ensure_project()
        await require_auth(self.page)
        previous = getattr(self, "character", None)
        # Preserve human attachments, but permit retries/batch continuation with
        # exactly the adapter-owned references from its previous configuration.
        current = await references(self.page, previous)
        if sorted(current) != sorted(getattr(self, "refs", [])):
            raise ValueError("Unexpected preexisting references")
        if previous is not None:
            # references() has just proved this exact adapter-owned chip.
            chip = await unique(self.page.locator("flow-character-ingredient-chip:visible button"))
            await chip.click()
        self.character = None
        from .project import verify_account

        verify_account(self.page.url, self.account_index)
        if job.get("count", 1) != 1:
            raise ValueError("One asset per job is required")
        await self.ensure_direct_mode()
        panel = await panel_for(self.page)
        mode = await control(panel, job.get("type", "image"))
        await mode.click()
        await choose(panel, job.get("ratio", "9:16"))
        await choose(panel, "x1")
        # Elements/Frames is a video panel contract, not the image add/reference
        # picker. validate_inputs rejects image modes before opening any browser.
        reference_mode = None
        if job.get("type", "image") == "video":
            reference_mode = job.get("mode") or (
                "frames" if job.get("start") or job.get("end") else None
            )
        if reference_mode:
            await (await control(panel, reference_mode)).click()
        trigger = await control(panel, "model")
        await trigger.click()
        options = await discover_models(self.page)
        model = job["model"]
        if model not in options:
            # Only public labels; never dump DOM, URLs or prompt.
            raise ConfigurationError(
                "model_unavailable", {"available": options, "requested": {"model": model}}
            )
        menu = await unique(
            self.page.locator('[role="menu"]:visible, [role="listbox"][data-model-menu]:visible')
        )
        await choose_model(menu, model)
        if job.get("duration"):
            await configure_duration(panel, job["duration"])
        self.expected = {
            "model": model,
            "type": job.get("type", "image"),
            "ratio": job.get("ratio", "9:16"),
            "count": 1,
            "duration": job.get("duration"),
            **({"reference_mode": reference_mode} if reference_mode else {}),
        }
        await (await control(self.page, "settings")).click()
        editor = await control(self.page, "editor")
        await editor.click()
        await editor.press("ControlOrMeta+a")
        await editor.press("Backspace")
        await self.page.keyboard.insert_text(job.get("prompt", ""))
        if await references(self.page):
            raise ValueError("Unexpected references remain from previous job")
        self.refs = []
        for key, slot in [("image", None), ("start", "initial"), ("end", "final")]:
            if job.get(key):
                self.refs.append(await upload_reference(self.page, job[key], slot))
        for path in job.get("images", []):
            self.refs.append(await upload_reference(self.page, path))
        if job.get("character"):
            self.character = await attach_character(self.page, job)
        verify_reference_bytes(self.reference_job)
        await self.verify_project_identity()
        effective = await verify_configuration(self.page, self.expected, self.refs, self.character)
        self.cost = await self.verify_cost()
        return effective | {"credits": self.cost}

    def set_submit_observer(self, observer):
        self._submit_observer = observer

    def observe_submit(self, stage, counts=None):
        observer = getattr(self, "_submit_observer", None)
        if observer is not None:
            observer(stage, counts)

    async def submit(self, job):
        from .project import verify_account

        self.observe_submit("authentication")
        await require_auth(self.page)
        verify_account(self.page.url, self.account_index)
        self.observe_submit("project")
        await self.verify_project_identity()
        self.observe_submit("references")
        if self.reference_job is not None:
            verify_reference_bytes(self.reference_job)
        self.observe_submit("direct_mode")
        await self.ensure_direct_mode()
        character = getattr(self, "character", None)
        self.observe_submit("character")
        if character is not None:
            await verify_character(self.page, character, saved=True)
        # Re-read after upload and prompt editing, immediately before click.
        self.observe_submit("configuration")
        await verify_configuration(self.page, self.expected, self.refs, character)
        self.observe_submit("cost")
        if await self.verify_cost() != self.cost:
            raise ConfigurationError("generation_cost_changed", {})
        self.observe_submit("references")
        await (await control(self.page, "settings")).click()
        if sorted(await references(self.page, character)) != sorted(self.refs):
            raise ConfigurationError("reference_mismatch", {})
        self.observe_submit("baseline")
        before = await stable_asset_baseline(self.page, self.refs)
        try:
            self.observe_submit(
                "baseline",
                {
                    "baseline_ids": len(before["ids"]),
                    "baseline_cards": await before["cards"].evaluate("es=>es.length"),
                    "baseline_progressing": before["progressing"],
                },
            )
            verify_account(self.page.url, self.account_index)
            self.observe_submit("project")
            await self.verify_project_identity()
            self.observe_submit("references")
            if self.reference_job is not None:
                verify_reference_bytes(self.reference_job)
            if sorted(await references(self.page, character)) != sorted(self.refs):
                raise ConfigurationError("reference_mismatch", {})
            button = await control(self.page, "submit")
            self.observe_submit("before_click")
            await button.click()
            self.observe_submit("click_returned")
        except BaseException:
            await before["cards"].dispose()
            raise
        return await new_asset(
            self.page,
            before,
            kind=job.get("type", "image"),
            prompt=job.get("prompt"),
            observer=self.observe_submit,
        )

    def require_credit_approval(self):
        value = self.max_credits
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise ConfigurationError("explicit_max_credits_required", {})

    async def verify_cost(self):
        self.require_credit_approval()
        # A dedicated UI component is the trust boundary. Never search composer
        # text: prompts, chips and user-authored markup are not cost evidence.
        composer = await unique(self.page.locator("flow-prompt-box:visible"), optional=True)
        if composer is None:
            raise ConfigurationError("generation_cost_unknown", {})
        # Prefer the observed service component in the visible settings panel.
        # An invalid service component must never fall back to a cheaper legacy label.
        safe = (
            ":not(:is([contenteditable], textarea, input, flow-rich-text-editor, .ProseMirror) *)"
            ":not(:has([contenteditable], textarea, input, flow-rich-text-editor, .ProseMirror))"
            ":not([contenteditable])"
        )
        panel = await unique(self.page.locator(PANEL), optional=True)
        service_selector = ":scope > div > flow-credit-cost-label.settings-credit-cost"
        service = panel.locator(service_selector) if panel is not None else None
        if service is not None and await service.count():
            labels = panel.locator(service_selector + safe)
        else:
            labels = composer.locator("flow-generation-cost" + safe)
        try:
            label = await unique(labels)
        except ValueError:
            raise ConfigurationError("generation_cost_unknown", {}) from None
        text = " ".join((await label.inner_text()).split())
        match = re.fullmatch(
            r"(?:(?:Generation cost|Custo da geração|Custo de geração|Coste de generación): "
            r"|A geração vai usar\s*)(0|[1-9][0-9]*) (?:credits|créditos)",
            text,
            re.I,
        )
        if not match:
            raise ConfigurationError("generation_cost_unknown", {})
        cost = int(match.group(1))
        if cost > self.max_credits:
            raise ConfigurationError("generation_cost_exceeds_approval", {})
        return cost

    async def ensure_direct_mode(self):
        sidebar = await unique(self.page.locator("flow-agent-panel:visible"), optional=True)
        if sidebar is not None:
            if not self.direct_mode:
                raise ConfigurationError("agent_mode_requires_direct_mode_opt_in", {})
            # Global Fechar is ambiguous: close only the observed agent sidebar.
            await (await unique(sidebar.get_by_role("button", name="Fechar", exact=True))).click()

        async def prove_direct():
            trigger = await control(self.page, "settings")
            panel = await unique(self.page.locator(PANEL), optional=True)
            if panel is None:
                await trigger.click()
                await self.page.locator(PANEL).wait_for(state="visible", timeout=1500)
                panel = await unique(self.page.locator(PANEL))
            await control(panel, "model")

        agent = await unique(
            self.page.get_by_role("button", name=re.compile(r"^(?:Agente|Agent)$")), optional=True
        )
        pressed = await agent.get_attribute("aria-pressed") if agent is not None else None
        # A persistent inactive chip is normal. Existing generation proof wins
        # over presence alone; only a confirmed active chip needs toggling.
        if pressed != "true":
            try:
                await prove_direct()
                return
            except (ValueError, PlaywrightTimeoutError):
                if agent is None or pressed == "false":
                    raise ConfigurationError("direct_mode_unconfirmed", {}) from None
        if agent is not None:
            if not self.direct_mode:
                raise ConfigurationError("agent_mode_requires_direct_mode_opt_in", {})
            if pressed not in (None, "true"):
                raise ConfigurationError("direct_mode_unconfirmed", {})
            await agent.click()
            direct = await unique(
                self.page.get_by_role("button", name=re.compile(r"^(?:Direto|Direct)$")),
                optional=True,
            )
            if direct is not None:
                await direct.click()
        try:
            await prove_direct()
            remaining = await unique(
                self.page.get_by_role("button", name=re.compile(r"^(?:Agente|Agent)$")),
                optional=True,
            )
            if remaining is not None and await remaining.get_attribute("aria-pressed") != "false":
                raise ValueError("Agent still active or unknown")
        except (ValueError, PlaywrightTimeoutError):
            raise ConfigurationError("direct_mode_unconfirmed", {}) from None

    async def download(self, job, asset):
        from .project import verify_account

        await self.ensure_project()
        verify_account(self.page.url, self.account_index)
        return await download_asset(self.page, job, asset)


async def download_asset(page, job, asset):
    from .security import ProfileLock

    destination = lexical_output(job["file"])
    with ProfileLock(destination.parent / ("." + destination.name + ".lock")):
        return await _download_asset(page, job, asset)


async def _download_asset(page, job, asset):
    asset = identifier(asset)
    destination = lexical_output(job["file"])
    receipt = destination.with_name(destination.name + ".receipt.json")
    timeout = job.get("generation_timeout", 180)
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or not 0 < timeout <= 600
    ):
        raise ValueError("generation_timeout must be finite and in (0, 600]")
    if destination.exists() or destination.is_symlink():
        return recover_output(destination, asset, job["type"])
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout

    def remaining():
        seconds = deadline - loop.time()
        if seconds <= 0:
            raise TimeoutError("Known asset/download action not ready")
        return seconds * 1000

    async def ready_action():
        menu_open = False
        while True:
            remaining()
            cards = await asset_map(page)
            card = cards.get(asset)
            if card is not None:
                other = "image" if job["type"] == "video" else "video"
                if await card.locator(f"flow-{other}-tile").count():
                    raise ValueError("Known asset media kind mismatch")
                await card.hover(timeout=remaining())
                direct = await control(card, "download", optional=True)
                if direct is not None:
                    return direct
                if not menu_open:
                    more = await control(card, "more", optional=True)
                    if more is not None:
                        await more.click(timeout=remaining())
                        menu_open = True
                if menu_open:
                    menu = await unique(page.locator('[role="menu"]:visible'), optional=True)
                    if menu is not None:
                        direct = await control(menu, "download", optional=True)
                        if direct is not None:
                            return direct
            await asyncio.sleep(min(0.1, remaining() / 1000))

    # Bound even DOM queries and transient detachments by the same deadline.
    try:
        direct = await asyncio.wait_for(ready_action(), timeout=remaining() / 1000)
    except (TimeoutError, asyncio.TimeoutError, PlaywrightTimeoutError):
        raise TimeoutError("Known asset/download action not ready") from None
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".flow-download-") as temp:
        async with page.expect_download(timeout=remaining()) as event:
            await direct.click(timeout=remaining())
            # Service submenus render asynchronously and decorate the original
            # 1K option with a subtitle. Never substitute an enhanced 2K/4K item.
            menus = page.locator('[role="menu"]:visible')
            resolution = job.get("resolution", "720p" if job["type"] == "video" else "1K")
            name = re.compile(r"^" + re.escape(resolution) + r"(?:\s+Tamanho original)?" + r"$")
            choices = menus.get_by_role("menuitem", name=name)
            if await direct.get_attribute("aria-haspopup") == "menu":
                await choices.wait_for(state="visible", timeout=remaining())
            choice = await unique(choices, optional=True)
            if choice is not None:
                await choice.click(timeout=remaining())
        download = await event.value
        if await asyncio.wait_for(download.failure(), timeout=remaining() / 1000):
            raise OSError("Browser download failed")
        source = Path(temp) / "payload"
        await asyncio.wait_for(download.save_as(source), timeout=remaining() / 1000)
        # Durable receipt precedes atomic publication, so a process dying after
        # publication can recover the exact known asset rather than regenerate.
        metadata = prepare_media(source, destination, job["type"]) | {
            "asset": asset,
            "file": str(destination.resolve()),
        }
        atomic_json(receipt, metadata)
        published = publish(source, destination, asset, job["type"])
        if published != metadata:
            raise ValueError("Publication integrity changed")
        return metadata
