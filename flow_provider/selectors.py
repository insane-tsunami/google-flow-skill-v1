"""Fail-closed controls. All locale fallbacks live here, never in workflows."""

import re

LABELS = {
    "settings": [
        "Acionador de definições",
        "Gatilho de configurações",
        "Settings trigger",
        "Settings",
        "Botón de configuración",
        "Activador de ajustes",
    ],
    "add": [
        "Adicionar ingredientes à caixa de comandos",
        "Adicionar elementos à caixa de comando",
        "Add ingredients to prompt",
        "Add elements",
        "Adicionar elementos",
        "Añadir elementos",
        "Agregar elementos",
        "Add to prompt",
        "Añadir",
        "Agregar",
        "Crear",
    ],
    "upload": [
        "Carregar multimédia",
        "Enviar mídia",
        "Upload media",
        "Cargar medios",
        "Cargar contenido multimedia",
        "Subir archivo multimedia",
        "Subir imagen",
    ],
    "confirm": [
        "Adicionar ao comando",
        "Incluir no comando",
        "Add to prompt",
        "Add to instruction",
        "Include in prompt",
        "Incluir no prompt",
        "Incluir en la petición",
        "Agregar a la instrucción",
        "Añadir a petición",
    ],
    "model": [
        "Selecionar família de modelos",
        "Selecionar a família de modelos",
        "Select model family",
        "Seleccionar familia de modelos",
    ],
    "home": ["Página inicial", "Início", "Home", "Inicio"],
    "new_project": [
        "Novo projeto",
        "Projeto novo",
        "New project",
        "Proyecto nuevo",
        "Nuevo proyecto",
    ],
    "image": ["Imagem", "Image", "Imagen"],
    "video": ["Vídeo", "Video"],
    "frames": ["Fotogramas", "Frames"],
    "ingredients": ["Ingredientes", "Ingredients"],
    "elements": ["Elementos", "Elements"],
    "portrait": ["Retrato", "Portrait"],
    "body": ["Corpo", "Cuerpo", "Body"],
    "voice": ["Voz", "Voice"],
    "initial": ["Início", "Inicio", "Start", "Iniciar"],
    "final": ["Fim", "Fin", "End"],
    "download": ["Transferir", "Baixar", "Descarregar", "Download", "Descargar"],
    "more": ["Mais opções", "More options", "Más opciones"],
    "login": ["Iniciar sessão", "Fazer login", "Sign in", "Iniciar sesión"],
}
STRUCTURE = {
    "settings": "button:has(span.model-select-trigger-content):not(flow-prompt-box-settings *), button.settings-trigger:not(flow-prompt-box-settings *)",
    "add": "button.add-menu-trigger",
    "model": "button:has(span.model-select-trigger-content)",
    "more": 'button:has(:is(i,mat-icon):text-is("more_vert"))',
    "download": ':is(button,[role="menuitem"]):has(:is(i,mat-icon):text-is("download"))',
    "submit": 'button:has(> :text-is("arrow_forward"))',
    "editor": 'flow-rich-text-editor [contenteditable="true"], .ProseMirror[contenteditable="true"]',
}
ROLES = {
    "upload": ["option", "button", "menuitem"],
    "image": ["radio", "tab", "button"],
    "video": ["radio", "tab", "button"],
    "frames": ["radio", "tab", "button"],
    "ingredients": ["radio", "tab", "button"],
    "elements": ["radio", "tab", "button"],
    "download": ["menuitem", "button"],
    "login": ["button", "link"],
}


def pattern(key):
    return re.compile(r"^\s*(?:" + "|".join(re.escape(x) for x in LABELS[key]) + r")\s*$", re.I)


async def unique(locator, *, optional=False):
    matches = [
        item for item in await locator.all() if await item.is_visible() and await item.is_enabled()
    ]
    if len(matches) != 1:
        if optional and not matches:
            return None
        raise ValueError(f"Control unresolved or ambiguous ({len(matches)} actionable targets)")
    return matches[0]


async def control(scope, key, *, optional=False):
    for locator in [
        scope.locator(f'[data-testid="flow-{key}"]'),
        scope.locator(STRUCTURE.get(key, ":not(*)")),
    ]:
        result = await unique(locator, optional=True)
        if result is not None:
            return result
    if key in LABELS:
        locator = scope.get_by_role(ROLES.get(key, ["button"])[0], name=pattern(key))
        for role in ROLES.get(key, ["button"])[1:]:
            locator = locator.or_(scope.get_by_role(role, name=pattern(key)))
        return await unique(locator, optional=optional)
    if optional:
        return None
    raise ValueError("Control not identifiable")
