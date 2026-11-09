# Manutenção e validação segura (#1–#5)

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
os padrões do Playwright. O smoke autenticado abaixo **não foi executado**.

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
- `failed`: terminal, inclusive configuração/auth inválida. Corrija a causa e
  peça decisão antes de nova execução. Não apague checkpoints para “tentar”.
- `pending` com `dependency_unavailable`: o dependente não executou.

Tentativas de download têm limite persistente 1–10 (`--max-attempts`), backoff
exponencial limitado a 10 s, e são contadas **antes** de executar. Configuração
interrompida pode retomar dentro do mesmo orçamento; configuração inválida é
terminal. Submit tem no máximo uma tentativa por job. Checkpoint truncado,
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
e decodificados; vídeo exige assinatura MP4/WebM, stream, dimensões, duração
positiva e decodificação FFmpeg. HTML, vazio e truncamentos são rejeitados.
Antes da publicação grava-se recibo sanitizado com ID/tipo/tamanho/SHA-256;
retomada confere o mesmo asset e hash. A saída é publicada atomicamente por
**hard link exclusivo** de temporário validado no mesmo filesystem (sem
sobrescrita concorrente); é intencional em vez de `replace`, que sobrescreveria
outro asset. Requer filesystem com hard links; se não suportado, falha seguro.

## Matriz de evidência / aceitação ainda humana

| Issue | Prova automatizada | Gate externo não executado |
|---|---|---|
| #1 | Chromium PT-PT/PT-BR/ES/EN, option/tooltip/ambiguidades; fluxo sintético referência → geração → download | CLI em conta autenticada, UI PT, referência Nano Banana |
| #2 | Modelo novo/exato/ausente, drift modelo/ratio/count/referência/login, nenhum clique de submit em erro | Descoberta da conta atual e smoke autorizado |
| #3 | Dois processos, morte abrupta/lock residual, Chrome lock sintético preservado, flags sandbox e auth DOM | Login/sessão expirada/rede contra Google real; Windows |
| #4 | Download real Chromium interceptado, nomes repetidos, HTML/asset incorreto, decode PNG/MP4/truncado | Asset real Google e variantes DOM do submenu |
| #5 | Crash configuração/submit/download, duas retomadas, hash/ausência/corrupção, dependência, limites | Reconciliação humana de resultado incerto real |

Primeira suite adicionada falhou no baseline (20 casos: módulos de segurança
inexistentes); após implementação passou. Integração sintética não substitui o
smoke da conta. `ci-offline.yml` contém os gates para Python 3.10 e 3.14.
**CI remoto bloqueado:** o OAuth disponível não tem scope `workflow`; GitHub
rejeitou o push quando o arquivo estava em `.github/workflows/offline.yml`.
SSH também não autenticou. O template foi preservado na raiz para permitir
publicar o restante sem alterar credenciais ou permissões da conta. Um mantenedor
com autorização `workflow` precisa instalar esse template em
`.github/workflows/offline.yml`; depois verificar os checks no SHA real do PR.
Não existe CI remoto aprovado enquanto esse gate não for instalado/executado.
Não fechar issues nem mergear só por CI: revisão independente e gates humanos
continuam obrigatórios. Para smoke futuro, obter autorização de custo, não tocar
no perfil piloto e usar um perfil de teste humano dedicado. Registrar somente
modelo/configuração/asset sanitizados e integridade, nunca sessão privada.
