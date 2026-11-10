#!/usr/bin/env python
"""Google Flow CLI: verified configuration, asset downloads and durable jobs."""

import argparse
import asyncio
import json
from pathlib import Path
import shutil
import sys

from playwright.async_api import Error as BrowserError

from flow_provider import browser, settings
from flow_provider.batch import Runner
from flow_provider.media import identifier, lexical_output
from flow_provider.project import account_index, explicit_project, flow_url, verify_account
from flow_provider.elements import exact_label, seal_references, validate_inputs
from flow_provider.safe_ui import UIAdapter
from flow_provider.security import auth_state

DEFAULT_OUT = Path(__file__).resolve().parent / "outputs"


def prepare_jobs(data, out):
    # Stable fallback; timestamps would silently create a fresh batch on resume.
    directory = Path(out) / identifier(data.get("project", "batch"))
    defaults = data.get("defaults", {})
    target_keys = [key for key in ("project_url", "project_id") if key in data]
    if len(target_keys) > 1:
        raise ValueError("Choose project_url or project_id")
    target = data[target_keys[0]] if target_keys else None
    project_id = explicit_project(target, account_index()) if target_keys else None
    title = data.get("project_title")
    if title is not None:
        exact_label(title)
        if not project_id:
            raise ValueError("Title verifies an explicit project; never selects one")
    jobs, outputs = [], {}
    for index, original in enumerate(data.get("jobs", [])):
        job = dict(original)
        if any(
            key in job for key in ("project_id", "project_url", "project_title", "project_scope")
        ):
            raise ValueError("Existing project selection belongs at batch top level")
        if isinstance(job.get("images"), list):
            job["images"] = list(job["images"])
        kind = job.setdefault("type", "image")
        validate_inputs(job)
        if project_id:
            job["project_scope"] = {
                "project": project_id,
                "account_index": account_index(),
                "title": title,
            }
        name = job.setdefault("name", f"{kind}_{index + 1:02d}")
        identifier(name)
        if kind not in ("image", "video") or job.get("count", 1) != 1:
            raise ValueError("Only image/video jobs with count=1 are supported")
        if name in outputs:
            raise ValueError("Duplicate job name")
        model = job.get("model", defaults.get(f"{kind}_model"))
        if not isinstance(model, str) or not model.strip():
            raise ValueError(
                "Explicit model required (job.model or defaults.image_model/video_model)"
            )
        job["model"] = model
        job.setdefault("ratio", defaults.get("ratio", "9:16"))
        job.setdefault("count", 1)
        if job["ratio"] not in ("9:16", "16:9", "1:1", "4:3", "3:4"):
            raise ValueError("Unsupported ratio")
        if kind == "video" and not job.get("duration") and defaults.get("video_duration"):
            job["duration"] = defaults["video_duration"]
        job["file"] = str(
            lexical_output(directory / (name + (".png" if kind == "image" else ".mp4")))
        )
        dependencies = list(job.get("depends_on", []))
        refs = [(key, job[key]) for key in ("image", "start", "end") if job.get(key)]
        refs += [(index, value) for index, value in enumerate(job.get("images", []))]
        for key, reference in refs:
            if reference:
                # Explicit output paths carry the same dependency as job-name
                # references. Never exempt an input from hashing without also
                # requiring its producer's verified completion.
                if reference not in outputs:
                    resolved = str(Path(reference).resolve())
                    producers = [n for n, output in outputs.items() if output == resolved]
                    if producers:
                        reference = producers[0]
                if reference in outputs:
                    dependencies.append(reference)
                    if isinstance(key, int):
                        job["images"][key] = outputs[reference]
                    else:
                        job[key] = outputs[reference]
                elif not Path(reference).is_file():
                    raise ValueError("Local reference missing or dependency not earlier in batch")
                else:
                    if isinstance(key, int):
                        job["images"][key] = str(Path(reference).resolve())
                    else:
                        job[key] = str(Path(reference).resolve())
        if any(d not in outputs for d in dependencies):
            raise ValueError("Dependencies must name earlier jobs")
        job["depends_on"] = sorted(set(dependencies))
        # Earlier generated dependencies are fingerprinted by their jobs; hash
        # local inputs now, then capture dependency bytes immediately before use.
        local = dict(job)
        local["images"] = [p for p in job.get("images", []) if p not in outputs.values()]
        for key in ("image", "start", "end"):
            if local.get(key) in outputs.values():
                local.pop(key)
        seal_references(local)
        if local.get("reference_hashes"):
            job["reference_hashes"] = local["reference_hashes"]
        outputs[name] = job["file"]
        jobs.append(job)
    if not jobs:
        raise ValueError("No jobs requested")
    return directory, jobs


async def check_session(login=False):
    profile = Path(settings.FLOW_CHROME_PROFILE)
    if not login and not profile.exists():
        return "profile_missing"
    await browser.startup()
    try:
        page = await browser.get_page()
        try:
            response = await page.goto(flow_url(), wait_until="domcontentloaded", timeout=60000)
            if response and response.status >= 400:
                return "network_error"
        except BrowserError:
            return "network_error"
        for _ in range(240 if login else 10):
            state = await auth_state(page)
            if state == "authenticated":
                verify_account(page.url)
            if state == "authenticated" or (state == "login_required" and not login):
                return state
            await asyncio.sleep(1)
        return await auth_state(page)
    finally:
        await browser.shutdown()


async def execute(args):
    if args.cmd in ("status", "login"):
        if args.cmd == "login":
            if settings.FLOW_HEADLESS:
                raise ValueError("Human login requires FLOW_HEADLESS=false")
            print(
                "Complete human login in the owned Chrome window; no credentials are collected.",
                file=sys.stderr,
            )
        state = await check_session(args.cmd == "login")
        print(json.dumps({"authentication": state}))
        return 0 if state == "authenticated" else 1
    if args.cmd == "clean":
        target = Path(args.out) / identifier(args.project)
        if target.exists():
            shutil.rmtree(target)
        return 0
    if args.cmd == "batch":
        data = json.loads(Path(args.jobfile).read_text(encoding="utf-8"))
    else:
        job = {
            k: v
            for k, v in vars(args).items()
            if k
            not in (
                "cmd",
                "out",
                "max_attempts",
                "direct_mode",
                "max_credits",
                "retry_configuration",
                "retry_download",
                "project_id",
                "project_url",
                "project_title",
            )
            and v is not None
        }
        job["type"] = args.cmd
        data = {"project": args.name, "jobs": [job]}
    for key in ("project_id", "project_url", "project_title"):
        value = getattr(args, key, None)
        if value is not None:
            if key in data and data[key] != value:
                raise ValueError("CLI and batch project conflict")
            data[key] = value
    directory, jobs = prepare_jobs(data, args.out)
    adapter = UIAdapter(
        directory / "project.json",
        direct_mode=args.direct_mode,
        max_credits=args.max_credits,
        project_scope=jobs[0].get("project_scope"),
    )
    runner = Runner(
        directory / "batch_report.json",
        jobs,
        adapter,
        max_attempts=args.max_attempts,
        retry_configuration=args.retry_configuration,
        retry_download=args.retry_download,
    )
    try:
        result = await runner.run()
        print(
            json.dumps(
                {
                    "report": str(runner.path),
                    "states": {row["name"]: row["state"] for row in runner.data["jobs"]},
                }
            )
        )
        return result
    finally:
        await browser.shutdown()


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="Non-generating live authentication check")
    sub.add_parser("login", help="Human login with exclusive profile ownership")
    for kind in ("image", "video"):
        p = sub.add_parser(kind)
        p.add_argument("--prompt", required=True)
        p.add_argument("--model", required=True, help="Exact model label; no silent fallback")
        p.add_argument(
            "--name", required=True, help="Stable job/output identifier (letters, digits, _, -)"
        )
        p.add_argument("--ratio", default="9:16")
        p.add_argument("--count", type=int, default=1)
        p.add_argument(
            "--image",
            dest="images",
            action="append",
            help="Local image reference; repeat for multiple Elements",
        )
        p.add_argument(
            "--mode",
            choices=("elements", "frames"),
            help="Explicit reference mode (required for video Elements)",
        )
        p.add_argument(
            "--character",
            help="Exact unique saved character name; verifies picker/detail/attached association",
        )
        p.add_argument(
            "--character-id",
            help="Unavailable in observed UI (no saved ID exposed); use --character",
        )
        p.add_argument(
            "--voice", help="Assert full saved associated voice name; video only, no replacement"
        )
        if kind == "video":
            p.add_argument("--start")
            p.add_argument("--end")
            p.add_argument("--duration")
        p.add_argument("--out", default=str(DEFAULT_OUT))
        p.add_argument("--max-attempts", type=int, default=3)
    p = sub.add_parser("batch", help="Run or resume exact same JSON and output directory")
    p.add_argument("jobfile")
    p.add_argument("--out", default=str(DEFAULT_OUT))
    p.add_argument("--max-attempts", type=int, default=3)
    for command in ("image", "video", "batch"):
        target = sub.choices[command].add_mutually_exclusive_group()
        target.add_argument(
            "--project-id", help="Existing project ID; requires explicit FLOW_ACCOUNT_INDEX"
        )
        target.add_argument("--project-url", help="Canonical account-scoped existing project URL")
        sub.choices[command].add_argument(
            "--project-title", help="Optional exact title verification; never project lookup"
        )
        sub.choices[command].add_argument(
            "--retry-download",
            metavar="ASSET_ID",
            default=None,
            help="Retry a failed download of this exact known asset within the existing budget",
        )
        sub.choices[command].add_argument(
            "--retry-configuration",
            action="store_true",
            help="Authorize retry of a known failed configuration before any submit; preserves attempts",
        )
        sub.choices[command].add_argument(
            "--direct-mode",
            action="store_true",
            help="Authorize exact Agent to Direct button transition",
        )
        sub.choices[command].add_argument(
            "--max-credits",
            type=float,
            help="Approve maximum visible credits per generation; required for submit",
        )
    p = sub.add_parser("clean", help="Explicitly delete one local project only")
    p.add_argument("project")
    p.add_argument("--out", default=str(DEFAULT_OUT))
    return parser


def main():
    args = build_parser().parse_args()
    try:
        return asyncio.run(execute(args))
    except KeyboardInterrupt:
        print(
            "Interrupted; resume the same command. Uncertain jobs are never re-submitted.",
            file=sys.stderr,
        )
        return 130
    except Exception as error:
        # Browser exceptions can contain signed URLs and DOM; never print them.
        from flow_provider.safe_ui import ConfigurationError

        if isinstance(error, ConfigurationError):
            print(f"Operation blocked: {error.code}", file=sys.stderr)
            return 1
        print(
            f"Operation blocked ({type(error).__name__}); review local state and maintenance guide.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
