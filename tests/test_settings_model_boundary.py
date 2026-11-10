import pytest
from flow_provider.selectors import control


@pytest.mark.asyncio
async def test_settings_control_never_aliases_model_trigger(page):
    await page.set_content("""<button id="composer-settings" aria-label="Gatilho de configurações">Settings</button>
    <flow-prompt-box-settings><button id="model" aria-label="Selecionar família de modelos"><span class="model-select-trigger-content">🍌 Nano Banana 2.1</span></button></flow-prompt-box-settings>""")
    assert await (await control(page, "settings")).get_attribute("id") == "composer-settings"
    assert (
        await (await control(page.locator("flow-prompt-box-settings"), "model")).get_attribute("id")
        == "model"
    )
