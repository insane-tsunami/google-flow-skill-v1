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
from flow_provider.media import identifier
from flow_provider.project import FLOW_BASE_URL
from flow_provider.safe_ui import UIAdapter
from flow_provider.security import auth_state

DEFAULT_OUT = Path(__file__).resolve().parent / "outputs"


def prepare_jobs(data, out):
    # Stable fallback; timestamps would silently create a fresh batch on resume.
    directory = Path(out) / identifier(data.get("project", "batch"))
    defaults = data.get("defaults", {})
    jobs, outputs = [], {}
    for index, original in enumerate(data.get("jobs", [])):
        job = dict(original)
        kind = job.setdefault("type", "image")
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
        job["file"] = str((directory / (name + (".png" if kind == "image" else ".mp4"))).resolve())
        dependencies = list(job.get("depends_on", []))
        for key in ("image", "start", "end"):
            if job.get(key):
                reference = job[key]
                if reference in outputs:
                    dependencies.append(reference)
                    job[key] = outputs[reference]
                elif not Path(reference).is_file():
                    raise ValueError("Local reference missing or dependency not earlier in batch")
                else:
                    job[key] = str(Path(reference).resolve())
        if any(d not in outputs for d in dependencies):
            raise ValueError("Dependencies must name earlier jobs")
        job["depends_on"] = sorted(set(dependencies))
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
            response = await page.goto(FLOW_BASE_URL, wait_until="domcontentloaded", timeout=60000)
            if response and response.status >= 400:
                return "network_error"
        except BrowserError:
            return "network_error"
        for _ in range(240 if login else 10):
            state = await auth_state(page)
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
            if k not in ("cmd", "out", "max_attempts") and v is not None
        }
        job["type"] = args.cmd
        data = {"project": args.name, "jobs": [job]}
    directory, jobs = prepare_jobs(data, args.out)
    adapter = UIAdapter(directory / "project.json")
    runner = Runner(directory / "batch_report.json", jobs, adapter, max_attempts=args.max_attempts)
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
        if kind == "image":
            p.add_argument("--image")
        else:
            p.add_argument("--start")
            p.add_argument("--end")
            p.add_argument("--duration")
        p.add_argument("--out", default=str(DEFAULT_OUT))
        p.add_argument("--max-attempts", type=int, default=3)
    p = sub.add_parser("batch", help="Run or resume exact same JSON and output directory")
    p.add_argument("jobfile")
    p.add_argument("--out", default=str(DEFAULT_OUT))
    p.add_argument("--max-attempts", type=int, default=3)
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
        print(
            f"Operation blocked ({type(error).__name__}); review local state and maintenance guide.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
