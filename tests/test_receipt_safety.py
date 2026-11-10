import json
from pathlib import Path
import sys

from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_safety import FakeAdapter


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["asset", "file", "sha256", "json"])
async def test_invalid_receipt_never_recovers_or_regenerates(tmp_path, mutation):
    from flow_provider.batch import Runner
    from flow_provider.media import atomic_json, publish

    class Published(FakeAdapter):
        async def download(self, job, asset):
            self.downloads += 1
            source = tmp_path / "source.png"
            Image.new("RGB", (8, 8)).save(source)
            receipt = publish(source, job["file"], asset, "image")
            atomic_json(job["file"] + ".receipt.json", receipt)
            raise KeyboardInterrupt()

    jobs = [{"name": "one", "type": "image", "file": str(tmp_path / "one.png")}]
    a = Published(tmp_path)
    with pytest.raises(KeyboardInterrupt):
        await Runner(tmp_path / "manifest.json", jobs, a, max_attempts=1).run()
    path = tmp_path / "one.png.receipt.json"
    if mutation == "json":
        path.write_text("{")
    else:
        data = json.loads(path.read_text())
        data[mutation] = {
            "asset": "wrong-asset",
            "file": str(tmp_path / "other.png"),
            "sha256": "0" * 64,
        }[mutation]
        path.write_text(json.dumps(data))
    assert await Runner(tmp_path / "manifest.json", jobs, a, max_attempts=1).run() == 1
    assert a.submits == 1 and a.downloads == 1


@pytest.mark.asyncio
async def test_dangling_output_symlink_blocks_before_submit(tmp_path):
    from flow_provider.batch import Runner

    target = tmp_path / "one.png"
    target.symlink_to(tmp_path / "missing")
    a = FakeAdapter(tmp_path)
    jobs = [{"name": "one", "type": "image", "file": str(target)}]
    assert await Runner(tmp_path / "manifest.json", jobs, a, backoff=0).run() == 1
    assert a.submits == 0 and a.downloads == 0
