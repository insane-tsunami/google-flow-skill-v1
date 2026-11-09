import json
from pathlib import Path
import sys

from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_safety import FakeAdapter


@pytest.mark.asyncio
async def test_crash_after_publication_recovers_even_when_budget_exhausted(tmp_path):
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
    assert await Runner(tmp_path / "manifest.json", jobs, a, max_attempts=1).run() == 0
    assert a.submits == 1 and a.downloads == 1
    assert json.loads((tmp_path / "manifest.json").read_text())["jobs"][0]["state"] == "completed"
