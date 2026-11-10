from pathlib import Path
import sys
import json

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_safety import FakeAdapter


@pytest.mark.asyncio
async def test_public_config_failure_and_no_submit(tmp_path):
    from flow_provider.batch import Runner
    from flow_provider.safe_ui import ConfigurationError

    class Unavailable(FakeAdapter):
        async def configure(self, job):
            raise ConfigurationError(
                "model_unavailable",
                {"available": ["Nano Banana 2.1"], "requested": {"model": "Nano Banana 9"}},
            )

    a = Unavailable(tmp_path)
    jobs = [{"name": "one", "file": str(tmp_path / "one.png"), "model": "Nano Banana 9"}]
    assert await Runner(tmp_path / "manifest.json", jobs, a).run() == 1
    assert a.submits == 0
    row = json.loads((tmp_path / "manifest.json").read_text())["jobs"][0]
    assert row["diagnostic"]["available"] == ["Nano Banana 2.1"]
    assert row["diagnostic"]["requested"]["model"] == "Nano Banana 9"


def test_unsafe_labels_not_public():
    from flow_provider.safe_ui import ConfigurationError

    with pytest.raises(ValueError):
        ConfigurationError("model_unavailable", {"available": ["https://secret/?token=private"]})


@pytest.mark.asyncio
async def test_process_death_lock_recovery(tmp_path):
    import subprocess
    from flow_provider.security import ProfileLock

    code = "import os,sys; from flow_provider.security import ProfileLock; x=ProfileLock(sys.argv[1]).acquire(); os._exit(9)"
    result = subprocess.run([sys.executable, "-c", code, str(tmp_path / "profile")])
    assert result.returncode == 9
    with ProfileLock(tmp_path / "profile"):
        pass


@pytest.mark.asyncio
async def test_invalid_config_terminal_and_before_submit_resume(tmp_path):
    from flow_provider.batch import Runner

    class Interrupted(FakeAdapter):
        async def configure(self, job):
            if self.crash:
                raise KeyboardInterrupt()
            return await super().configure(job)

    jobs = [{"name": "one", "type": "image", "file": str(tmp_path / "one.png")}]
    a = Interrupted(tmp_path, "config")
    with pytest.raises(KeyboardInterrupt):
        await Runner(tmp_path / "manifest.json", jobs, a).run()
    a.crash = None
    assert await Runner(tmp_path / "manifest.json", jobs, a).run() == 0
    assert a.submits == 1


@pytest.mark.asyncio
async def test_resume_corrupt_output_never_regenerates(tmp_path):
    from flow_provider.batch import Runner

    jobs = [{"name": "one", "type": "image", "file": str(tmp_path / "one.png")}]
    a = FakeAdapter(tmp_path)
    assert await Runner(tmp_path / "manifest.json", jobs, a).run() == 0
    (tmp_path / "one.png").write_bytes(b"corrupt")
    assert await Runner(tmp_path / "manifest.json", jobs, a).run() == 1
    assert a.submits == 1
