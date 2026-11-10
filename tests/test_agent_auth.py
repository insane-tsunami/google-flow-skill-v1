import pytest
from flow_provider.security import auth_state, require_auth

SHELL = """<flow-project-shell><flow-project-page>
<button aria-label="Página inicial">home</button>
<flow-creative-agent-prompt-box><flow-rich-text-editor><div contenteditable="true" style="min-height:30px;display:block"></div></flow-rich-text-editor></flow-creative-agent-prompt-box>
</flow-project-page></flow-project-shell>"""


@pytest.mark.asyncio
async def test_agent_project_auth_independent_of_settings(page):
    await page.route(
        "https://flow.google.com/**",
        lambda route: route.fulfill(content_type="text/html; charset=utf-8", body=SHELL),
    )
    await page.goto("https://flow.google.com/u/1/project/test")
    assert await auth_state(page) == "authenticated"


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["shell", "home", "editor"])
async def test_incomplete_agent_project_not_auth_evidence(page, missing):
    html = SHELL
    if missing == "shell":
        html = html.replace("flow-project-shell", "section")
    elif missing == "home":
        html = html.replace('aria-label="Página inicial"', 'aria-label="other"')
    else:
        html = html.replace('contenteditable="true"', 'contenteditable="false"')
    await page.route(
        "https://flow.google.com/**",
        lambda route: route.fulfill(content_type="text/html; charset=utf-8", body=html),
    )
    await page.goto("https://flow.google.com/u/1/project/test")
    assert await auth_state(page) == "unverifiable"


@pytest.mark.asyncio
async def test_require_auth_waits_for_app_render(page):
    await page.route(
        "https://flow.google.com/**",
        lambda route: route.fulfill(content_type="text/html; charset=utf-8", body="<body></body>"),
    )
    await page.goto("https://flow.google.com/u/1/project/test")
    await page.evaluate("html => setTimeout(() => {document.body.innerHTML=html}, 200)", SHELL)
    await require_auth(page)
    assert await auth_state(page) == "authenticated"
