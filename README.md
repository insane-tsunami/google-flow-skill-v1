# Google Flow Skill — safe durable jobs

> Implementación offline verificada; smoke autenticado pendiente. Los rótulos de modelo en ejemplos no prometen disponibilidad. Cada comando reanuda su manifiesto; nunca repite automáticamente una generación incierta. Cambios de compatibilidad y recuperación: [MAINTENANCE.md](docs/MAINTENANCE.md).

Dile a un agente con terminal local: **“Crea tres imágenes y dos clips sobre esta idea; usa Google Flow y entrégame los archivos.”** El agente prepara los prompts, controla Flow en Chrome, espera la generación y descarga los resultados. También puede ejecutar lotes a partir de un JSON.

Funciona con Claude Code, Codex, OpenCode u otros agentes **cuando se ejecutan en tu equipo con escritorio y Chrome visible**. El requisito es el entorno local, no la marca del agente.

## Qué incluye

- Imagen desde texto o con referencia local.
- Video desde texto, fotograma inicial o fotogramas inicial y final.
- Lotes ordenados de imágenes y videos, con encadenamiento imagen → video.
- Selección de modelo, formato y duración de video compatible con Flow.
- Descarga automática a `outputs/` y reporte `batch_report.json`.

Cada trabajo guarda un resultado. Para diez imágenes, crea diez trabajos `image`; consulta [el ejemplo de lote](examples/lote_imagenes.json). La skill pública entrega **assets de Flow**. Para un Short terminado con montaje, voz y subtítulos, conecta después un editor como Remotion o un pipeline aparte.

## Instalación

Necesitas Python 3.10+, Google Chrome y FFmpeg/ffprobe para video. Lee [la guía de mantenimiento y los gates pendientes](docs/MAINTENANCE.md). Instala en un entorno aislado, sin ejecutar el instalador global legado:

```powershell
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
# Activa .venv antes de ejecutar python flow.py
python flow.py status
python flow.py login
```

`login` abre Chrome para que **tú** inicies sesión. El perfil queda en `session/flowbot-profile/`; nunca lo subas al repositorio ni lo compartas. `status` verifica autenticación real sin generar; perfil presente no implica sesión válida. Si las reglas de tu workspace exigen mostrar o aprobar comandos, el agente debe respetarlas.

Repositorio actual: [BRPLia/google-flow-skill-v1](https://github.com/BRPLia/google-flow-skill-v1). El nombre de la URL conserva “v1”; este código corresponde a la v2.

## Uso rápido

```powershell
python flow.py image --model "Nano Banana 2.1" --prompt "Three distinct paper flowers on a plain table, vertical 9:16" --name flores
python flow.py video --prompt "A gentle breeze moves the paper flowers" --start outputs/flores/flores.png --model "Veo 3.1 - Lite" --duration 8s --name flores_clip
python flow.py batch examples/lote_imagenes.json
```

Para lotes, el agente debe escribir el JSON y ejecutar `batch`; tú no tienes que copiar prompts uno por uno. Los resultados quedan en `outputs/<project>/`. Revisa el reporte del lote para ver éxitos y errores.

## Preguntas frecuentes

**¿Crea imágenes por lotes?** Sí. Cada entrada `image` del JSON genera y descarga una imagen. Puedes mezclar imágenes y videos en el mismo lote.

**¿Sirve para contenido de YouTube?** Sí, para crear las imágenes y los clips. Un video completo también requiere guion, voz si corresponde, edición y exportación. Esta skill no hace ese montaje por sí sola.

**¿Cómo conecto Flow con Remotion y Claude?** Claude dirige `flow.py batch` y recibe rutas de MP4/PNG. Un proyecto Remotion usa esos archivos locales como fuentes y renderiza el video final. Remotion se instala y configura por separado; esta skill no lo incluye.

**¿Por qué no aparece la ventana de Chrome en Antigravity?** Si el código corre en un sandbox remoto, la ventana puede abrirse allí y no en tu escritorio. Usa un ejecutor local con acceso a la pantalla. Claude Code, Codex u OpenCode también necesitan ejecución local para mostrarla; el nombre del agente no garantiza visibilidad.

**¿Es gratis?** La automatización no añade una suscripción propia. Google Flow usa créditos para generar medios; puede haber créditos diarios sin suscripción y el costo depende del modelo. Comprueba los [límites y costos actuales](https://support.google.com/flow/answer/16526234?hl=es-419).

## Archivos

- `flow.py`: CLI pública.
- `SKILL.md`: instrucciones para el agente.
- `flow_provider/`: automatización interna de Flow.
- `examples/`: lotes de ejemplo.
- `session/`: perfil privado de Chrome, excluido de Git.
- `outputs/`: descargas locales, excluidas de Git.

La automatización depende de la interfaz web de Flow y puede requerir mantenimiento cuando Google la cambie.

### Existing projects and local Elements (issue #7)

The following examples are illustrative. Replace the public placeholder ID,
model label and local paths yourself; they are not real account identifiers or
live acceptance evidence. These commands would consume credits when submitted;
they have **not** been executed against Google for this change.

```sh
FLOW_ACCOUNT_INDEX=2 python flow.py image --project-id EXAMPLE_PROJECT_ID \
  --model 'EXACT UI MODEL' --name illustration --prompt 'A landscape' \
  --image ./reference-a.png --image ./reference-b.png --max-credits 1
FLOW_ACCOUNT_INDEX=2 python flow.py video \
  --project-url 'https://flow.google.com/u/2/project/EXAMPLE_PROJECT_ID' \
  --model 'EXACT UI MODEL' --name motion --prompt 'Slow camera movement' \
  --mode elements --image ./reference-a.png --image ./reference-b.png \
  --duration 8s --max-credits 1
```

`--project-id` and `--project-url` select only an explicitly identified existing
project under an explicit `FLOW_ACCOUNT_INDEX`. With neither option, the CLI
keeps its isolated create/resume default. `--project-title 'Exact full title'`
is optional exact verification of the unique visible navigation-header editable
input value (observed current UI), or a unique visible exact heading on older
layouts, never a title lookup. Missing, ambiguous or mismatched evidence blocks.

Batch JSON uses top-level `project_id` **or** `project_url`, optional
`project_title`, and the existing `project` as the **local output folder**.
For example (illustrative, local reference files must exist):

```json
{
  "project": "illustrative_elements",
  "project_id": "EXAMPLE_PROJECT_ID",
  "defaults": {"image_model": "EXACT UI MODEL", "video_model": "EXACT UI MODEL"},
  "jobs": [
    {"type": "image", "name": "still", "prompt": "A landscape", "images": ["./reference-a.png", "./reference-b.png"]},
    {"type": "video", "name": "motion", "prompt": "Slow camera movement", "mode": "elements", "images": ["still", "./reference-b.png"]}
  ]
}
```

Run with `FLOW_ACCOUNT_INDEX=2 python flow.py batch illustrative.json --max-credits 1`.
`images` is an ordered list; legacy JSON `image` remains supported separately.
Video Elements require explicit `mode: "elements"`. **Images must omit `mode`**:
image `--mode elements` and `--mode frames` (and their JSON equivalents) now
fail pure preflight before any browser/profile access, rather than silently
ignoring the option or searching for a video tab. For an image edit with a
saved character, use `image --image ./reference.png --character "Full saved name"`
plus the required model, prompt, name, project and cost arguments above, without
`--mode`. Image references and characters use the direct `+` picker. CLI and
batch preparation never infer a reference mode for images; `defaults` has no
reference-mode setting. Video start/end frames use
`mode: "frames"` (also inferred for legacy start/end jobs), and cannot combine
with Elements or characters. Every job still produces exactly one file.

**Saved characters by exact unique name.** Use `--character "Full saved name"`
(JSON `character`) for image or video. Video requires `--mode elements` and
validates the saved associated voice; optional `--voice "Full voice name"` asserts
that association, it does not replace it with an unrelated voice. Image jobs
ignore associated audio; explicit image voice is invalid. Full DOM labels are
required; ellipses, ambiguity, missing detail/voice/variant evidence and changed
associations block before submit. `--character-id` remains unsupported because
the observed UI does not expose a saved-character ID; preview image IDs are not
character IDs.

Attachment-only live observation verified exact picker row → active character
detail → Include in prompt → character chip with the same row thumbnail. The
chip's generic `Elemento` label is never accepted as identity. Before payment,
the adapter removes only its proven owned chip, rereads the saved details and
reattaches, because Flow hides attached characters from the picker. All other
references, project/account, settings and cost gates still apply. Concurrent
human editing of the same composer is unsupported. No separate portrait/body
variant selector or guarantee of generated voice/body fidelity is offered.
See `docs/CHARACTER-CONTRACT.md` for evidence and limits. This is direct Elements
handling, not Agent generation support; no live generation was tested.

Local reference bytes and explicit project/account/title participate in the
fingerprint. Changed bytes or project requests block resume instead of repeating
a submission. Existing manifests whose old fingerprint lacks these inputs may
fail closed; do not delete them or reset uncertain jobs to force generation.
See [maintenance limits](docs/MAINTENANCE.md) and the local test evidence in
`scratch/issue7-final.md`.
