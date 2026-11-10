"""Pure identity parsing tests run even when the Chromium sandbox cannot start."""

import pytest

from flow_provider.safe_ui import _attached_image_id

UUID = "12345678-1234-4567-89ab-123456789abc"
URL = f"https://flow-content.google/image/{UUID}"


@pytest.mark.parametrize(
    "suffix", ["", "?Expires=1&KeyName=test&Signature=synthetic", "?Signature=rotated"]
)
def test_identity_ignores_signed_query(suffix):
    assert _attached_image_id(URL + suffix) == UUID


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        URL.replace("https:", "http:"),
        URL.replace("https:", ""),
        URL.replace("flow-content.google", "evil.test"),
        URL.replace("flow-content.google", "flow-content.google.evil.test"),
        URL.replace("flow-content.google", "user@flow-content.google"),
        URL.replace("flow-content.google", "flow-content.google:443"),
        URL.replace("/image/", "/video/"),
        URL + "/extra",
        URL + "#fragment",
        URL.replace(UUID, "reference.png"),
        URL.replace(UUID, "%31" + UUID[1:]),
        " " + URL,
        URL + "\n",
        "https://[invalid/image/" + UUID,
    ],
)
def test_unknown_source_fails_without_leaking_url(url):
    with pytest.raises(ValueError, match="source unverified") as error:
        _attached_image_id(url)
    assert str(error.value) == "Attached reference source unverified"
