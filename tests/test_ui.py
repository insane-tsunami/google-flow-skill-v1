import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "label", ["Carregar multimédia", "Enviar mídia", "Upload media", "Cargar medios"]
)
async def test_upload_option_tooltip(page, label):
    from flow_provider.selectors import control

    await page.set_content(
        f'<div role="dialog"><div role="option">{label}</div><div role="tooltip">{label}</div></div><div hidden role="option">{label}</div>'
    )
    target = await control(page.get_by_role("dialog"), "upload")
    assert await target.get_attribute("role") == "option"
    await target.click()


@pytest.mark.asyncio
async def test_selector_ambiguity_disabled_and_stable_priority(page):
    from flow_provider.selectors import control

    await page.set_content("<button>Upload media</button><button>Upload media</button>")
    with pytest.raises(ValueError):
        await control(page, "upload")
    await page.set_content("<button disabled>Upload media</button>")
    with pytest.raises(ValueError):
        await control(page, "upload")
    await page.set_content(
        '<button data-testid="flow-upload">X</button><button>Upload media</button>'
    )
    assert await (await control(page, "upload")).inner_text() == "X"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "label",
    [
        "Acionador de definições",
        "Gatilho de configurações",
        "Settings trigger",
        "Activador de ajustes",
    ],
)
async def test_settings_locales(page, label):
    from flow_provider.selectors import control

    await page.set_content(
        f'<button aria-label="{label}"></button><div role="tooltip">{label}</div>'
    )
    assert await (await control(page, "settings")).count() == 1


@pytest.mark.asyncio
async def test_auth_states(page):
    from flow_provider.security import auth_state

    await page.set_content("<button>New project</button>")
    assert await auth_state(page, trusted=True) == "authenticated"
    await page.set_content('<a href="https://accounts.google.com/">Sign in</a>')
    assert await auth_state(page, trusted=True) == "login_required"
    await page.set_content("<div>loading</div>")
    assert await auth_state(page, trusted=True) == "unverifiable"
    await page.set_content("<button>New project</button>")
    assert await auth_state(page) != "authenticated"


@pytest.mark.asyncio
async def test_new_model_exact_discovery_and_presubmit(page):
    from flow_provider.safe_ui import verify_configuration, discover_models

    await page.set_content("""<flow-prompt-box-settings>
    <button data-testid="flow-model">Nano Banana 2.1</button>
    <button role="radio" aria-checked="true">9:16</button>
    <button role="radio" aria-checked="true">x1</button>
    </flow-prompt-box-settings>
    <div role="menu"><div role="menuitem">Nano Banana 2</div><div role="menuitem">Nano Banana 2.1</div></div>
    """)
    assert await discover_models(page) == ["Nano Banana 2", "Nano Banana 2.1"]
    assert (
        await verify_configuration(
            page, {"model": "Nano Banana 2.1", "ratio": "9:16", "count": 1}, []
        )
    )["model"] == "Nano Banana 2.1"
    for spec in ({"model": "Nano Banana 2"}, {"ratio": "16:9"}, {"count": 2}):
        with pytest.raises(ValueError):
            await verify_configuration(
                page, {"model": "Nano Banana 2.1", "ratio": "9:16", "count": 1} | spec, []
            )
    with pytest.raises(ValueError):
        await verify_configuration(
            page, {"model": "Nano Banana 2.1", "ratio": "9:16", "count": 1}, ["reference-1"]
        )


@pytest.mark.asyncio
async def test_asset_identity_ambiguity(page):
    from flow_provider.safe_ui import asset_ids, new_asset

    await page.set_content('<flow-tile-container><img data-media-id="old"></flow-tile-container>')
    before = await asset_ids(page)
    await page.set_content(
        '<flow-tile-container><img data-media-id="old"></flow-tile-container><flow-tile-container><img data-media-id="new"></flow-tile-container>'
    )
    with pytest.raises(ValueError, match="lifecycle baseline"):
        await new_asset(page, before, timeout=0.1)
    with pytest.raises(ValueError):
        await new_asset(page, set(), timeout=0.1)
