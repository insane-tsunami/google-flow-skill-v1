"""Durable jobs. Submit is never retried, including ambiguous interruptions."""

import asyncio
import hashlib
import json
from pathlib import Path

from .media import atomic_json, identifier, lexical_output, recover_output, validate
from .security import ProfileLock


# Explicit codes raised by safe_ui during configuration. Never infer eligibility
# from an exception name or a prefix in a persisted checkpoint.
CONFIGURATION_FAILURES = frozenset(
    {
        "configuration_or_authentication",
        "model_unavailable",
        "configuration_mismatch",
        "mode_unconfirmed",
        "reference_mismatch",
        "video_decoder_install_ffmpeg_and_ffprobe_on_PATH",
        "explicit_max_credits_required",
        "generation_cost_unknown",
        "generation_cost_exceeds_approval",
        "agent_mode_requires_direct_mode_opt_in",
        "direct_mode_unconfirmed",
    }
)


DOWNLOAD_FAILURES = frozenset({"invalid_media_or_identity", "download_attempts_exhausted"})


class Runner:
    def __init__(
        self,
        path,
        jobs,
        adapter,
        max_attempts=3,
        backoff=0.25,
        retry_configuration=False,
        retry_download=None,
    ):
        if not isinstance(max_attempts, int) or not 1 <= max_attempts <= 10:
            raise ValueError("max_attempts must be 1..10")
        self.path, self.jobs, self.adapter = Path(path), jobs, adapter
        self.maximum, self.backoff = max_attempts, backoff
        self.retry_configuration = retry_configuration
        self.retry_download = identifier(retry_download) if retry_download is not None else None
        names = [identifier(j["name"]) for j in jobs]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate job names")
        files = [str(Path(j["file"]).resolve()) for j in jobs]
        if len(files) != len(set(files)):
            raise ValueError("Duplicate output paths")
        self.fingerprint = hashlib.sha256(json.dumps(jobs, sort_keys=True).encode()).hexdigest()
        self.data = self._load()

    def _load(self):
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if (
                    data["version"] != 1
                    or data["fingerprint"] != self.fingerprint
                    or len(data["jobs"]) != len(self.jobs)
                ):
                    raise ValueError("Manifest does not match jobs")
                for row, job in zip(data["jobs"], self.jobs):
                    if row["name"] != job["name"] or row["state"] not in (
                        "pending",
                        "configuring",
                        "uncertain",
                        "submitted",
                        "generating",
                        "downloading",
                        "completed",
                        "failed",
                    ):
                        raise ValueError("Invalid checkpoint")
                    if row.get("asset"):
                        identifier(row["asset"])
                return data
            except (KeyError, TypeError, json.JSONDecodeError) as exc:
                raise ValueError("Incomplete checkpoint; explicit repair required") from exc
        return {
            "version": 1,
            "fingerprint": self.fingerprint,
            "jobs": [{"name": j["name"], "state": "pending", "attempts": {}} for j in self.jobs],
        }

    def checkpoint(self, row, state, **extra):
        row.update(state=state, **extra)
        atomic_json(self.path, self.data)

    def _recover_configuration(self, row, job):
        attempts = row.get("attempts", {})
        configure = attempts.get("configure", 0)
        destination = Path(job["file"])
        if (
            not self.retry_configuration
            or row["state"] != "failed"
            or row.get("error") not in CONFIGURATION_FAILURES
            or type(configure) is not int
            or not 1 <= configure < self.maximum
            or "submit" in attempts
            or "asset" in row
            or "result" in row
            or destination.exists()
            or destination.is_symlink()
        ):
            return
        # Copy only allowlisted public codes, never arbitrary persisted diagnostics.
        history = row.get("configuration_recoveries", [])
        history = [
            {"error": item["error"], "configure_attempts": item["configure_attempts"]}
            for item in history
            if isinstance(item, dict)
            and item.get("error") in CONFIGURATION_FAILURES
            and type(item.get("configure_attempts")) is int
            and item["configure_attempts"] >= 1
        ]
        history.append({"error": row["error"], "configure_attempts": configure})
        row.pop("error", None)
        row.pop("diagnostic", None)
        self.checkpoint(row, "pending", configuration_recoveries=history)

    def _recover_download(self, row, job):
        attempts = row.get("attempts", {})
        download = attempts.get("download", 0)
        destination = Path(job["file"])
        if (
            self.retry_download is None
            or row["state"] != "failed"
            or row.get("asset") != self.retry_download
            or row.get("error") not in DOWNLOAD_FAILURES
            or type(attempts.get("submit")) is not int
            or attempts["submit"] != 1
            or type(download) is not int
            or not 1 <= download < self.maximum
            or destination.exists()
            or destination.is_symlink()
        ):
            return
        # Preserve only public recovery evidence, never arbitrary diagnostics.
        history = row.get("download_recoveries", [])
        if not isinstance(history, list):
            history = []
        history = [
            {"error": item["error"], "download_attempts": item["download_attempts"]}
            for item in history
            if isinstance(item, dict)
            and item.get("error") in DOWNLOAD_FAILURES
            and type(item.get("download_attempts")) is int
            and 1 <= item["download_attempts"] <= 10
        ]
        history.append({"error": row["error"], "download_attempts": download})
        row.pop("error", None)
        row.pop("diagnostic", None)
        self.checkpoint(row, "submitted", download_recoveries=history)

    async def run(self):
        # A separate lock also protects concurrent resume/manifest replacement.
        with ProfileLock(self.path.parent / ("." + self.path.name + ".lock")):
            self.data = self._load()
            atomic_json(self.path, self.data)
            for job, row in zip(self.jobs, self.data["jobs"]):
                kind = job.get("type", "image")
                try:
                    lexical_output(job["file"])
                except ValueError:
                    self.checkpoint(row, "failed", error="unsafe_output_path")
                    continue
                if row["state"] == "completed":
                    try:
                        current = validate(row["result"]["file"], kind)
                        if current["sha256"] != row["result"]["sha256"]:
                            raise ValueError("Integrity mismatch")
                        continue
                    except (ValueError, KeyError):
                        if Path(job["file"]).exists():
                            self.checkpoint(row, "failed", error="output_integrity")
                            continue
                        self.checkpoint(row, "submitted")
                self._recover_download(row, job)
                self._recover_configuration(row, job)
                if row["state"] in ("uncertain", "failed"):
                    continue
                dependencies = job.get("depends_on", [])
                completed = {r["name"] for r in self.data["jobs"] if r["state"] == "completed"}
                if any(d not in completed for d in dependencies):
                    self.checkpoint(row, "pending", error="dependency_unavailable")
                    continue
                if not row.get("asset"):
                    destination = Path(job["file"])
                    if destination.exists() or destination.is_symlink():
                        self.checkpoint(row, "failed", error="output_destination_exists")
                        continue
                    self.checkpoint(row, "configuring")
                    row["attempts"]["configure"] = row["attempts"].get("configure", 0) + 1
                    atomic_json(self.path, self.data)
                    if row["attempts"]["configure"] > self.maximum:
                        self.checkpoint(row, "failed", error="configure_attempts_exhausted")
                        continue
                    try:
                        effective = await self.adapter.configure(job)
                    except Exception as error:
                        from .safe_ui import ConfigurationError

                        extra = (
                            {"diagnostic": error.evidence}
                            if isinstance(error, ConfigurationError)
                            else {}
                        )
                        self.checkpoint(
                            row,
                            "failed",
                            error=error.code
                            if isinstance(error, ConfigurationError)
                            else "configuration_or_authentication",
                            **extra,
                        )
                        continue
                    # Durable uncertainty BEFORE any operation that might submit.
                    row["attempts"]["submit"] = 1
                    self.checkpoint(row, "uncertain", effective=effective)
                    try:
                        asset = identifier(await self.adapter.submit(job))
                    except Exception:
                        self.checkpoint(row, "uncertain", error="submit_or_identity_unconfirmed")
                        continue
                    self.checkpoint(row, "submitted", asset=asset)
                # Recover publication locally before consulting the retry budget.
                destination = Path(job["file"])
                if destination.exists() or destination.is_symlink():
                    try:
                        result = recover_output(destination, row["asset"], kind)
                    except ValueError:
                        self.checkpoint(row, "failed", error="invalid_media_or_identity")
                    else:
                        self.checkpoint(row, "completed", result=result)
                    continue
                for _ in range(self.maximum):
                    tries = row["attempts"].get("download", 0)
                    if tries >= self.maximum:
                        self.checkpoint(row, "failed", error="download_attempts_exhausted")
                        break
                    row["attempts"]["download"] = tries + 1
                    self.checkpoint(row, "downloading")
                    try:
                        result = await self.adapter.download(job, row["asset"])
                        if result["asset"] != row["asset"]:
                            raise ValueError("Wrong asset receipt")
                        check = validate(result["file"], kind)
                        if check["sha256"] != result["sha256"]:
                            raise ValueError("Wrong result integrity")
                        self.checkpoint(row, "completed", result=result)
                        break
                    except ValueError:
                        self.checkpoint(row, "failed", error="invalid_media_or_identity")
                        break
                    except Exception:
                        if tries + 1 >= self.maximum:
                            self.checkpoint(row, "failed", error="download_attempts_exhausted")
                        else:
                            self.checkpoint(row, "submitted", error="download_retry")
                            await asyncio.sleep(min(self.backoff * 2**tries, 10))
            return 0 if all(r["state"] == "completed" for r in self.data["jobs"]) else 1
