"""Observed Flow service records. URLs/prompts exist only in volatile memory.

This module never requests an endpoint. It consumes ordinary browser responses;
unknown layouts are ignored rather than guessed. Numeric image model identifiers
are evidence, never mappings to a named model.
"""

from dataclasses import dataclass
import asyncio
import hashlib
import json
import re
from urllib.parse import urlsplit, parse_qs

from .media import identifier


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def canonical_thumbnail(url, account=None):
    if not isinstance(url, str) or any(ord(c) <= 32 or ord(c) == 127 for c in url):
        raise ValueError("Invalid thumbnail")
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.netloc not in {"lh3.googleusercontent.com", "flow.google.com"}
        or parts.fragment
        or not parts.path.startswith("/")
        or parts.path == "/"
        or "%" in parts.path
        or "\\" in parts.path
        or "//" in parts.path
        or any(p in {".", ".."} for p in parts.path.split("/"))
    ):
        raise ValueError("Unknown thumbnail contract")
    if parts.query and (
        account is None
        or parse_qs(parts.query, strict_parsing=True) != {"authuser": [str(account)]}
    ):
        raise ValueError("Thumbnail account query mismatch")
    path = re.sub(r"=s(?:512|1600)-rw$", "", parts.path)
    if "=" in path:
        raise ValueError("Unknown thumbnail transformation")
    return path


@dataclass(frozen=True)
class ServiceRecord:
    asset: str
    project: str
    kind: str
    seconds: int
    nanos: int
    prompt: str
    thumbnail: str
    model: str | int
    request_metadata: object = None
    group_id: str | None = None

    def proof(self):
        return {
            "asset_hash": digest(self.asset),
            "group_hash": digest(self.group_id),
            "project": self.project,
            "kind": self.kind,
            "timestamp": [self.seconds, self.nanos],
            "prompt_hash": digest(self.prompt),
            "prompt_sha256": hashlib.sha256(self.prompt.encode()).hexdigest(),
            "thumbnail_hash": digest(self.thumbnail),
            "model_hash": digest(self.model),
            "request_metadata_hash": digest(self.request_metadata),
        }


def stable_record_proof(proof):
    """Ownership metadata is durable; a signed thumbnail location is not."""
    return {key: value for key, value in proof.items() if key != "thumbnail_hash"}


def _record(v, project):
    try:
        if not isinstance(v, list) or len(v) < 6 or v[1] != project:
            return None
        asset = identifier(v[0])
        q = v[5]
        sec, nano = q[0]
        if type(sec) is not int or type(nano) is not int or sec < 0 or not 0 <= nano < 10**9:
            return None
        thumbnail = canonical_thumbnail(q[5])
        # Only the two explicitly observed layouts are supported.
        if len(v) > 6 and isinstance(v[6], list) and v[6] and isinstance(v[6][0], list):
            model = v[6][0][8]
            if type(model) is not int or type(q[6][4]) is not int or q[6][4] != 1:
                return None
            kind, prompt = "image", q[6][2][0][0]
        else:
            kind, prompt, model = "video", q[1], q[6][1][0][0]
            if not isinstance(model, str) or not model:
                return None
        if not isinstance(prompt, str) or not prompt:
            return None
        return ServiceRecord(
            asset,
            project,
            kind,
            sec,
            nano,
            prompt,
            thumbnail,
            model,
            q[6][3] if len(q[6]) > 3 else None,
            identifier(v[2]) if isinstance(v[2], str) else None,
        )
    except (IndexError, TypeError, ValueError):
        return None


def parse_records(body, project):
    """Decode XSSI/decimal length framing and recursively embedded JSON.

    Limits apply before recursion and malformed framing rejects the whole body.
    Conflicting versions of one stable ID reject the response.
    """
    identifier(project)
    if not isinstance(body, str) or len(body) > 8_000_000:
        raise ValueError("Service response too large")
    body = body.removeprefix(")]}'").lstrip()
    decoder = json.JSONDecoder()
    roots = []
    while body:
        match = re.match(r"^(\d+)\n", body)
        length = int(match[1]) if match else None
        if match:
            body = body[match.end() :]
        try:
            value, end = decoder.raw_decode(body)
        except ValueError:
            raise ValueError("Unknown service framing") from None
        # Observed batchexecute lengths count UTF-16 units including the
        # delimiter following the length and the final JSON newline, not UTF-8.
        if length is not None and (
            length != len(body[:end].encode("utf-16-le")) // 2 + 2
            or not body[end:].startswith("\n")
        ):
            raise ValueError("Invalid service frame length")
        roots.append(value)
        body = body[end:].lstrip()
    records, visited = {}, 0

    def walk(value, depth=0):
        nonlocal visited
        visited += 1
        if depth > 32 or visited > 100000:
            raise ValueError("Service nesting limit")
        if isinstance(value, str) and value.startswith(("[", "{")):
            try:
                embedded = json.loads(value)
            except ValueError:
                return
            walk(embedded, depth + 1)
        elif isinstance(value, list):
            row = _record(value, project)
            if row is not None:
                if row.asset in records and records[row.asset] != row:
                    raise ValueError("Conflicting service records")
                records[row.asset] = row
                # An owning record's prompt/metadata are user-authored leaves,
                # never another RPC envelope or authoritative owning record.
                return
            for child in value:
                walk(child, depth + 1)
        elif isinstance(value, dict):
            for child in value.values():
                walk(child, depth + 1)

    for root in roots:
        walk(root)
    return list(records.values())


def select_record(records, *, baseline, project, kind, prompt, start_ns, end_ns):
    """Candidate selection only; scoped detail/parameter proof is still required."""
    matches = [
        r
        for r in records
        if r.asset not in baseline
        and r.project == project
        and r.kind == kind
        and r.prompt == prompt
        and start_ns <= r.seconds * 10**9 + r.nanos <= end_ns
    ]
    if len(matches) != 1:
        raise ValueError("Missing or ambiguous owning service record")
    return matches[0]


def match_physical_tile(records, source_urls, account=None):
    """Return a unique index only when the complete canonical paths agree.

    Inputs are in-memory thumbnail src values from physical kind-filtered tiles.
    Unknown source URL contracts fail closed, even if another URL would match.
    This function does not authorize download or replace scoped detail proof.
    """
    if len(records) != 1:
        raise ValueError("Unique owning service record required")
    matches = []
    for index, urls in enumerate(source_urls):
        paths = {canonical_thumbnail(url, account) for url in urls}
        if records[0].thumbnail in paths:
            matches.append(index)
    if len(matches) != 1:
        raise ValueError("Missing or ambiguous physical service tile")
    return matches[0]


class ServiceObserver:
    """Passive, account-scoped response journal; never initiates requests.

    A recognized owning record is required to establish the baseline. In
    particular an empty/unknown frame is not evidence of an empty project.
    """

    def __init__(self, page, account):
        self.page, self.account = page, account
        self.project = None
        self.records = {}
        self.frames = 0
        self.tasks = set()
        self.error = False
        self.armed_prompt = None
        self.linked = {}
        self.requests = set()
        page.on("request", self.capture_request)
        page.on("response", self.receive)

    def capture_request(self, request):
        if self.armed_prompt is not None:
            self.requests.add(request)

    def arm(self, prompt, contract=None, configuration=None):
        if not isinstance(contract, GenerationInvocationContract) or not isinstance(
            configuration, dict
        ):
            raise ValueError("Observed generation invocation contract unavailable")
        self.contract, self.configuration = contract, configuration
        self.requests.clear()
        self.linked.clear()
        self.armed_prompt = prompt

    def scope(self, project):
        if project != self.project:
            self.project = identifier(project)
            self.records = {}
            self.frames = 0
            self.error = False

    def receive(self, response):
        import asyncio

        task = asyncio.create_task(self.consume(response, self.project))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def consume(self, response, project):
        if project is None or self.account is None:
            return
        parts = urlsplit(response.url)
        expected = f"/u/{self.account}/_/AiSandboxAngularFrontend/data/batchexecute"
        if parts.scheme != "https" or parts.netloc != "flow.google.com" or parts.path != expected:
            return
        if response.status != 200:
            return
        try:
            headers = await asyncio.wait_for(response.all_headers(), timeout=5)
            if headers.get("content-type", "").split(";")[0].strip() != "application/json":
                return
            body = await asyncio.wait_for(response.text(), timeout=5)
            rows = parse_records(body, project)
            request = response.request
            post = request.post_data if request.method == "POST" else None
            if post and self.armed_prompt and request in self.requests:
                linked = linked_response_records(
                    post,
                    body,
                    project,
                    self.armed_prompt,
                    contract=self.contract,
                    configuration=self.configuration,
                )
                for row in linked:
                    proof = {
                        "post_body_hash": hashlib.sha256(post.encode()).hexdigest(),
                        "response_body_hash": hashlib.sha256(body.encode()).hexdigest(),
                        "record": row.proof(),
                    }
                    previous = self.linked.get(row.asset)
                    if previous and previous != proof:
                        raise ValueError("Conflicting invocation linkage")
                    self.linked[row.asset] = proof
            if project != self.project:
                return
            for row in rows:
                self.records[row.asset] = row
            if rows:
                self.frames += 1
        except (ValueError, TypeError):
            self.error = True
        except Exception:
            self.error = True

    async def flush(self, timeout=5):
        # Snapshot once: unrelated continuous traffic cannot extend the deadline.
        pending = list(self.tasks)
        if pending:
            try:
                await asyncio.wait_for(asyncio.gather(*pending), timeout=timeout)
            except asyncio.TimeoutError:
                self.error = True
                raise TimeoutError("Observed service response deadline exceeded") from None
        if self.error:
            raise ValueError("Invalid observed service response")

    async def baseline(self, timeout=0):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + (timeout or 5)
        previous, stable_since = None, loop.time()
        while True:
            await self.flush(timeout=max(0.001, deadline - loop.time()))
            now = loop.time()
            current = frozenset(self.records)
            if current != previous:
                previous, stable_since = current, now
            if self.frames and (not timeout or now - stable_since >= 0.25):
                return set(current)
            if now >= deadline:
                raise ValueError("Known owning project response required before submit")
            if not timeout:
                raise ValueError("Known owning project response required before submit")
            await asyncio.sleep(min(0.05, deadline - now))

    def known(self, asset_hash):
        matches = [r for r in self.records.values() if digest(r.asset) == asset_hash]
        if len(matches) != 1:
            raise ValueError("Known service record unavailable or ambiguous")
        return matches[0]


@dataclass(frozen=True)
class DetailContract:
    """Explicit observed selector contract, installed by provider code only.

    No default selectors or numeric model/ratio mappings are inferred. The
    parameter verifier must bind *all* sealed inputs to the service record,
    including reference IDs, ratio, mode, duration, model and character/voice.
    Returning anything other than True rejects the result.
    """

    panel: str
    open_control: str
    fields: dict
    verify_parameters: object

    async def verify(self, page, card, record, job, references):
        if self.verify_parameters(record, job, tuple(references)) is not True:
            raise ValueError("Service request parameters not bound")
        opener = card.locator(self.open_control)
        if await opener.count() != 1:
            raise ValueError("Unique scoped detail opener required")
        await opener.click()
        panel = page.locator(self.panel)
        await panel.wait_for(state="visible", timeout=5000)
        if await panel.count() != 1 or not await panel.is_visible():
            raise ValueError("Unique visible scoped service detail required")
        expected = {"model": job["model"], "ratio": job["ratio"], "prompt": job["prompt"]}
        for key in ("duration", "mode", "character", "voice"):
            if job.get(key) is not None:
                expected[key] = job[key]
        if set(expected) - set(self.fields):
            raise ValueError("Incomplete scoped detail contract")
        for key, value in expected.items():
            field = panel.locator(self.fields[key])
            if await field.count() != 1 or await field.inner_text() != str(value):
                raise ValueError("Scoped service detail mismatch")


@dataclass(frozen=True)
class GenerationInvocationContract:
    """Provider-installed wire contract, never supplied by a CLI flag.

    No live generation RPC contract has yet been captured without a new paid
    request. The production default is intentionally absent. Synthetic offline
    fixtures install their own explicitly labeled contract, not a guessed RPC.
    """

    rpc: str
    prompt_path: tuple
    configuration_path: tuple

    def accepts(self, invocation, prompt, configuration):
        try:
            if invocation[0] != self.rpc or not isinstance(invocation[1], str):
                return False
            payload = json.loads(invocation[1])

            def at(path):
                value = payload
                for key in path:
                    value = value[key]
                return value

            return at(self.prompt_path) == prompt and at(self.configuration_path) == configuration
        except (ValueError, TypeError, KeyError, IndexError):
            return False


def linked_response_records(post, body, project, prompt, *, contract=None, configuration=None):
    """Only a single exact-prompt RPC and its matching wrb.fr frame may own output.

    The transport RPC identifier is observed envelope structure, not an invented
    generation parameter. Other response frames, including project lists, cannot
    satisfy the link. Raw POST bodies remain in memory only.
    """
    if not isinstance(contract, GenerationInvocationContract) or not isinstance(
        configuration, dict
    ):
        return []
    if len(post) > 8_000_000:
        raise ValueError("Request too large")
    forms = parse_qs(post, strict_parsing=True)
    if len(forms.get("f.req", [])) != 1:
        return []
    envelope = json.loads(forms["f.req"][0])
    if not isinstance(envelope, list) or len(envelope) != 1:
        return []
    invocations = envelope[0]
    if not isinstance(invocations, list):
        return []
    matches = [
        v
        for v in invocations
        if isinstance(v, list)
        and len(v) >= 2
        and isinstance(v[0], str)
        and contract.accepts(v, prompt, configuration)
    ]
    # A multi invocation request cannot prove which invocation created a record.
    if len(matches) != 1 or len(invocations) != 1:
        return []
    rpc = matches[0][0]
    text = body.removeprefix(")]}'").lstrip()
    decoder = json.JSONDecoder()
    result = []
    while text:
        match = re.match(r"^(\d+)\n", text)
        if match:
            text = text[match.end() :]
        root, end = decoder.raw_decode(text)
        if match and (
            int(match[1]) != len(text[:end].encode("utf-16-le")) // 2 + 2
            or not text[end:].startswith("\n")
        ):
            raise ValueError("Invalid frame length")
        if isinstance(root, list):
            for frame in root:
                if (
                    isinstance(frame, list)
                    and len(frame) >= 3
                    and frame[0] == "wrb.fr"
                    and frame[1] == rpc
                ):
                    result.extend(parse_records(json.dumps(frame[2]), project))
        text = text[end:].lstrip()
    return result


def selected_image_source(url, record, account):
    """Bind the observed signed full image to its owning stable service ID.

    Thumbnail hosts and full-content URLs are separate contracts. Signatures
    stay in memory, are never followed outside the browser, and cannot alter ID.
    """
    if not isinstance(url, str) or any(ord(c) <= 32 or ord(c) == 127 for c in url):
        raise ValueError("Invalid selected source")
    parts = urlsplit(url)
    if parts.netloc == "flow-content.google":
        query = parse_qs(parts.query, strict_parsing=True)
        if (
            parts.scheme != "https"
            or parts.fragment
            or not re.fullmatch(
                r"/image/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
                parts.path,
            )
            or set(query) != {"Expires", "KeyName", "Signature"}
            or any(len(values) != 1 or not values[0] for values in query.values())
        ):
            raise ValueError("Unknown selected content contract")
        return parts.path == "/image/" + record.asset
    return canonical_thumbnail(url, account) == record.thumbnail


class ObservedMediaDetail:
    """Scoped media detail observed in the supplied sanitized live contracts.

    Effective configuration is independently checked before submit. The owning
    record must additionally come from that submit's exact response invocation.
    No numeric model or parameter slots are mapped here.
    """

    def __init__(self, account=None):
        self.account = account

    async def verify(self, page, card, record, job, references):
        import asyncio

        paths = set()
        if card is not None:
            output = card.locator(f"flow-{record.kind}-tile img")
            paths = {
                canonical_thumbnail(await img.get_attribute("src"), self.account)
                for img in await output.all()
            }
        history_required = record.kind == "video" or record.thumbnail not in paths
        if card is not None:
            await card.click()
        editor = "flow-image-editor" if record.kind == "image" else "flow-scene-builder"
        await page.locator(editor + ":visible").wait_for(state="visible", timeout=5000)
        # Group editor selection is separate from the generation action.
        tiles = page.locator(f"flow-editor-history-step-{record.kind} .history-step:visible")
        deadline = asyncio.get_running_loop().time() + 5
        while history_required and not await tiles.count():
            if asyncio.get_running_loop().time() >= deadline:
                raise ValueError("Required scoped history unavailable")
            await asyncio.sleep(0.05)
        if await tiles.count():
            matches = []
            for step in await tiles.all():
                urls = [
                    await img.get_attribute("src")
                    for img in await step.locator(
                        f"flow-tile-container flow-{record.kind}-tile img:not(flow-ingredient-chip *, flow-image-ingredient-chip *, flow-character-ingredient-chip *)"
                    ).all()
                ]
                if record.thumbnail in {canonical_thumbnail(url, self.account) for url in urls}:
                    matches.append(step)
            if len(matches) != 1:
                raise ValueError("Exact history target unavailable or ambiguous")
            step = matches[0]
            prompt = step.locator("flow-expandable-prompt .prompt-text span.text-part")
            if await prompt.count() != 1 or await prompt.inner_text() != job["prompt"]:
                raise ValueError("History prompt mismatch")
            if record.kind == "image":
                current = page.locator(
                    "flow-image-editor .image-container > img.read-only-image, flow-image-editor > img.image"
                )
                already_selected = [
                    image
                    for image in await current.all()
                    if await image.is_visible()
                    and selected_image_source(
                        await image.get_attribute("src"), record, self.account
                    )
                ]
                if len(already_selected) > 1:
                    raise ValueError("Ambiguous selected image")
                if not already_selected:
                    await step.locator(
                        f"flow-tile-container:has(flow-{record.kind}-tile):not(flow-ingredient-chip *, flow-image-ingredient-chip *, flow-character-ingredient-chip *)"
                    ).click()
        elif record.kind == "video":
            raise ValueError("Exact scoped video history required")
        if record.kind == "video":
            # No independent named model label exists in the observed scene
            # builder. Submit/resume must already carry exact invocation proof
            # plus the sealed pre-click model/configuration and record model.
            if await page.locator("flow-scene-builder:visible").count() != 1:
                raise ValueError("Observed video scene builder required")
            return step.locator(
                "flow-tile-container:has(flow-video-tile):not(flow-ingredient-chip *, flow-image-ingredient-chip *, flow-character-ingredient-chip *)"
            )
        main = page.locator(
            "flow-image-editor :is(img.image, .image-container > img.read-only-image)"
            ":not(flow-editor-history-panel *, flow-ingredient-chip *, flow-image-ingredient-chip *, flow-character-ingredient-chip *)"
        )
        deadline = asyncio.get_running_loop().time() + 5
        while True:
            selected = [
                img
                for img in await main.all()
                if await img.is_visible()
                and selected_image_source(await img.get_attribute("src"), record, self.account)
            ]
            if len(selected) == 1:
                break
            if len(selected) > 1 or asyncio.get_running_loop().time() >= deadline:
                raise ValueError("Selected main image path not confirmed")
            await asyncio.sleep(0.05)
        opener = page.locator(
            'flow-editor-header button[aria-label="Mostrar informações do recurso"]'
        )
        panel = page.locator("aside.info-panel-overlay flow-info-panel")
        if await panel.count() == 0 or (await panel.count() == 1 and not await panel.is_visible()):
            if await opener.count() != 1:
                raise ValueError("Observed image info action unavailable")
            await opener.click()
        await panel.wait_for(state="visible", timeout=5000)
        if await panel.count() != 1 or not await panel.is_visible():
            raise ValueError("Unique image detail required")
        prompt = panel.locator("flow-expandable-prompt .prompt-text span.text-part")
        if await prompt.count() != 1 or await prompt.inner_text() != job["prompt"]:
            raise ValueError("Detail prompt mismatch")
        rows = panel.locator(":scope > .container > .metadata > .metadata-row")
        labels = [(await row.inner_text()).replace("🍌", "").strip() for row in await rows.all()]
        if labels.count(job["model"]) != 1:
            raise ValueError("Independent named model mismatch")
