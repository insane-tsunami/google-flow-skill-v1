"""Conservative Flow UI adapter. Unknown DOM means stop, not substitution."""

import asyncio
import json
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import parse_qs, urlsplit

from . import browser
from .media import atomic_json, identifier, publish, validate
from .security import require_auth
from .selectors import control, unique

PANEL = "flow-prompt-box-settings:visible"
CARDS = 'flow-grid-tile-container, flow-tile-container, [aria-roledescription="draggable"]'
ATTACHED = (
    ".ingredient-bar-container img, "
    "flow-prompt-box button img[data-media-id], "
    "flow-rich-text-editor .mention-chip[data-mention-id]"
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


async def references(page):
    values = []
    for element in await page.locator(ATTACHED).all():
        if await element.is_visible():
            value = await element.get_attribute("data-media-id") or await element.get_attribute(
                "data-mention-id"
            )
            if value:
                values.append(identifier(value))
    if len(values) != len(set(values)):
        raise ValueError("Ambiguous attached references")
    return values


async def verify_configuration(page, request, refs):
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
    if sorted(await references(page)) != sorted(refs):
        raise ConfigurationError("reference_mismatch", evidence)
    duration = request.get("duration")
    if duration:
        match = re.fullmatch(r"(\d+)\s*s", duration)
        if not match or not await selected(panel, f"{match.group(1)} s"):
            raise ValueError("Duration not confirmed")
    return {
        "model": actual,
        "ratio": request["ratio"],
        "count": request["count"],
        "reference_count": len(refs),
        "duration": duration,
    }


async def asset_map(page):
    found = {}
    for card in await page.locator(CARDS).all():
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


async def new_asset(page, before, timeout=180):
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        added = (await asset_ids(page)) - before
        if len(added) > 1:
            raise ValueError("Multiple new assets: attribution uncertain")
        if len(added) == 1:
            return added.pop()
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("Asset identity not confirmed")
        await asyncio.sleep(0.5)


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
        current = set(await references(page))
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
    def __init__(self, project_file):
        self.project_file = Path(project_file)
        self.page = None
        self.expected = None
        self.refs = []

    async def ensure_project(self):
        if self.page is not None:
            return
        from .project import create_project, navigate_to_project

        page = await browser.get_page()
        new_project = None
        if self.project_file.exists():
            data = json.loads(self.project_file.read_text())
            await navigate_to_project(identifier(data["project"]))
        else:
            project, _ = await create_project()
            new_project = identifier(project)
        await require_auth(page)
        if new_project is not None:
            atomic_json(self.project_file, {"project": new_project})
        self.page = page

    async def configure(self, job):
        if job.get("type") == "video":
            missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
            if missing:
                raise ConfigurationError(
                    "video_decoder_install_ffmpeg_and_ffprobe_on_PATH", {"missing_tools": missing}
                )
        await self.ensure_project()
        await require_auth(self.page)
        if job.get("count", 1) != 1:
            raise ValueError("One asset per job is required")
        panel = await panel_for(self.page)
        mode = await control(panel, job.get("type", "image"))
        await mode.click()
        await choose(panel, job.get("ratio", "9:16"))
        await choose(panel, "x1")
        if job.get("type") == "video" and (job.get("start") or job.get("end")):
            await (await control(panel, "frames")).click()
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
        item = await unique(
            menu.get_by_role("menuitem", name=model, exact=True).or_(
                menu.get_by_role("option", name=model, exact=True)
            )
        )
        await item.click()
        if job.get("duration"):
            match = re.fullmatch(r"(\d+)\s*s", job["duration"])
            if not match:
                raise ValueError("Invalid duration")
            await choose(panel, f"{match.group(1)} s")
        self.expected = {
            "model": model,
            "type": job.get("type", "image"),
            "ratio": job.get("ratio", "9:16"),
            "count": 1,
            "duration": job.get("duration"),
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
        return await verify_configuration(self.page, self.expected, self.refs)

    async def submit(self, job):
        await require_auth(self.page)
        # Re-read after upload and prompt editing, immediately before click.
        await verify_configuration(self.page, self.expected, self.refs)
        await (await control(self.page, "settings")).click()
        before = await asset_ids(self.page)
        await (await control(self.page, "submit")).click()
        return await new_asset(self.page, before)

    async def download(self, job, asset):
        await self.ensure_project()
        return await download_asset(self.page, job, asset)


async def download_asset(page, job, asset):
    from .security import ProfileLock

    destination = Path(job["file"])
    with ProfileLock(destination.parent / ("." + destination.name + ".lock")):
        return await _download_asset(page, job, asset)


async def _download_asset(page, job, asset):
    asset = identifier(asset)
    destination = Path(job["file"])
    receipt = destination.with_name(destination.name + ".receipt.json")
    if destination.exists():
        if not receipt.exists():
            raise ValueError("Existing output has no asset receipt")
        metadata = json.loads(receipt.read_text())
        if (
            metadata["asset"] != asset
            or validate(destination, job["type"])["sha256"] != metadata["sha256"]
        ):
            raise ValueError("Existing output/asset integrity mismatch")
        return metadata
    cards = await asset_map(page)
    if asset not in cards:
        raise ValueError("Known asset absent; refusing latest-card fallback")
    card = cards[asset]
    await card.hover()
    direct = await control(card, "download", optional=True)
    if direct is None:
        await (await control(card, "more")).click()
        menu = await unique(page.locator('[role="menu"]:visible'))
        direct = await control(menu, "download")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".flow-download-") as temp:
        async with page.expect_download(timeout=60000) as event:
            await direct.click()
            # Resolution submenu is optional; require exact match if present.
            menus = page.locator('[role="menu"]:visible')
            if await menus.count():
                resolution = job.get("resolution", "720p" if job["type"] == "video" else "1K")
                choice = await unique(
                    menus.get_by_role("menuitem", name=resolution, exact=True), optional=True
                )
                if choice is not None:
                    await choice.click()
        download = await event.value
        if await download.failure():
            raise OSError("Browser download failed")
        source = Path(temp) / "payload"
        await download.save_as(source)
        # Durable receipt precedes atomic publication, so a process dying after
        # publication can recover the exact known asset rather than regenerate.
        metadata = validate(source, job["type"]) | {
            "asset": asset,
            "file": str(destination.resolve()),
        }
        atomic_json(receipt, metadata)
        published = publish(source, destination, asset, job["type"])
        if published != metadata:
            raise ValueError("Publication integrity changed")
        return metadata
