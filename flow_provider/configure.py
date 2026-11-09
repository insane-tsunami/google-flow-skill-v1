"""Deprecated split configuration API; use Runner + UIAdapter."""


async def select_image_mode(*args, **kwargs):
    raise RuntimeError("Migrate split generation calls to Runner + UIAdapter")


async def select_video_mode(*args, **kwargs):
    raise RuntimeError("Migrate split generation calls to Runner + UIAdapter")
