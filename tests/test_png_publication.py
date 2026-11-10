import hashlib
import json
from pathlib import Path
import sys

from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flow_provider.media import atomic_json, publish, recover_output
from test_safety import FakeAdapter


@pytest.mark.parametrize(
    "fmt,mode", [("JPEG", "RGB"), ("WEBP", "RGBA"), ("PNG", "RGBA"), ("JPEG", "CMYK")]
)
def test_png_destination_encodes_final_bytes(tmp_path, fmt, mode):
    source = tmp_path / "source"
    Image.new(mode, (8, 9)).save(source, format=fmt)
    original = source.read_bytes()
    destination = tmp_path / "result.PNG"
    metadata = publish(source, destination, "asset-one", "image")
    data = destination.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(destination) as image:
        assert image.format == "PNG"
        image.load()
        assert image.size == (8, 9)
        if mode == "RGBA":
            assert image.mode == "RGBA"
    assert metadata["format"] == "PNG"
    assert metadata["size"] == len(data)
    assert metadata["sha256"] == hashlib.sha256(data).hexdigest()
    assert source.read_bytes() == original
    atomic_json(str(destination) + ".receipt.json", metadata)
    assert recover_output(destination, "asset-one", "image") == metadata
    with pytest.raises(FileExistsError):
        publish(source, destination, "other", "image")
    assert destination.read_bytes() == data


@pytest.mark.parametrize("data", [b"", b"not an image", b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff"])
def test_invalid_png_source_does_not_publish(tmp_path, data):
    source = tmp_path / "source"
    source.write_bytes(data)
    destination = tmp_path / "out.png"
    with pytest.raises(ValueError):
        publish(source, destination, "asset-one", "image")
    assert not destination.exists()
    assert not list(tmp_path.glob("*.part"))
    assert not Path(str(destination) + ".receipt.json").exists()


def test_legacy_jpeg_receipt_is_not_rewritten(tmp_path):
    from flow_provider.media import validate

    destination = tmp_path / "legacy.png"
    Image.new("RGB", (8, 8)).save(destination, format="JPEG")
    metadata = validate(destination, "image") | {"asset": "legacy", "file": str(destination)}
    receipt = Path(str(destination) + ".receipt.json")
    atomic_json(receipt, metadata)
    before = destination.read_bytes(), receipt.read_bytes()
    assert recover_output(destination, "legacy", "image") == metadata
    assert (destination.read_bytes(), receipt.read_bytes()) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("fmt", ["JPEG", "WEBP"])
async def test_converted_receipt_recovers_without_new_download(tmp_path, fmt):
    from flow_provider.batch import Runner

    class Published(FakeAdapter):
        async def download(self, job, asset):
            self.downloads += 1
            source = tmp_path / "source"
            Image.new("RGB", (8, 8)).save(source, format=fmt)
            receipt = publish(source, job["file"], asset, "image")
            assert receipt["format"] == "PNG"
            atomic_json(job["file"] + ".receipt.json", receipt)
            raise KeyboardInterrupt()

    jobs = [{"name": "one", "type": "image", "file": str(tmp_path / "one.png")}]
    adapter = Published(tmp_path)
    manifest = tmp_path / "manifest.json"
    with pytest.raises(KeyboardInterrupt):
        await Runner(manifest, jobs, adapter, max_attempts=1).run()
    assert await Runner(manifest, jobs, adapter, max_attempts=1).run() == 0
    assert await Runner(manifest, jobs, adapter, max_attempts=1).run() == 0
    assert adapter.submits == 1 and adapter.downloads == 1
    receipt = json.loads((tmp_path / "one.png.receipt.json").read_text())
    assert receipt["sha256"] == hashlib.sha256((tmp_path / "one.png").read_bytes()).hexdigest()
