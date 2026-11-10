"""Regressions derived from authenticated redirect, without account content."""

import pytest

from flow_provider import project


def test_accept_canonical_account_redirect(monkeypatch):
    monkeypatch.setenv("FLOW_ACCOUNT_INDEX", "1")
    assert project.flow_url() == "https://flow.google.com/u/1/"
    project.verify_account("https://flow.google.com/u/1/project/test")
    project.verify_account("https://labs.google/fx/tools/flow/u/1/project/test")


@pytest.mark.parametrize(
    "url",
    [
        "https://flow.google.com/u/0/project/test",
        "https://flow.google.com/project/test",
        "https://flow.google.com.evil.test/u/1/project/test",
        "http://flow.google.com/u/1/project/test",
        "https://flow.google.com/u/10/project/test",
        "https://evil.test/u/1/project/test",
    ],
)
def test_reject_foreign_canonical_scope(monkeypatch, url):
    monkeypatch.setenv("FLOW_ACCOUNT_INDEX", "1")
    with pytest.raises(ValueError, match="account"):
        project.verify_account(url)
