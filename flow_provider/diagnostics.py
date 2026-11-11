"""Fixed-schema diagnostics: no exception messages, locals, URLs or proof values."""

from pathlib import Path
import traceback

STAGES = frozenset(
    {
        "configure",
        "submit_entry",
        "authentication",
        "project",
        "references",
        "direct_mode",
        "character",
        "configuration",
        "cost",
        "baseline",
        "before_click",
        "click_returned",
        "asset_lifecycle",
    }
)
FIELDS = frozenset({"name", "kind", "thumbnail", "variants", "voice", "description", "sample"})
COUNTS = frozenset(
    {
        "baseline_cards",
        "baseline_ids",
        "baseline_progressing",
        "candidate_cards",
        "candidate_ids",
        "bound",
        "progressing",
    }
)


class ProofChanged(ValueError):
    def __init__(self, fields):
        self.fields = sorted(FIELDS.intersection(fields))
        super().__init__(
            "Saved character or associated voice changed (fields: " + ", ".join(self.fields) + ")"
        )


def event(stage, counts=None):
    if stage not in STAGES:
        raise ValueError("Unknown diagnostic stage")
    result = {"stage": stage}
    if counts:
        if set(counts) - COUNTS or any(
            type(v) is not int or not 0 <= v <= 100000 for v in counts.values()
        ):
            raise ValueError("Unsafe diagnostic counts")
        result["counts"] = dict(counts)
    return result


def failure(error, stage):
    """Use trusted code metadata only; never format or inspect exception text."""
    result = event(stage)
    classes = {
        "ValueError",
        "TimeoutError",
        "RuntimeError",
        "OSError",
        "KeyError",
        "TypeError",
        "ConfigurationError",
        "ProofChanged",
        "Error",
    }
    name = type(error).__name__
    result["class"] = name if name in classes else "Exception"
    package = Path(__file__).resolve().parent
    frames = []
    for frame in traceback.extract_tb(error.__traceback__):
        path = Path(frame.filename)
        if path.parent.resolve() == package and path.suffix == ".py":
            frames.append({"file": path.name, "line": frame.lineno})
    result["frames"] = frames[-8:]
    if isinstance(error, ProofChanged):
        result["fields"] = sorted(FIELDS.intersection(error.fields))
    return result
