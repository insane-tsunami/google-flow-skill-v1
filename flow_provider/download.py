"""Asset-bound downloads only; latest-card recovery is deliberately disabled."""

from .browser import get_page
from .safe_ui import download_asset


async def download_latest(output_path, resolution="1K", is_video=False, *, asset_id=None):
    if not asset_id:
        raise ValueError("asset_id required; latest-card and Downloads heuristics disabled")
    return (
        await download_asset(
            await get_page(),
            {
                "file": output_path,
                "type": "video" if is_video else "image",
                "resolution": resolution,
            },
            asset_id,
        )
    )["file"]


async def delete_latest_card(*args, **kwargs):
    raise ValueError("Automatic deletion of unattributed assets is disabled")
