"""Bounded exact-asset recovery, real Runner with offline media only."""

import json

import pytest
from PIL import Image

import flow
from flow_provider.batch import Runner
from flow_provider.media import atomic_json, publish

ASSET = "6ccbc008-b60f-4611-9dff-665377e09ba5"


class DownloadOnly:
    def __init__(self, root):
        self.root, self.assets = root, []

    async def configure(self, job):
        pytest.fail("Recovery configured a generation")

    async def submit(self, job):
        pytest.fail("Recovery submitted a generation")

    async def download(self, job, asset):
        self.assets.append(asset)
        source = self.root / "source.png"
        Image.new("RGB", (8, 8)).save(source)
        return publish(source, job["file"], asset, "image")


def seed(tmp_path, **changes):
    jobs = [{"name": "one", "file": str(tmp_path / "one.png")}]
    adapter = DownloadOnly(tmp_path)
    runner = Runner(tmp_path / "report.json", jobs, adapter)
    row = runner.data["jobs"][0]
    row.update(
        state="failed",
        asset=ASSET,
        error="invalid_media_or_identity",
        attempts={"configure": 1, "submit": 1, "download": 1},
        diagnostic={"private": "secret"},
    )
    row.update(changes)
    atomic_json(runner.path, runner.data)
    return runner, jobs, adapter


@pytest.mark.asyncio
@pytest.mark.parametrize("error", ["invalid_media_or_identity", "download_attempts_exhausted"])
async def test_exact_asset_only_and_default_terminal(tmp_path, error):
    original, jobs, adapter = seed(tmp_path, error=error)
    assert await Runner(original.path, jobs, adapter).run() == 1
    runner = Runner(original.path, jobs, adapter, retry_download=ASSET)
    assert await runner.run() == 0
    row = runner.data["jobs"][0]
    assert adapter.assets == [ASSET]
    assert row["attempts"] == {"configure": 1, "submit": 1, "download": 2}
    assert row["download_recoveries"] == [{"error": error, "download_attempts": 1}]
    assert "diagnostic" not in row
    assert runner.fingerprint == original.fingerprint


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes,requested",
    [
        ({}, "wrong-asset"),
        ({"state": "uncertain"}, ASSET),
        ({"attempts": {"submit": 1, "download": 3}}, ASSET),
        ({"attempts": {"submit": True, "download": 1}}, ASSET),
        ({"attempts": {"submit": 0, "download": 1}}, ASSET),
        ({"attempts": {"submit": 1, "download": True}}, ASSET),
        ({"attempts": {"submit": 1, "download": 0}}, ASSET),
        ({"error": "output_integrity"}, ASSET),
        ({"asset": None}, ASSET),
    ],
)
async def test_blocked(tmp_path, changes, requested):
    original, jobs, adapter = seed(tmp_path, **changes)
    before = json.loads(original.path.read_text())["jobs"][0]["attempts"]
    runner = Runner(original.path, jobs, adapter, retry_download=requested)
    assert await runner.run() == 1
    assert adapter.assets == []
    assert runner.data["jobs"][0]["attempts"] == before


@pytest.mark.asyncio
@pytest.mark.parametrize("symlink", [False, True])
async def test_existing_output_blocked(tmp_path, symlink):
    original, jobs, adapter = seed(tmp_path)
    out = tmp_path / "one.png"
    if symlink:
        out.symlink_to(tmp_path / "missing")
    else:
        out.write_bytes(b"existing")
    assert await Runner(original.path, jobs, adapter, retry_download=ASSET).run() == 1
    assert adapter.assets == []


@pytest.mark.parametrize("command", ["image", "video", "batch"])
def test_cli_flag(command):
    argv = (
        [command, "jobs.json"]
        if command == "batch"
        else [command, "--name", "one", "--model", "Model", "--prompt", "p"]
    )
    parser = flow.build_parser()
    assert parser.parse_args(argv).retry_download is None
    assert parser.parse_args(argv + ["--retry-download", ASSET]).retry_download == ASSET


def test_invalid_identifier(tmp_path):
    original, jobs, adapter = seed(tmp_path)
    with pytest.raises(ValueError):
        Runner(original.path, jobs, adapter, retry_download="../bad")


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["image", "video", "batch"])
async def test_cli_passes_flag_outside_fingerprint(tmp_path, monkeypatch, command):
    adapter = DownloadOnly(tmp_path)
    monkeypatch.setattr(flow, "UIAdapter", lambda *args, **kwargs: adapter)

    async def shutdown():
        pass

    monkeypatch.setattr(flow.browser, "shutdown", shutdown)
    # Video uses an image fixture only to prove the blocked exact-asset path;
    # successful decoding is covered by the image and batch cases.
    if command == "batch":
        data = {"project": "one", "jobs": [{"name": "one", "model": "Model"}]}
        jobfile = tmp_path / "jobs.json"
        jobfile.write_text(json.dumps(data))
        argv = [command, str(jobfile)]
    else:
        data = {
            "project": "one",
            "jobs": [
                {
                    "type": command,
                    "name": "one",
                    "model": "Model",
                    "prompt": "p",
                    "ratio": "9:16",
                    "count": 1,
                }
            ],
        }
        argv = [command, "--name", "one", "--model", "Model", "--prompt", "p"]
    directory, jobs = flow.prepare_jobs(data, tmp_path)
    runner = Runner(directory / "batch_report.json", jobs, adapter)
    runner.data["jobs"][0].update(
        state="failed",
        asset=ASSET,
        error="invalid_media_or_identity",
        attempts={"submit": 1, "download": 1},
    )
    atomic_json(runner.path, runner.data)
    argv += ["--out", str(tmp_path), "--retry-download", ASSET]
    result = await flow.execute(flow.build_parser().parse_args(argv))
    assert result == (1 if command == "video" else 0)
    assert adapter.assets == [ASSET]
    assert json.loads(runner.path.read_text())["fingerprint"] == runner.fingerprint
