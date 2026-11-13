# Manutenção e validação segura (#1–#5)

> **Rascunho #12, não instalar:** a atribuição por registros de serviço tem
> mapeamento/download existente validado, mas geração nova fica bloqueada antes
> do clique até existir contrato observado do RPC/slots de geração. Fixtures
> sintéticas não são contrato do serviço real. Ver `SERVICE-RECORDS.md`.

## Instalação isolada

Requer Python **3.10+**, Chrome de desktop e FFmpeg/ffprobe no PATH para vídeos.
Não execute `setup.py` (instalador legado global). Na cópia de desenvolvimento:

```sh
uv venv --python 3.10 .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
```

Os testes usam Chromium efêmero, rede offline/interceptada, fixtures sintéticas,
PNG realmente decodificado por Pillow e MP4 produzido/decodificado por FFmpeg.
`TEST_CHROMIUM` permite indicar o executável local. Nenhum teste acessa uma conta
Google, perfil privado, navegador ativo ou créditos. O sandbox de produção está
ativado inclusive via `chromium_sandbox=True`; o Chromium efêmero dos testes usa
os padrões do Playwright. Em 2026-11-09 o smoke autenticado separado concluiu
uma imagem pela CLI e retomou o mesmo job sem novo submit; detalhes em
`docs/SMOKE-20261109.md`. Testes offline não substituem essa evidência real.

## Operação e compatibilidade

```sh
.venv/bin/python flow.py status
.venv/bin/python flow.py login
.venv/bin/python flow.py image --model 'Nano Banana 2.1' --name cena_01 \
  --prompt 'Uma paisagem' --image referencia.png
.venv/bin/python flow.py batch examples/lote_imagenes.json --max-attempts 3
```

- `status` agora abre exclusivamente o perfil dedicado e verifica estado real,
  sem gerar/criar projeto. Retorna JSON e código 0 só para `authenticated`;
  distingue `profile_missing`, `login_required`, `network_error`, `unverifiable`.
  Uma falha de inicialização/lock é erro operacional, nunca autenticação válida.
- `--model` e `--name` são obrigatórios em geração individual. Modelos são rótulos
  exatos descobertos no menu atual, não uma enum fixa. O exemplo não promete
  disponibilidade de Nano Banana 2.1 ou Omni 1.2 Flash na sua conta.
- Nomes de projeto/job aceitam letras ASCII, números, `_`, `-` (sem caminhos,
  pontos ou normalização silenciosa). Ratios existentes continuam suportados.
- Cada job produz um asset (`count=1`). Os defaults de modelo em JSON são pedidos,
  não afirmações de disponibilidade. `depends_on` e referências por nome só
  apontam para jobs anteriores, concluídos e com arquivo íntegro.
- A mesma entrada, projeto, nome e `--out` retomam o mesmo manifesto; entrada
  diferente com manifesto existente bloqueia. Projetos sem nome usam `batch`,
  não um timestamp que criaria outro lote inadvertidamente.
- Gerações individuais agora ficam em `outputs/<name>/<name>.png|mp4`, com
  `project.json`, `batch_report.json` e recibo do asset. Esta mudança é intencional.
- A API interna antiga dividida em configure/submit/download-latest foi retirada
  da exportação e bloqueada explicitamente. Migrar integrações para
  `Runner(path, jobs, UIAdapter(project_file))`. Nenhum consumidor deve enviar
  prompts diretamente, saltando o checkpoint ou a releitura pré-submit.
- `clean` exige projeto explícito; não há mais limpeza indiscriminada de outputs.
  Nunca use limpeza para destravar um job incerto.

## Seletores e aprovação humana

`selectors.py` concentra rótulos PT-PT/PT-BR/ES/EN. Primeiro atributos estáveis,
depois estrutura, depois papel + nome exato. Só controles visíveis/habilitados;
ambiguidade bloqueia. Configuração/upload/download consultam o componente ativo.
Upload aceita `role=option`; tooltip duplicado é ignorado. Referência precisa de
identidade explícita no chip anexado. Se a UI não a expuser, para antes de gerar.
Não se inventa vínculo por nome de arquivo ou primeira imagem. Alguns estados
anexam automaticamente; outros exigem `Adicionar ao comando`/`Incluir no comando`.

Não remover modais via JavaScript. Direitos de imagem, políticas e aprovação do
agente pertencem ao humano. Se o modo Agente solicitar aprovação, usar **aprovação
única**, nunca “sempre aprovar”. Este adaptador conservador não escolhe esse modo,
nem infere seus custos/duração/resolução a partir do modo direto. Sem bypass de
bloqueios de política. Montagem, áudio editorial e WhatsApp estão fora do escopo.

## Exclusão mútua e privacidade

`FLOW_CHROME_PROFILE` deve ser um perfil **dedicado**, nunca o Chrome pessoal ou o
piloto em uso. Lock de arquivo é mantido pelo kernel, com PID/UID locais. Outro
processo não pode adquirir o mesmo inode; morte do proprietário libera o lock.
O arquivo residual não é apagado; nenhum PID é morto e nenhum `SingletonLock` do
Chrome é removido. Chrome externo ativo pode recusar o lançamento; isso é erro
seguro, não motivo para limpar locks. Diretórios criados são 0700 e arquivos
checkpoint/lock/temporários 0600 em POSIX. Perfil preexistente precisa já estar
protegido; não se percorrem cookies para alterar permissões.

`FLOW_UNSAFE_NO_SANDBOX=true` é exceção explícita apenas para ambientes isolados
sem suporte ao sandbox. Não usar no desktop normal. `FLOW_SESSION_FILE` legado
é rejeitado: faça login humano no perfil dedicado. Não recolher credenciais.
Não imprimir exceções Playwright (podem conter DOM/URLs assinadas), nem salvar
HTML/screenshots automaticamente no novo pipeline. Manifesto guarda hashes,
identificadores e configurações públicas; não guarda prompt, cookies nem URL de
projeto/download. Não comitar perfil, `.env`, recibos, outputs ou diagnóstico.

## Estados, recuperação e limites de retry

O próprio `batch_report.json` é o manifesto incremental versionado, publicado por
`fsync` + rename atômico em cada transição. Estados: `pending`, `configuring`,
`uncertain`, `submitted`, `downloading`, `completed`, `failed`. Não há transação
exactly-once entre Chrome e disco. **Antes do clique** persiste `uncertain`.
Se o processo morrer antes de confirmar a identidade do novo asset, nunca repete
submit automaticamente, mesmo que isso tenha ocorrido antes do clique real.
É a escolha conservadora para evitar duplicação de créditos.

- `completed`: revalida arquivo e SHA-256. Ausência com asset conhecido retoma
  download sem gerar. Corrupção de saída existente bloqueia, sem sobrescrever.
- `submitted/downloading`: retoma download do mesmo asset no projeto persistido.
- `uncertain`: pare e peça decisão humana. Confira no projeto o resultado real.
  Com todos os processos parados e backup local do manifesto, um humano pode
  reconciliar **apenas** o ID do asset correto (`asset`, `state: submitted`).
  Se não houver prova, mantenha incerto; criar novo job exige autorização
  explícita para possível gasto duplicado. Não há reset automático.
- `failed`: terminal por padrão. Após corrigir uma falha conhecida de configuração
  anterior a qualquer submit, o humano pode autorizar explicitamente a retomada
  com `--retry-configuration` em `image`, `video` ou `batch`, mantendo a mesma
  entrada, nome, projeto e `--out`. Não apague o manifesto nem crie outro projeto.
  A opção não integra os jobs nem altera seu fingerprint. Só recupera erros
  `configuration_or_authentication` ou códigos de configuração explicitamente
  permitidos de `safe_ui`, com pelo menos uma tentativa de configuração, sem
  chave de tentativa `submit` (mesmo zero), sem `asset`/`result` e sem saída
  existente. Incerteza, submit, download, integridade e conflitos não autorizam
  nova geração. Todos os contadores são preservados; orçamento esgotado exige
  aumentar explicitamente `--max-attempts` (até 10), sem override da opção.
  O histórico `configuration_recoveries` guarda apenas código público anterior e
  contador de configuração, nunca campos privados de diagnóstico. Cada execução
  autorizada faz no máximo uma nova tentativa de configuração por job.
  Exemplo: `python flow.py batch lote.json --retry-configuration --max-attempts 4
  --max-credits 1` (acrescente `--direct-mode` somente se autorizado). Depois da
  configuração validada, o submit continua sujeito às aprovações normais.
- `pending` com `dependency_unavailable`: o dependente não executou.

Para um único job que já esgotou seu limite original (1–10) e nunca teve
submit, uma autorização humana específica pode usar
`--retry-configuration --max-attempts ORIGINAL --additional-configuration-attempts 1|2`.
É uma única extensão durável, não renovável, somente de configuração: preserva
fingerprint, contadores e histórico, não aumenta downloads nem tentativas pagas.
O marcador persiste o limite original: 2 + 2 = 4, 10 + 2 = 12; reexecução não
acumula extensão e não pode trocar o limite original. Manifestos legados sem
campo de orçamento exigem contador esgotado exatamente igual ao limite explícito.
Exige o mesmo número autorizado em cada retomada; omitir a opção não concede
a extensão. Estado incerto ou pós-submit nunca é reconfigurado. Detalhes e
resultado do smoke em `OMNI-CONTRACT-20261110.md`.

Tentativas de download têm limite persistente 1–10 (`--max-attempts`), backoff
exponencial limitado a 10 s, e são contadas **antes** de executar. A espera pelo
asset conhecido e controle de download é temporária/retryable, não falha terminal
prematura. `generation_timeout` por job tem padrão 180 s e limite finito até 600 s;
o mesmo deadline limita o início e a transferência via navegador. Um recibo local
válido é recuperado **antes** de verificar orçamento esgotado (inclusive limite 1),
sem nova tentativa nem geração. Destino preexistente ou symlink sem asset conhecido
bloqueia antes de configurar/submeter. Recibos com asset, caminho ou hash incorretos
não são recuperados. Configuração
interrompida pode retomar dentro do mesmo orçamento; configuração inválida é
terminal sem a autorização explícita restrita descrita acima. Submit tem no máximo uma tentativa por job. Checkpoint truncado,
manifesto divergente e outputs repetidos bloqueiam. Sobras `.part` não contam
como resultado, nunca são procuradas como fallback.

## Download e publicação

Identidade do asset é diferença única entre IDs observados antes/depois do
submit, com automação exclusiva no perfil. Isso **não** prova autoria se alguém
usar manualmente o mesmo projeto em paralelo: não fazê-lo. Mais de um asset novo
ou ausência de ID mantém o job incerto. Nenhum fallback “mais recente”, CDN por
heurística ou busca em `~/Downloads` permanece.

Download é evento do navegador provocado pelo controle da card do ID conhecido,
em destino isolado, sem confiar no nome sugerido. PNG/JPEG/WebP são verificados
e decodificados. Novas saídas de imagem `.png` são codificadas como PNG real
antes do recibo e da publicação exclusiva; JPEG/WebP são convertidos no staging
isolado (CMYK → RGB, transparência preservada). Tamanho/SHA-256 descrevem os
bytes PNG finais. PNG válido já recebido é preservado byte a byte. Recibos
legados continuam validando o conteúdo original, sem conversão/regravação na
retomada; o artefato JPEG do smoke de 2026-11-09 permanece intocado.
Vídeo exige assinatura MP4/WebM, stream, dimensões, duração
positiva e decodificação FFmpeg. HTML, vazio e truncamentos são rejeitados.
Antes da publicação grava-se recibo sanitizado com ID/tipo/tamanho/SHA-256;
retomada confere o mesmo asset e hash. A saída é publicada atomicamente por
**hard link exclusivo** de temporário validado no mesmo filesystem (sem
sobrescrita concorrente); é intencional em vez de `replace`, que sobrescreveria
outro asset. Requer filesystem com hard links; se não suportado, falha seguro.

## Matriz de evidência / aceitação ainda humana

| Issue | Prova automatizada | Gate externo não executado |
|---|---|---|
| #1 | Chromium PT-PT/PT-BR/ES/EN; CLI real PT-BR texto → imagem → download | Referência real Nano Banana e demais variantes de idioma |
| #2 | Descoberta real Nano Banana 2.1, custo visível 0, releitura pré-submit; drift offline bloqueado | Outros modelos/contas e vídeo reais |
| #3 | Conta /u/1/ autenticada na CLI; locks e sandbox; falhas offline | Sessão expirada/rede real; Windows |
| #4 | Asset real Google baixado, decode/hash/recibo; submenu original 1K real | Vídeo real e demais variantes de submenu |
| #5 | Crash configuração/submit/download, duas retomadas, hash/ausência/corrupção, dependência, limites | Reconciliação humana de resultado incerto real |

Primeira suite adicionada falhou no baseline (20 casos: módulos de segurança
inexistentes); após implementação passou. As duas revisões independentes iniciais
reprovaram problemas concretos; foram acrescentadas regressões RED/GREEN para
preflight dos decoders, Python 3.10, inicialização de projeto, espera de asset,
recuperação no limite 1 e conflitos de destino. O deadline após o evento de download
também teve regressão falhando antes de ser corrigido. A suíte final executada
**diretamente no terminal Hermes**, fora do sandbox Codex, passou **178/178** em
Python 3.14.7 e **178/178** em Python 3.10.22 após as correções do smoke.
O guard de symlink também é testado
pelo entrypoint `prepare_jobs` + `Runner`: validar o caminho lexical **antes** de
resolver evita apagar a identidade de um link para destino ausente, inclusive
links no diretório do projeto. Os dois casos falharam antes da correção e depois
passaram, sem submit ou publicação no destino estrangeiro. Erros de fixture Chromium dentro do
sandbox Codex (`setsockopt: Operation not permitted`) não foram contados como
aprovação; a execução válida usou navegador efêmero offline fora desse sandbox.
Integração sintética não substitui o
smoke da conta. `ci-offline.yml` contém os gates para Python 3.10 e 3.14.
**CI remoto vigente:** o workflow `.github/workflows/offline.yml` está instalado.
A evidência local `outputs/authenticated-smoke-20261109/evidence.json` registra
quatro checks remotos verdes (push/PR, Python 3.10/3.14) no SHA
`6b191dd0f3ff959a610a61c6a237d72249366951`. Isso valida aquele SHA anterior;
as alterações locais PR6 ainda precisam dos próprios checks e revisão.
Não fechar issues nem mergear só por CI: revisão independente e gates humanos
continuam obrigatórios. Para smoke futuro, obter autorização de custo, não tocar
no perfil piloto e usar um perfil de teste humano dedicado. Registrar somente
modelo/configuração/asset sanitizados e integridade, nunca sessão privada.


## PR6: conta, modo direto e aprovação de créditos

`FLOW_ACCOUNT_INDEX=1` navega explicitamente para
`https://flow.google.com/u/1/` (a barra final é necessária na home atual).
Rotas de projeto canônicas `flow.google.com/u/1/project/...` e redirects
`labs.google/fx/tools/flow/u/1/project/...` preservam o escopo. A URL é verificada antes
 de criar projeto, após criação, ao retomar e imediatamente antes do submit.
O índice (inclusive ausência explícita) é capturado no adaptador e passado
aos helpers; mudanças posteriores no ambiente não alteram a conta. Páginas
em cache são verificadas antes de configuração, prompt ou upload.
Autenticação não identifica nem autoriza a conta pedida. Sem variável, o caminho
padrão anterior continua disponível. `project.json` persiste `account_index`;
retomar sob outro índice (inclusive escopo ausente versus explícito) bloqueia
antes de abrir navegador. Projetos legados sem escopo só retomam sem índice
explícito; não atribuir uma conta a eles por inferência.

`--direct-mode` autoriza clicar no botão exato `Agente`/`Agent`, que pode
expor diretamente as configurações, ou oferecer `Direto`/`Direct`. Na UI observada
o mesmo botão permanece visível com `aria-pressed=false`; chamadas repetidas
não o ativam novamente. A barra lateral é fechada somente por seu botão local
`Fechar`, com opt-in, nunca por aprovações de agente. A transição
exige o gatilho de configurações e o painel `flow-prompt-box-settings` com
controle de família de modelos; ausência de Agente sozinha não é prova. Sem opt-in, modo Agente bloqueia com
`agent_mode_requires_direct_mode_opt_in` no relatório sanitizado. O controle
`tune` do agente nunca é interpretado como configurações de modelo. PT-BR usa
`Gatilho de configurações`; PT-PT usa `Acionador de definições`. DOM desconhecido
ou ambíguo permanece bloqueado, inclusive após a transição autorizada.

Todo submit exige `--max-credits N` explícito, finito e não negativo (limite por
job, não orçamento total do lote). Configuração sem aprovação bloqueia antes de
criar projeto. Na UI real observada o custo vem de
`flow-prompt-box-settings > div > flow-credit-cost-label.settings-credit-cost`,
como `A geração vai usar 0 créditos`. É relido antes de fechar o painel e do
submit. O contrato alternativo dedicado `flow-generation-cost` permanece
suportado no compositor ativo, fora de editores, inputs e conteúdo editável, como rótulo
explícito `Generation cost: N credits`, `Custo da geração: N créditos`,
`Custo de geração: N créditos` ou `Coste de generación: N créditos`.
Saldo da conta e preço inferido do modelo não são custo confirmado. Ausência,
ambiguidade, formato desconhecido, custo acima da aprovação ou alteração entre
configuração e submit bloqueiam. Nenhuma exceção para smoke/fixtures.
A extração é deliberadamente restrita; outro formato exige evidência sanitizada
e regressão antes de ampliar suporte. Texto do prompt, saldo da conta e valores
em chips editáveis nunca satisfazem o gate.

Exemplo para um humano autorizado no desktop dedicado:
`FLOW_ACCOUNT_INDEX=1 python flow.py image --model 'RÓTULO EXATO' --name smoke \
--prompt 'Uma paisagem' --direct-mode --max-credits 1`.
Não executar se o custo/modelo/conta não puderem ser verificados. O gate humano
continua: no máximo um submit autorizado, validar decode/hash e retomar sem gerar.
Os testes PR6 usam mocks/Chromium efêmero offline; evidência RED/GREEN local em
`scratch/pr6/`, sem acesso Google nem uso intencional de perfil privado.

Correções de revisão: fixtures DOM Chromium offline em `tests/test_blocker_dom.py`
e `tests/test_live_safe_ui.py`; execução final real fora do sandbox: 178 testes
aprovados em cada versão Python. Erros de lançamento no sandbox Codex não foram
contados como aprovação. A CLI `status` autenticou explicitamente `/u/1/`, e a
CLI de imagem concluiu geração/download/retomada. Ver `docs/SMOKE-20261109.md`.

### Retomada explícita de download conhecido

`--retry-download ASSET_ID` está disponível em `image`, `video` e `batch`, com
padrão `None`, fora dos jobs e do fingerprint. Use a mesma entrada e diretório:
`python flow.py batch lote.json --retry-download 6ccbc008-b60f-4611-9dff-665377e09ba5`.
Só recupera `failed` com esse ID exato validado e erro
`invalid_media_or_identity` ou `download_attempts_exhausted`, `attempts.submit`
inteiro exatamente 1 e `attempts.download` inteiro entre 1 e `max_attempts - 1`.
Saída existente ou symlink bloqueia. O orçamento nunca é reiniciado; aumentá-lo
exige `--max-attempts` explícito, dentro de 1–10. A transição é somente para
`submitted`, preservando asset e tentativas, sem configurar ou submeter novamente.
`download_recoveries` retém apenas código público e contador anterior sanitizados.
Estado incerto, asset diferente, integridade e orçamento esgotado continuam
bloqueados; a opção não substitui validação de recibo/arquivo nem corrige o DOM.

## Issue #7: explicit project and Elements boundaries

Local-only implementation; no Google session, account, profile or paid generation
was used for this change. Examples in README are generic illustrative inputs.
The selected branch is `fix/flow-elements-cli`; no commit/push/PR is part of this work.

- `image`, `video`, `batch`: `--project-id` or `--project-url`, requiring explicit
  `FLOW_ACCOUNT_INDEX`. Canonical URLs accept only the account-scoped Flow/Labs
  origins and project paths, without query/fragment. Title is a separate exact
  project navigation-header editable-input value or unique visible heading
  assertion (`--project-title`), never lookup. Unknown/missing or
  ambiguous title blocks. Account/project are checked after navigation, on cached
  reuse, after uploads and immediately before submit. A persisted target conflict
  blocks before opening a browser. Absence of explicit target retains isolated
  creation. An existing project must not be edited concurrently by a human.
- Repeat `--image` for local references on image/video; JSON uses ordered `images`
  (exclusive with legacy `image`). References can name earlier batch jobs.
  Video references require `mode: elements`; start/end frames cannot combine with
  Elements, characters or explicit Elements mode. Incompatibility fails preflight.
  `mode` is video-only: image `elements` **and** `frames` fail before browser
  startup with guidance to omit `--mode`/JSON `mode`. Image references and saved
  characters attach through the direct `+` picker, not video Elements controls.
  Use `image --image reference.png --character "Full saved name"` with the required
  model/prompt/name and approved project/cost options, without a mode. Single CLI,
  batch preparation and adapter entry all enforce the same pure validation;
  batch defaults do not provide or infer a reference mode. Existing invalid image
  manifests must be preserved, not reset or rewritten to bypass fingerprints.
- Local file SHA-256 values, ordered references, project/account/title, requested
  character, voice and mode enter the durable job fingerprint. Dependency output
  bytes are captured before configuration and checked again before submit; their
  producer job is already included in the manifest fingerprint. Final attached
  IDs must match exactly, and uploads must preserve all previous attached IDs.
  Changed/missing input bytes block; no automatic reset or repeated submit.
- Privacy remains unchanged: report stores only the fingerprint, sanitized state
  and effective settings; no prompt, reference file contents, title or URL is
  added to persisted reports. `project.json` stores only project ID/account.
  Reference hashes are in-memory inputs to the fingerprint. Legacy manifests with
  different fingerprints block; do not migrate by deleting recovery evidence.

### Observed saved-character contract

Authorized attachment-only observation on 2026-11-10 supersedes the initial
read-only limitation. Exact `.asset-title` plus character `.type-subtitle`, a
unique active picker row and its scoped `flow-character-preview-pane` establish
the saved entry. Include in prompt creates a `flow-character-ingredient-chip`
whose image equals the selected row thumbnail. Generic `Elemento` and hover
counts alone are not identity. The saved ID is not exposed; `--character-id`
fails before browser access, while exact-name selection is implemented.

Video validates full associated voice name, description and scoped audio sample;
explicit voice is an assertion, not a replacement selector. Image skips voice.
Pre-submit revalidation removes only the adapter-owned proven chip, rereads the
same unique saved entry and reattaches; already attached entries are absent from
the picker. Clicking an already active option includes it immediately, so the
adapter reads that detail without clicking it. Ambiguous/incomplete search,
missing variant evidence, truncation or association drift fails closed. Private
URLs/IDs are compared only in memory and not persisted. Existing unproved human
attachments are preserved and rejected; adapter-owned retained chips are checked
and removed on the next configuration/retry.

The second variant was previously misidentified as a placeholder. A fresh visual
inspection found an actual full-body front/side/back reference; both images were
loaded. This is an observation of that entry, not a general Body classifier or
a promise of generation fidelity. No separately named portrait/body selector is
offered. `docs/CHARACTER-CONTRACT.md` records acceptance boundaries. No Google
generation or approval was clicked, no prompt was filled and no credits were
spent. Direct Elements/model/cost gates remain required; Agent generation is not
implemented by this change.

### Local validation evidence

`scratch/issue7-red.txt` records the initial five failing tests (one passed).
`scratch/issue7-final.md` records exact commands, outcomes and environment limits.
The first Codex sandbox Chromium launch failed with `setsockopt: Operation not
permitted`; it was not counted as passing validation. Hermes then ran the full
suite outside that sandbox with ephemeral offline Chromium: **242 passed** on
Python **3.10.22** (209.88 s) and **242 passed** on Python **3.14.7** (217.88 s).
Ruff lint/format, compileall and real image/video/batch `--help` passed. A first
independent review returned FAIL (output-path dependency alias and missing mode
recovery allowlist); both have dedicated regressions and fixes. This is offline
functional/safety evidence, not paid Google service acceptance. Read-only DOM
inspection used the already-running browser only, without adding attachments,
changing voice, filling prompts, invoking generation or modifying profile data.

## Passive service attribution (issue #12)

The service contract in [SERVICE-RECORDS.md](SERVICE-RECORDS.md) supersedes the
older DOM-lifecycle attribution description above. The public CLI now seals a
job/configuration intent before click, passively binds an exact outbound single
RPC invocation to its own response's owning record, maps explicit record groups
to a unique gallery tile, and checks the exact scoped output before original
image/video download. It never falls back to DOM node differences, newest cards
or later listProject responses as submit proof. Download resume navigates the
known project's gallery and requires the durable record proof. URLs and raw POST
bodies are not persisted; ordinary media receipts and budget guards are retained.

This contract requires an explicit supported account route and a recognized
nonempty owning-project baseline. Empty/new projects, unknown transport layouts
or submit responses without an owning record remain unsupported and fail closed.
Image info supplies the independent named model. Observed video history has no
independent named-model label: its model proof uses the directly linked record
plus the configuration verified before click, with no guessed model-code mapping
or undocumented parameter slots. Unknown response parameter fields are hashed,
not decoded or represented as independently verified settings.

`flow.py reconcile --report ... --evidence ... --output ...` is a separate
read-only offline audit of independent historical assertions. It accepts the
original exhausted uncertain job without resetting its budget or rewriting any
historical file. It **does not** authenticate the evidence's origin, clear the
uncertainty, authorize a download or resubmit. See the exact schema and limits in
SERVICE-RECORDS.md. The worker performed no live/profile/paid action. Offline
Chromium acceptance must be recorded separately from sandbox launch failures.
