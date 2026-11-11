"""One bounded, durable configuration-only extension; never extra payment."""

import json

import pytest

import flow
from flow_provider.batch import Runner
from flow_provider.media import atomic_json
from test_retry_configuration import Adapter


def exhausted(tmp_path, base=10):
    jobs = [{"name": "one", "file": str(tmp_path / "one.png")}]
    adapter = Adapter(tmp_path)
    runner = Runner(tmp_path / "report.json", jobs, adapter, max_attempts=base)
    row = runner.data["jobs"][0]
    row.update(
        state="failed",
        error="model_unavailable",
        attempts={"configure": base},
        configuration_recoveries=[{"error": "model_unavailable", "configure_attempts": base - 1}],
    )
    atomic_json(runner.path, runner.data)
    return runner, jobs, adapter


@pytest.mark.asyncio
@pytest.mark.parametrize("base", [2, 10])
async def test_extension_is_not_renewed_and_needs_explicit_flag_each_time(tmp_path, base):
    runner, jobs, adapter = exhausted(tmp_path, base)
    kwargs = dict(max_attempts=base, retry_configuration=True, additional_configuration_attempts=2)
    for expected in (base + 1, base + 2, base + 2):
        current = Runner(runner.path, jobs, adapter, **kwargs)
        assert await current.run() == 1
        row = current.data["jobs"][0]
        assert row["attempts"] == {"configure": expected}
        assert current.maximum == base  # download budget is NOT extended
        assert current.data["fingerprint"] == runner.fingerprint
        assert row["configuration_extension"] == {"base": base, "additional": 2}
        if expected == base + 1:
            plain = Runner(runner.path, jobs, adapter, max_attempts=base, retry_configuration=True)
            assert await plain.run() == 1
            assert plain.data["jobs"][0]["attempts"] == {"configure": base + 1}
    assert adapter.configurations == 2 and adapter.submits == 0
    assert row["configuration_recoveries"] == [
        {"error": "model_unavailable", "configure_attempts": i} for i in (base - 1, base, base + 1)
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("base", [2, 10])
async def test_extension_success_and_replay_only_one_submit(tmp_path, base):
    runner, jobs, adapter = exhausted(tmp_path, base)
    adapter.failing = False
    kwargs = dict(max_attempts=base, retry_configuration=True, additional_configuration_attempts=2)
    for _ in range(2):
        current = Runner(runner.path, jobs, adapter, **kwargs)
        assert await current.run() == 0
    assert current.data["jobs"][0]["attempts"] == {
        "configure": base + 1,
        "submit": 1,
        "download": 1,
    }
    assert adapter.configurations == 1 and adapter.submits == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"state": "uncertain"},
        {"attempts": {"configure": 10, "submit": 0}},
        {"asset": None},
        {"result": {}},
        {"error": "unknown"},
        {"attempts": {"configure": 9}},
        {"configuration_extension": {"base": 10, "additional": 99}},
    ],
)
async def test_extension_cannot_revive_unsafe_or_foreign_state(tmp_path, change):
    runner, jobs, adapter = exhausted(tmp_path)
    runner.data["jobs"][0].update(change)
    atomic_json(runner.path, runner.data)
    before = runner.path.read_bytes()
    with pytest.raises(ValueError):
        await Runner(
            runner.path,
            jobs,
            adapter,
            max_attempts=10,
            retry_configuration=True,
            additional_configuration_attempts=2,
        ).run()
    assert runner.path.read_bytes() == before
    assert adapter.configurations == adapter.submits == 0


@pytest.mark.parametrize("amount", [-1, 3, True, 1.5])
def test_extension_range_is_strict(tmp_path, amount):
    runner, jobs, adapter = exhausted(tmp_path)
    with pytest.raises(ValueError):
        Runner(
            runner.path,
            jobs,
            adapter,
            max_attempts=10,
            retry_configuration=True,
            additional_configuration_attempts=amount,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"state": "submitted", "attempts": {"configure": 11, "submit": 1}},
        {"state": "pending", "attempts": {"configure": 11, "submit": 1}},
        {"attempts": {"configure": 9}},
        {"attempts": {"configure": True}},
        {"attempts": {}},
        {"attempts": {"configure": 13}},
    ],
)
async def test_existing_marker_rejects_corrupt_counters_and_submit_state(tmp_path, change):
    runner, jobs, adapter = exhausted(tmp_path)
    row = runner.data["jobs"][0]
    row.update(configuration_extension={"base": 10, "additional": 2})
    row.update(change)
    atomic_json(runner.path, runner.data)
    before = runner.path.read_bytes()
    with pytest.raises(ValueError):
        await Runner(
            runner.path,
            jobs,
            adapter,
            max_attempts=10,
            retry_configuration=True,
            additional_configuration_attempts=2,
        ).run()
    assert runner.path.read_bytes() == before
    assert adapter.configurations == adapter.submits == 0


@pytest.mark.parametrize("command", ["image", "video", "batch"])
def test_cli_extension_flag_is_operational_not_job_input(command):
    argv = (
        [command, "jobs.json"]
        if command == "batch"
        else [command, "--prompt", "x", "--model", "M", "--name", "one"]
    )
    args = flow.build_parser().parse_args(argv + ["--additional-configuration-attempts", "2"])
    assert args.additional_configuration_attempts == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("base", [2, 10])
async def test_cli_extension_preserves_fingerprint(tmp_path, monkeypatch, base):
    adapter = Adapter(tmp_path)
    monkeypatch.setattr(flow, "UIAdapter", lambda *a, **kw: adapter)

    async def shutdown():
        pass

    monkeypatch.setattr(flow.browser, "shutdown", shutdown)
    argv = [
        "image",
        "--name",
        "one",
        "--model",
        "M",
        "--prompt",
        "private",
        "--out",
        str(tmp_path),
        "--max-attempts",
        str(base),
    ]
    parser = flow.build_parser()
    assert await flow.execute(parser.parse_args(argv)) == 1
    path = tmp_path / "one" / "batch_report.json"
    data = json.loads(path.read_text())
    fingerprint = data["fingerprint"]
    data["jobs"][0]["attempts"]["configure"] = base
    atomic_json(path, data)
    assert (
        await flow.execute(
            parser.parse_args(
                argv + ["--retry-configuration", "--additional-configuration-attempts", "2"]
            )
        )
        == 1
    )
    data = json.loads(path.read_text())
    assert data["fingerprint"] == fingerprint
    assert data["jobs"][0]["attempts"] == {"configure": base + 1}


@pytest.mark.asyncio
@pytest.mark.parametrize("base", [2, 10])
@pytest.mark.parametrize("extra", [0, 1, 2])
async def test_extension_cannot_change_original_budget_on_replay(tmp_path, base, extra):
    runner, jobs, adapter = exhausted(tmp_path, base)
    current = Runner(
        runner.path,
        jobs,
        adapter,
        max_attempts=base,
        retry_configuration=True,
        additional_configuration_attempts=2,
    )
    assert await current.run() == 1
    before = runner.path.read_bytes()
    changed = base + 1 if base < 10 else base - 1
    with pytest.raises(ValueError):
        await Runner(
            runner.path,
            jobs,
            adapter,
            max_attempts=changed,
            retry_configuration=True,
            additional_configuration_attempts=extra,
        ).run()
    assert runner.path.read_bytes() == before
    assert adapter.configurations == 1 and adapter.submits == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["uncertain", "submitted"])
async def test_base_two_rejects_paid_or_uncertain_extension(tmp_path, state):
    runner, jobs, adapter = exhausted(tmp_path, 2)
    runner.data["jobs"][0].update(state=state, attempts={"configure": 2, "submit": 1})
    atomic_json(runner.path, runner.data)
    before = runner.path.read_bytes()
    with pytest.raises(ValueError):
        await Runner(
            runner.path,
            jobs,
            adapter,
            max_attempts=2,
            retry_configuration=True,
            additional_configuration_attempts=2,
        ).run()
    assert runner.path.read_bytes() == before
    assert adapter.configurations == adapter.submits == 0
