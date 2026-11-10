import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_safety_modules_exist():
    for name in ("selectors", "security", "media", "batch", "safe_ui"):
        assert (ROOT / "flow_provider" / f"{name}.py").exists(), name


def test_profile_lock(tmp_path):
    from flow_provider.security import ProfileLock

    profile = tmp_path / "profile"
    with ProfileLock(profile):
        lock = profile / "SingletonLock"
        lock.symlink_to("external-chrome-123")
        code = "from flow_provider.security import ProfileLock; import sys; ProfileLock(sys.argv[1]).acquire()"
        result = subprocess.run([sys.executable, "-c", code, str(profile)], capture_output=True)
        assert result.returncode != 0
        assert lock.is_symlink()
    with ProfileLock(profile):
        assert lock.is_symlink()
    assert profile.stat().st_mode & 0o077 == 0


def test_media_validation_atomic(tmp_path):
    from flow_provider.media import publish, validate

    src = tmp_path / "source.png"
    Image.new("RGB", (8, 8), "red").save(src)
    out = tmp_path / "out.png"
    meta = publish(src, out, "asset-1", "image")
    assert meta["size"] > 0 and len(meta["sha256"]) == 64
    assert validate(out, "image")["format"] == "PNG"
    with pytest.raises(FileExistsError):
        publish(src, out, "asset-2", "image")
    for data in (b"", b"<html>login</html>", src.read_bytes()[:30]):
        src.write_bytes(data)
        with pytest.raises(ValueError):
            publish(src, tmp_path / "bad.png", "asset-1", "image")
        assert not (tmp_path / "bad.png").exists()
    assert not list(tmp_path.glob("*.part"))


def test_real_video_validation(tmp_path):
    from flow_provider.media import validate

    target = tmp_path / "clip.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=32x32:d=0.3",
            "-an",
            "-c:v",
            "mpeg4",
            str(target),
        ],
        check=True,
    )
    assert validate(target, "video")["duration"] > 0
    with pytest.raises(ValueError):
        validate(target, "image")
    target.write_bytes(target.read_bytes()[:60])
    with pytest.raises(ValueError):
        validate(target, "video")


class FakeAdapter:
    def __init__(self, root, crash=None):
        self.root, self.crash, self.submits, self.downloads = root, crash, 0, 0

    async def configure(self, job):
        return {"model": job.get("model", "Nano Banana 2.1"), "ratio": "9:16", "count": 1}

    async def submit(self, job):
        self.submits += 1
        if self.crash == "submit":
            raise KeyboardInterrupt()
        return "asset-1"

    async def download(self, job, asset):
        from flow_provider.media import publish

        self.downloads += 1
        if self.crash == "download":
            raise KeyboardInterrupt()
        src = self.root / "source.png"
        Image.new("RGB", (8, 8), "red").save(src)
        return publish(src, Path(job["file"]), asset, "image")


@pytest.mark.asyncio
async def test_resume_never_resubmits_uncertain(tmp_path):
    from flow_provider.batch import Runner

    jobs = [
        {"name": "one", "type": "image", "prompt": "PRIVATE", "file": str(tmp_path / "one.png")}
    ]
    a = FakeAdapter(tmp_path, "submit")
    with pytest.raises(KeyboardInterrupt):
        await Runner(tmp_path / "manifest.json", jobs, a).run()
    for _ in range(2):
        assert await Runner(tmp_path / "manifest.json", jobs, a).run() == 1
    assert a.submits == 1
    text = (tmp_path / "manifest.json").read_text()
    assert "PRIVATE" not in text and "uncertain" in text


@pytest.mark.asyncio
async def test_resume_known_asset_without_generation(tmp_path):
    from flow_provider.batch import Runner

    jobs = [{"name": "one", "type": "image", "file": str(tmp_path / "one.png")}]
    a = FakeAdapter(tmp_path, "download")
    with pytest.raises(KeyboardInterrupt):
        await Runner(tmp_path / "manifest.json", jobs, a).run()
    a.crash = None
    assert await Runner(tmp_path / "manifest.json", jobs, a).run() == 0
    assert await Runner(tmp_path / "manifest.json", jobs, a).run() == 0
    assert a.submits == 1 and a.downloads == 2
    (tmp_path / "one.png").unlink()
    assert await Runner(tmp_path / "manifest.json", jobs, a).run() == 0
    assert a.submits == 1


@pytest.mark.asyncio
async def test_retry_limit_and_dependency(tmp_path):
    from flow_provider.batch import Runner

    class Broken(FakeAdapter):
        async def download(self, job, asset):
            self.downloads += 1
            raise OSError("https://secret/?token=private")

    jobs = [
        {"name": "one", "type": "image", "file": str(tmp_path / "one.png")},
        {"name": "two", "type": "image", "depends_on": ["one"], "file": str(tmp_path / "two.png")},
    ]
    a = Broken(tmp_path)
    runner = Runner(tmp_path / "manifest.json", jobs, a, max_attempts=2, backoff=0)
    assert await runner.run() == 1
    assert await Runner(tmp_path / "manifest.json", jobs, a, max_attempts=2, backoff=0).run() == 1
    assert a.submits == 1 and a.downloads == 2
    text = (tmp_path / "manifest.json").read_text()
    assert "token" not in text and "https" not in text


def test_incomplete_checkpoint_fails(tmp_path):
    from flow_provider.batch import Runner

    p = tmp_path / "manifest.json"
    p.write_text("{")
    with pytest.raises(ValueError):
        Runner(p, [], FakeAdapter(tmp_path))
