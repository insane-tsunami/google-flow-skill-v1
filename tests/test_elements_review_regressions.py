"""Review regressions: output aliases cannot bypass producer verification."""

import pytest
from PIL import Image

import flow
from flow_provider.batch import Runner
from test_safety import FakeAdapter


@pytest.mark.parametrize("key", ["image", "images", "start"])
@pytest.mark.parametrize("exists", [False, True])
async def test_output_path_requires_producer(tmp_path, key, exists):
    output = tmp_path / "batch" / "producer.png"
    if exists:
        output.parent.mkdir()
        Image.new("RGB", (4, 4), "red").save(output)
    consumer = dict(type="video" if key == "start" else "image", name="consumer", model="Exact")
    consumer[key] = [str(output)] if key == "images" else str(output)
    data = dict(
        project="batch", jobs=[dict(type="image", name="producer", model="Exact"), consumer]
    )
    directory, jobs = flow.prepare_jobs(data, tmp_path)
    assert jobs[1]["depends_on"] == ["producer"]
    adapter = FakeAdapter(tmp_path)
    runner = Runner(directory / "report.json", jobs, adapter)
    # A failed/corrupt producer must never allow its alias-path consumer to pay.
    runner.data["jobs"][0].update(state="failed", error="output_integrity")
    runner.checkpoint(runner.data["jobs"][0], "failed")
    assert await runner.run() == 1
    assert adapter.submits == 0
    assert runner.data["jobs"][1]["state"] == "pending"


async def test_changed_external_input_blocks_resume(tmp_path):
    source = tmp_path / "external.png"
    Image.new("RGB", (4, 4), "red").save(source)
    data = dict(
        project="batch", jobs=[dict(type="image", name="one", model="Exact", images=[str(source)])]
    )
    directory, jobs = flow.prepare_jobs(data, tmp_path)
    runner = Runner(directory / "report.json", jobs, None)
    runner.checkpoint(runner.data["jobs"][0], "uncertain")
    Image.new("RGB", (4, 4), "blue").save(source)
    _, changed = flow.prepare_jobs(data, tmp_path)
    with pytest.raises(ValueError, match="Manifest does not match"):
        Runner(runner.path, changed, None)
