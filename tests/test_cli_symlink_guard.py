from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import flow
from flow_provider.batch import Runner
from test_safety import FakeAdapter


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["output", "project_directory"])
async def test_public_prepare_jobs_blocks_lexical_symlink_before_paid_submit(tmp_path, kind):
    project = tmp_path / "project"
    foreign = tmp_path / "foreign"
    if kind == "output":
        project.mkdir()
        (project / "one.png").symlink_to(foreign / "one.png")
        link = project / "one.png"
    else:
        foreign.mkdir()
        project.symlink_to(foreign, target_is_directory=True)
        link = project
    adapter = FakeAdapter(tmp_path)
    blocked = False
    try:
        directory, jobs = flow.prepare_jobs(
            {"project": "project", "jobs": [{"name": "one", "model": "Nano Banana 2.1"}]}, tmp_path
        )
        blocked = await Runner(directory / "batch_report.json", jobs, adapter, backoff=0).run() == 1
    except ValueError:
        blocked = True
    assert blocked, "Public preparation must not erase symlink identity before the guard"
    assert adapter.submits == 0 and adapter.downloads == 0
    assert link.is_symlink()
    assert not (foreign / "one.png").exists()
