"""Decode before publishing. No download-directory heuristics."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from PIL import Image


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", value):
        raise ValueError("Invalid asset identifier")
    return value


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(dir=path.parent, suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
        if os.name != "nt":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        Path(temp).unlink(missing_ok=True)


def validate(path, kind):
    path = Path(path)
    try:
        if not path.is_file() or not path.stat().st_size:
            raise ValueError("Empty or missing media")
        if kind == "image":
            with Image.open(path) as image:
                fmt = image.format
                if fmt not in ("PNG", "JPEG", "WEBP"):
                    raise ValueError("Unsupported image signature")
                image.verify()
            with Image.open(path) as image:
                image.load()
                if min(image.size) < 1:
                    raise ValueError("Invalid dimensions")
            info = {"format": fmt}
        elif kind == "video":
            with path.open("rb") as f:
                head = f.read(16)
            if head[4:8] != b"ftyp" and head[:4] != b"\x1aE\xdf\xa3":
                raise ValueError("Invalid video signature")
            proc = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_streams",
                    "-show_format",
                    "-of",
                    "json",
                    str(path),
                ],
                capture_output=True,
                timeout=30,
                check=True,
            )
            data = json.loads(proc.stdout)
            streams = [
                s
                for s in data["streams"]
                if s.get("codec_type") == "video"
                and s.get("width", 0) > 0
                and s.get("height", 0) > 0
            ]
            duration = float(data["format"]["duration"])
            if not streams or not 0 < duration < float("inf"):
                raise ValueError("No valid video stream/duration")
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-xerror",
                    "-i",
                    str(path),
                    "-map",
                    "0:v:0",
                    "-f",
                    "null",
                    "-",
                ],
                check=True,
                capture_output=True,
                timeout=120,
            )
            info = {"format": data["format"]["format_name"], "duration": duration}
        else:
            raise ValueError("Unknown media type")
        hasher = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
        digest = hasher.hexdigest()
        return info | {"type": kind, "size": path.stat().st_size, "sha256": digest}
    except (
        OSError,
        KeyError,
        subprocess.SubprocessError,
        SyntaxError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError("Media decode failed") from exc


def publish(source, destination, asset, kind):
    asset = identifier(asset)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination.exists():
        raise FileExistsError("Destination already exists; never overwrite an asset")
    fd, temp = tempfile.mkstemp(dir=destination.parent, suffix=".part")
    os.close(fd)
    try:
        shutil.copyfile(source, temp)
        metadata = validate(temp, kind)
        with open(temp, "rb") as f:
            os.fsync(f.fileno())
        # Hard-link publishes atomically with exclusive-create semantics. Unlike
        # replace(), it cannot overwrite a concurrent download's final asset.
        os.link(temp, destination)
        return metadata | {"asset": asset, "file": str(destination.resolve())}
    finally:
        Path(temp).unlink(missing_ok=True)
