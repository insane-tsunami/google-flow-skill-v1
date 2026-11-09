"""Uncheckpointed submit APIs are disabled to avoid duplicate credit spending."""


async def submit_prompt(*args, **kwargs):
    raise RuntimeError("Use Runner + UIAdapter for verified, checkpointed submission")


submit_segments_with_voice = submit_prompt
submit_prompt_with_voice = submit_prompt
submit_prompt_with_mentions = submit_prompt
