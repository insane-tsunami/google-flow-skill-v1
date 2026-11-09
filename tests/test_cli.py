import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import flow


def test_prepare_jobs_stable_and_dependencies(tmp_path):
    data = {
        "project": "demo",
        "defaults": {"image_model": "Nano Banana 2.1", "video_model": "Omni 1.2 Flash"},
        "jobs": [
            {"name": "one", "prompt": "test"},
            {"name": "two", "type": "video", "start": "one"},
        ],
    }
    directory, jobs = flow.prepare_jobs(data, tmp_path)
    assert directory == tmp_path / "demo"
    assert jobs[1]["depends_on"] == ["one"]
    assert jobs[1]["start"] == jobs[0]["file"]
    assert jobs[0]["model"] == "Nano Banana 2.1"
    assert flow.prepare_jobs(data, tmp_path) == (directory, jobs)


@pytest.mark.parametrize(
    "job", [{"name": "../oops"}, {"name": "same", "count": 2}, {"name": "one", "type": "unknown"}]
)
def test_invalid_jobs_fail_before_browser(tmp_path, job):
    with pytest.raises(ValueError):
        flow.prepare_jobs({"project": "demo", "jobs": [job]}, tmp_path)


def test_status_absent_profile_no_launch(tmp_path):
    import os

    result = subprocess.run(
        [sys.executable, str(Path(flow.__file__)), "status"],
        env=os.environ | {"FLOW_CHROME_PROFILE": str(tmp_path / "absent")},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["authentication"] == "profile_missing"
    assert not (tmp_path / "absent").exists()


def test_default_sandbox():
    from flow_provider.browser import launch_options

    assert launch_options()["chromium_sandbox"] is True
    assert "--no-sandbox" not in launch_options()["args"]
