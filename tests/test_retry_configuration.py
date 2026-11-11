"""Explicit pre-submit recovery through the real Runner and CLI, offline only."""

import json

import pytest

import flow
from flow_provider.batch import Runner
from flow_provider.media import atomic_json
from flow_provider.safe_ui import ConfigurationError
from test_safety import FakeAdapter


class Adapter(FakeAdapter):
    failing = True
    configurations = 0

    async def configure(self, job):
        self.configurations += 1
        if self.failing:
            raise ConfigurationError("model_unavailable", {"available": ["Model"]})
        return await super().configure(job)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "previous_error",
    ["model_unavailable", "configuration_or_authentication", "reference_mode_unconfirmed"],
)
async def test_explicit_recovery_preserves_attempts_and_default_is_terminal(
    tmp_path, previous_error
):
    jobs = [{"name": "one", "file": str(tmp_path / "one.png")}]
    path = tmp_path / "report.json"
    adapter = Adapter(tmp_path)
    assert await Runner(path, jobs, adapter).run() == 1
    data = json.loads(path.read_text())
    data["jobs"][0]["error"] = previous_error
    atomic_json(path, data)
    adapter.failing = False
    assert await Runner(path, jobs, adapter).run() == 1
    assert adapter.configurations == 1 and adapter.submits == 0
    runner = Runner(path, jobs, adapter, retry_configuration=True)
    assert await runner.run() == 0
    row = runner.data["jobs"][0]
    assert row["attempts"] == {"configure": 2, "submit": 1, "download": 1}
    assert row["configuration_recoveries"] == [{"error": previous_error, "configure_attempts": 1}]
    assert adapter.submits == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"state": "uncertain"},
        {"state": "submitted", "asset": "asset-1"},
        {"state": "downloading", "asset": "asset-1"},
        {"attempts": {"configure": 1, "submit": 0}},
        {"asset": None},
        {"result": {}},
        {"error": "output_integrity"},
        {"error": "output_destination_exists"},
        {"error": "configure_attempts_exhausted"},
        {"error": "unknown_private_error"},
        {"attempts": {"configure": 0}},
        {"attempts": {"configure": 3}},
        {"output": True},
    ],
)
async def test_blocked_recovery_zero_submits(tmp_path, change):
    jobs = [{"name": "one", "file": str(tmp_path / "one.png")}]
    adapter = Adapter(tmp_path)
    runner = Runner(tmp_path / "report.json", jobs, adapter)
    row = runner.data["jobs"][0]
    row.update(state="failed", error="model_unavailable", attempts={"configure": 1})
    if change.get("output"):
        (tmp_path / "one.png").write_bytes(b"existing")
    row.update({k: v for k, v in change.items() if k != "output"})
    before = dict(row["attempts"])
    atomic_json(runner.path, runner.data)
    await Runner(runner.path, jobs, adapter, retry_configuration=True).run()
    assert adapter.submits == 0 and adapter.configurations == 0
    after = json.loads(runner.path.read_text())["jobs"][0]
    assert "configuration_recoveries" not in after
    assert all(after["attempts"][key] == value for key, value in before.items())
    if change.get("state") not in ("submitted", "downloading"):
        assert after["attempts"] == before


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["image", "video", "batch"])
async def test_real_cli_resume_budget_and_sanitized_history(tmp_path, monkeypatch, command):
    adapter = Adapter(tmp_path)
    monkeypatch.setattr(flow, "UIAdapter", lambda *a, **kw: adapter)

    async def shutdown():
        pass

    monkeypatch.setattr(flow.browser, "shutdown", shutdown)
    if command == "batch":
        jobfile = tmp_path / "jobs.json"
        jobfile.write_text(
            json.dumps({"project": "one", "jobs": [{"name": "one", "model": "Model"}]})
        )
        argv = [command, str(jobfile)]
    else:
        argv = [command, "--name", "one", "--model", "Model", "--prompt", "private"]
    argv += ["--out", str(tmp_path), "--max-attempts", "1"]
    parser = flow.build_parser()
    assert await flow.execute(parser.parse_args(argv)) == 1
    path = tmp_path / "one" / "batch_report.json"
    data = json.loads(path.read_text())
    data["jobs"][0]["diagnostic"] = {"private": "secret"}
    atomic_json(path, data)
    assert await flow.execute(parser.parse_args(argv + ["--retry-configuration"])) == 1
    assert adapter.configurations == 1 and adapter.submits == 0
    # A larger budget is explicit; retry remains a single configuration attempt.
    assert (
        await flow.execute(
            parser.parse_args(argv + ["--retry-configuration", "--max-attempts", "2"])
        )
        == 1
    )
    row = json.loads(path.read_text())["jobs"][0]
    assert row["attempts"] == {"configure": 2}
    assert row["configuration_recoveries"] == [
        {"error": "model_unavailable", "configure_attempts": 1}
    ]
    assert adapter.submits == 0
    assert (
        await flow.execute(
            parser.parse_args(argv + ["--retry-configuration", "--max-attempts", "3"])
        )
        == 1
    )
    row = json.loads(path.read_text())["jobs"][0]
    assert row["attempts"] == {"configure": 3}
    assert row["configuration_recoveries"][-1] == {
        "error": "model_unavailable",
        "configure_attempts": 2,
    }
    assert len(row["configuration_recoveries"]) == 2
    assert adapter.submits == 0


@pytest.mark.parametrize("command", ["status", "login", "clean"])
def test_flag_only_generation_commands(command):
    with pytest.raises(SystemExit):
        flow.build_parser().parse_args([command, "--retry-configuration"])
