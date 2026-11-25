# YouTube Automation Pipeline — Python

Pipeline genérico de produção com **exatamente sete skills independentes**, configuração YAML por canal e revisão humana obrigatória de títulos e thumbnails. Gera um MP4 local com áudio, imagens ou B-roll e um manifesto JSON. Python 3.11+, macOS ou Linux, execução local ou em servidor.

Esta é uma migração do [youtube-automation-agent](https://github.com/darkzOGx/youtube-automation-agent), a partir do commit `b9da1af5c5e3cb88a36ac21cb05c792f6878f482`. O runtime Node.js foi substituído; a licença MIT original foi preservada. A análise e o mapeamento estão em [docs/ADAPTACAO.md](docs/ADAPTACAO.md).

## Fluxo

```text
pesquisa_titulos → APROVAÇÃO E SELEÇÃO → thumbnail → APROVAÇÃO E SELEÇÃO
    → roteiro → plano_visual → narracao → imagens → edicao → final.mp4
```

As cinco últimas etapas são automáticas por padrão e aceitam aprovação opcional. Nenhuma opção desativa as duas aprovações obrigatórias. A geração de um roteiro só começa depois de aprovar título e thumbnail.

| Skill | Entrada tipada | Saída adicionada |
|---|---|---|
| `pesquisa_titulos` | `Brief` | `research`: fontes, análise, títulos e justificativas |
| `thumbnail` | `ResearchOutput` com título escolhido | `thumbnail`: variantes, prompts e JPEGs |
| `roteiro` | `ThumbnailOutput` com thumbnail escolhida | `script`: roteiro completo em seções ordenadas |
| `plano_visual` | `ScriptOutput` | `visual_plan`: cenas, prompts em inglês, busca e pesos de duração |
| `narracao` | `VisualOutput` | `narration`: áudio e duração real de cada seção |
| `imagens` | `NarrationOutput` | `assets`: imagens/B-roll, origem e licença declarada |
| `edicao` | `ImagesOutput` | `video`: MP4, dimensões, duração e hash |

Cada saída mantém o contexto tipado da etapa anterior. O orquestrador aplica a escolha humana antes de entregar o JSON à próxima skill. Um agente não pode alterar campos anteriores nem selecionar um candidato em nome do revisor. Os modelos Pydantic rejeitam campos extras, referências desconhecidas, IDs duplicados e cenas sem cobertura do roteiro.

## Instalação

Clone o projeto completo, incluindo pipeline e dashboard:

```bash
git clone https://github.com/andersonroccha21-hub/youtube-automation-agent.git
cd youtube-automation-agent
```

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock
```

Instale **FFmpeg e ffprobe**, disponíveis no mesmo pacote:

```bash
# macOS
brew install ffmpeg
# Ubuntu / DigitalOcean
sudo apt-get update
sudo apt-get install -y ffmpeg python3-venv
```

Para desenvolvimento e o comando global opcional:

```bash
pip install -e '.[dev]'
youtube-pipeline --help
```

## Dashboard web local

O dashboard Darklab Studio acompanha as sete skills, permite iniciar vídeos, selecionar o canal, aprovar títulos e thumbnails, solicitar revisões e assistir ao vídeo final. O frontend é HTML, JavaScript e Tailwind CSS compilado localmente; o backend usa FastAPI. O CLI continua disponível com os mesmos comandos.

Depois de instalar as dependências, execute **na pasta do projeto**:

```bash
python -m uvicorn web.app:app --host 127.0.0.1 --port 8000
```

Abra [http://localhost:8000](http://localhost:8000). O CSS já acompanha o projeto; Node.js e acesso a CDN não são necessários para usar o dashboard.

1. Selecione um canal descoberto em `channels/`.
2. Digite o tema e escolha **Demonstração** ou **Produção**. Demonstração é explicitamente selecionada no formulário inicial e usa conteúdo sintético sem chamadas pagas.
3. Clique em **Iniciar pipeline**. A execução continua em segundo plano e a tela atualiza o estado automaticamente.
4. Em **Aprovar título**, selecione uma proposta e informe seu nome de revisor.
5. Em **Aprovar thumbnail**, veja as imagens, selecione uma variante e aprove.
6. Acompanhe as etapas restantes. Quando terminar, o vídeo aparece no player com opção de download.

Também são respeitadas as aprovações opcionais do YAML. Para solicitar outra versão, preencha os ajustes e clique em **Solicitar revisão**; a etapa e as seguintes serão refeitas, com novas aprovações quando necessário. Clicar numa etapa com resultado abre seu JSON para inspeção.

### Canais, progresso e persistência

- Os arquivos `.yaml` e `.yml` são lidos recursivamente de `channels/`. Cada um precisa ter `channel.id` único. Configurações inválidas ou duplicadas são indicadas na tela.
- Para usar outra pasta, defina `YOUTUBE_CHANNELS_DIR` antes de iniciar o servidor.
- O histórico inclui execuções criadas tanto pelo dashboard quanto pelo CLI, dentro do `output_root` de cada canal.
- O servidor usa um worker local e uma fila limitada; uma execução não pode ser iniciada duas vezes simultaneamente pelo dashboard. O lock do orquestrador também protege contra concorrência com o CLI.
- O progresso conta etapas concluídas: uma etapa que aguarda aprovação só entra na contagem depois da decisão. A porcentagem representa etapas, não uma estimativa do tempo restante.
- O dashboard usa a configuração original salva na execução ao retomá-la. Alterações no YAML são usadas em novas execuções. Mantenha o `channel.id` e `output_root` para descobrir as execuções anteriores.
- Reiniciar o servidor preserva os checkpoints e decisões. Uma execução interrompida não é reiniciada automaticamente; use **Retomar execução** após conferir seu estado.
- Ao aprovar pelo dashboard, a execução continua automaticamente. Pelo CLI, aprovar e retomar continuam sendo comandos separados.

O servidor foi preparado para uso local, sem autenticação de usuários. Mantenha o bind em `127.0.0.1`; o modo web não publica arquivos nem faz upload para YouTube. A API limita mídias aos artefatos registrados na execução e verifica sua integridade. O pedido de aprovação inclui o hash da versão exibida, recusando decisões sobre versões antigas.

### API do dashboard

Documentação interativa em [http://localhost:8000/docs](http://localhost:8000/docs).

| Método | Endpoint | Uso |
|---|---|---|
| GET | `/api/channels` | Canais e prontidão para produção |
| GET | `/api/channels/{canal}/runs` | Histórico do canal |
| POST | `/api/runs` | Iniciar execução: `channel_id`, `topic`, `demo` |
| GET | `/api/channels/{canal}/runs/{execucao}` | Progresso, revisão pendente e vídeo |
| POST | `/api/channels/{canal}/runs/{execucao}/approve` | Aprovar/rejeitar a versão exibida |
| POST | `/api/channels/{canal}/runs/{execucao}/revise` | Refazer uma etapa com feedback |
| POST | `/api/channels/{canal}/runs/{execucao}/resume` | Retomar uma execução interrompida |
| GET | `/api/channels/{canal}/runs/{execucao}/checkpoints/{etapa}` | Resultado JSON de uma skill |
| GET | `/api/channels/{canal}/runs/{execucao}/media/{caminho}` | Visualizar mídia ou reproduzir vídeo |

Para alterar o frontend e recompilar Tailwind:

```bash
cd web
npm ci
npm run build:css
```

O código fica em `web/static/index.html` e `web/static/app.js`; os estilos de origem estão em `web/theme.css`. O comando gera `web/static/styles.css`. Execute somente um worker Uvicorn para manter a fila local única.

## Primeiro teste sem API ou cobrança

```bash
python main.py --channel channels/canal_exemplo/config.yaml --validate
python main.py --channel channels/canal_exemplo/config.yaml --check --demo
python main.py --channel channels/canal_exemplo/config.yaml --demo --topic "Tema de teste"
```

`--demo` utiliza títulos e roteiros sintéticos, cartões visuais identificados e um tom de áudio de teste, **sem TTS nem pesquisa real**. A edição usa FFmpeg de verdade. O arquivo final chama-se `final.demo.mp4`; o manifesto contém `demo: true`. Os pontos de aprovação continuam ativos.

No terminal interativo, leia as opções e digite `approve`, seu nome e o ID escolhido. Para thumbnails, abra os JPEGs cujos caminhos aparecem no terminal antes de aprovar. Qualquer outra entrada deixa a execução pausada.

Sem terminal interativo, o processo salva o estado e termina com código **2**. Isso significa “aguardando revisão”, não uma falha. Copie o caminho exibido como `Run directory` e use o fluxo abaixo.

## Aprovação persistida e retomada

```bash
RUN_DIR="runs/canal_exemplo/ID_EXIBIDO_PELO_COMANDO"

python main.py --channel channels/canal_exemplo/config.yaml --run-dir "$RUN_DIR" --status

# Após revisar os títulos, selecione um ID existente, por exemplo t2:
python main.py --channel channels/canal_exemplo/config.yaml --run-dir "$RUN_DIR" \
  --approve pesquisa_titulos --select t2 --reviewer "Seu nome"

# Gera thumbnails e pausa novamente:
python main.py --channel channels/canal_exemplo/config.yaml --run-dir "$RUN_DIR"

# Abra as imagens e escolha um ID existente, por exemplo thumb1:
python main.py --channel channels/canal_exemplo/config.yaml --run-dir "$RUN_DIR" \
  --approve thumbnail --select thumb1 --reviewer "Seu nome"

# Continua as cinco etapas restantes:
python main.py --channel channels/canal_exemplo/config.yaml --run-dir "$RUN_DIR"
```

Os IDs são retornados por cada skill; `t2` e `thumb1` acima são apenas exemplos. Gravar uma decisão não executa nem cobra etapas seguintes. É necessário retomar explicitamente com `--run-dir`. Ao retomar uma demonstração, o modo é lido do estado; não é preciso repetir `--demo`.

As decisões incluem revisor, horário UTC, ID escolhido e hash do JSON revisado. Os hashes dos arquivos referenciados também são conferidos. Se o conteúdo mudar, a aprovação anterior não serve para a nova versão. A identificação do revisor é autodeclarada; controle o acesso ao diretório e ao servidor. Não há serviço de autenticação ou assinatura criptográfica de decisões.

### Rejeitar e refinar

```bash
python main.py --channel channels/canal_exemplo/config.yaml --run-dir "$RUN_DIR" \
  --reject thumbnail --reviewer "Seu nome" --feedback "Simplifique a composição e aumente o foco."

python main.py --channel channels/canal_exemplo/config.yaml --run-dir "$RUN_DIR" \
  --revise thumbnail --feedback "Simplifique a composição e aumente o foco."

python main.py --channel channels/canal_exemplo/config.yaml --run-dir "$RUN_DIR"
```

`--revise` também pode ser usado diretamente para refazer uma etapa concluída. Remove seus checkpoints, arquivos e aprovações e os de todas as etapas seguintes; preserva as anteriores. As novas propostas precisam de nova revisão. O feedback entra nos prompts das etapas generativas. Para edição ou áudio importado, altere as configurações/arquivos na origem e inicie uma nova execução quando necessário.

### Aprovação opcional

```yaml
approvals:
  mode: file
  optional:
    roteiro: true
    plano_visual: true
    narracao: false
    imagens: false
    edicao: true
```

Para uma etapa sem candidatos: `--approve roteiro --reviewer "Seu nome"`, sem `--select`. Mesmo se `optional.pesquisa_titulos` ou `optional.thumbnail` receber `false`, esses dois pontos continuam obrigatórios.

## Configurar um novo canal

```bash
mkdir -p channels/meu_canal
cp channels/canal_exemplo/config.yaml channels/meu_canal/config.yaml
```

1. Defina um `channel.id` único, nome, nicho, público, idioma, tom, estética, regras e duração desejada.
2. Configure os modelos/endpoints de texto, imagens e voz. Nomes de modelos no exemplo são configuráveis; confirme o acesso e os parâmetros suportados pelo seu provedor.
3. Forneça fontes de pesquisa reais ou ative a pesquisa YouTube.
4. Defina o modo de aprovação e as revisões opcionais.
5. Valide o arquivo e as dependências antes de começar.

```bash
export OPENAI_API_KEY="sua-chave"
python main.py --channel channels/meu_canal/config.yaml --validate
python main.py --channel channels/meu_canal/config.yaml --check
python main.py --channel channels/meu_canal/config.yaml --topic "Tema do vídeo"
```

O comando aceita qualquer caminho YAML, inclusive `--channel canais/meu_canal/config.yaml`. Não existe cadastro de canais no código. Saídas ficam em `output_root/channel.id/run_id`, com isolamento por canal e execução. Todos os caminhos do YAML são relativos à pasta do próprio arquivo, independentemente do diretório de onde o comando é executado.

O CLI lê chaves das variáveis de ambiente. `.env.example` é uma referência; o CLI não carrega `.env` automaticamente. Não grave chaves no YAML, nos prompts ou no Git. `--check` verifica presença de chaves, binários e arquivos locais; não testa acesso ou saldo dos provedores.

### Pesquisa de nicho e fontes

O exemplo começa com `sources: []` para não fornecer evidência fictícia. Em produção, isso causa um erro explícito até você preencher fontes reais ou ativar YouTube. Para pesquisa editorial com material fornecido:

```yaml
research:
  provider: provided
  title_count: 3
  sources:
    - id: fonte_1
      title: "Título real da fonte que você leu"
      url: "https://dominio-da-fonte.example/artigo"
      excerpt: "Substitua este exemplo pelo trecho factual relevante que você verificou."
```

O bloco acima é um **modelo de preenchimento**, não evidência. O adaptador `provided` usa os trechos fornecidos; não acessa automaticamente as páginas. O modelo só pode referenciar IDs desse catálogo.

Para buscar cobertura do nicho no YouTube:

```yaml
research:
  provider: youtube
  youtube_api_key_env: YOUTUBE_API_KEY
  region: BR
  queries: ["consulta alinhada ao nicho", "outra dúvida do público"]
  max_results: 10
  title_count: 3
  sources: []
```

Exporte `YOUTUBE_API_KEY` e habilite YouTube Data API v3. A pesquisa coleta títulos, descrições e URLs reais. Esses sinais mostram cobertura temática; não comprovam fatos, tendências, CTR ou demanda quantitativa. Fontes editoriais em `sources` podem complementar os resultados. O roteiro deve apoiar suas afirmações no material fornecido; a revisão factual continua necessária.

### Provedores

O adaptador de texto utiliza `POST /chat/completions`, com JSON validado localmente contra o esquema da skill. Aceita OpenAI e serviços compatíveis configurando `base_url`, `model` e `api_key_env`. Se o serviço não oferecer `response_format`, use `text.json_mode: false`; a validação local continua obrigatória. Não há adaptação nativa da API Gemini/Anthropic; use um gateway compatível ou implemente um adaptador.

Imagens usam `POST /images/generations` (resposta base64 ou URL HTTPS); voz usa `POST /audio/speech` com saída WAV. Configure cada endpoint separadamente. A compatibilidade de texto não implica que o mesmo serviço ofereça imagens ou TTS. `image.size` precisa ser aceito pelo modelo; os arquivos gerados são convertidos para o tamanho final configurado. Thumbnails têm 1280×720.

Para modelos de voz que suportam instruções, configure `speech.instructions`. Nesse caso, o pedido inclui idioma, tom e `prompts.narracao`. Deixe o campo ausente em modelos que não o suportam. Voz e velocidade vêm de `speech.voice` e `speech.speed`. As seções têm até 3500 caracteres para limitar o tamanho de cada chamada TTS.

Não há retentativa automática de POST pago: um timeout pode ocorrer depois de o provedor cobrar. Revise a situação e retome a execução conscientemente. Etapas já concluídas são reutilizadas; uma etapa que falhou antes de gravar seu checkpoint pode repetir chamadas parciais ao retomar. Em produção não há fallback silencioso para mídias demonstrativas.

Referências dos contratos HTTP: [texto](https://developers.openai.com/api/reference/resources/chat), [imagens](https://developers.openai.com/api/reference/resources/images), [voz](https://developers.openai.com/api/reference/resources/audio/subresources/speech/methods/create).

### Áudio local e biblioteca de B-roll

É possível importar áudio gravado ou gerado por outra ferramenta. Ative aprovação de `roteiro`, veja os IDs das seções e configure os arquivos antes de criar a execução definitiva:

```yaml
narration:
  provider: files
  files:
    abertura: assets/abertura.wav
    desenvolvimento: assets/desenvolvimento.wav
    encerramento: assets/encerramento.wav
media:
  provider: library
  library:
    - path: assets/experimento.mp4
      tags: ["experimento", "laboratório"]
      license: "Material próprio"
      source: "Acervo do canal"
    - path: assets/diagrama.jpg
      tags: ["diagrama", "explicação"]
      license: "Material próprio"
      source: "Acervo do canal"
```

Os IDs de `narration.files` precisam corresponder exatamente às seções. Você pode manter caminhos de destino definidos no YAML e preencher os arquivos enquanto o pipeline está pausado no roteiro; sua existência será conferida ao gerar a narração. Se mudar o YAML, inicie outra execução.

Na biblioteca, a seleção usa correspondência entre `scene.search_terms` e `tags`, respeitando `media_type`. Empates seguem a ordem da configuração. Ausência de correspondência interrompe a etapa, em vez de escolher mídia aleatória. Vídeos curtos são repetidos e seu áudio original é descartado. O provedor `generated` gera somente imagens estáticas; vídeos devem vir da biblioteca. A licença é uma declaração do catálogo, não uma verificação automática de direitos.

## Checkpoints e recuperação

```text
runs/<channel.id>/<run_id>/
  state.json                  # Config resolvida, decisões e hashes dos checkpoints
  checkpoints/<skill>.json     # Saída tipada de cada skill
  assets/<skill>/              # Arquivos por etapa
  timeline.json                # Cenas alinhadas à narração e aos frames
  result.json                 # Manifesto cumulativo final
  final.mp4                   # Ou final.demo.mp4
```

O `state.json` guarda a escolha humana; os checkpoints de propostas de títulos/thumbnails permanecem sem seleção. A escolha é aplicada pelo orquestrador ao preparar a entrada seguinte. Não edite esses arquivos para aprovar ou revisar: use o CLI.

Gravações JSON são atômicas e operações na mesma execução usam bloqueio de processo (`flock`). Retomar reutiliza checkpoints cujo JSON, contexto anterior e arquivos ainda correspondem aos hashes. Mudanças no YAML ou no tópico exigem uma execução nova, evitando misturar configurações. Canais e execuções distintos podem rodar em processos separados; não há fila distribuída nem suporte a locks entre múltiplas máquinas em armazenamento remoto.

A montagem ordena as seções, distribui a duração real do áudio entre as cenas pelos pesos, arredonda os limites visuais por frames e codifica a narração completa uma única vez. Isso evita acumular pausas de AAC entre cenas. O resultado usa H.264/AAC, `yuv420p`, corte proporcional para preencher a tela e `faststart`. A duração solicitada é um alvo para o roteiro; a duração final vem do áudio real.

Códigos de saída: `0` sucesso/decisão registrada, `2` aprovação pendente, `1` erro ou rejeição, `130` interrupção. Se uma chamada externa falhar, corrija a causa e retome com `--run-dir`. Se um checkpoint/mídia estiver alterado ou inválido, use `--revise <etapa>`.

## Executar uma skill isolada

Cada skill implementa `Skill.__call__(entrada_tipada, Context)` e pode ser importada sem o orquestrador. O CLI também aceita JSON de entrada/saída explícitos:

```bash
mkdir -p scratch
printf '%s\n' '{"topic":"Tema de teste"}' > scratch/brief.json
python main.py --channel channels/canal_exemplo/config.yaml \
  --skill pesquisa_titulos --input scratch/brief.json \
  --output scratch/research.json --assets-dir scratch/artifacts --demo
```

Esse comando é para desenvolvimento ou integração de uma etapa; não executa o pipeline nem registra aprovações. Para encadear a produção com revisão obrigatória, use sempre o orquestrador. Skills isoladas não podem gravar diretamente na raiz de uma execução orquestrada. As entradas seguintes precisam conter as seleções aprovadas e apontar para o mesmo diretório de artefatos.

Para exportar os contratos de configuração, entradas e saídas:

```bash
python scripts/export_schemas.py
```

## DigitalOcean / Docker

Um Droplet Ubuntu com CPU pode executar o pipeline; GPU não é necessária. O tempo de render e o espaço em disco dependem da duração, resolução e quantidade de cenas. Instale Docker Engine e Compose seguindo a documentação oficial, envie o projeto e configure seu canal.

```bash
cp .env.example .env
# Preencha .env com as chaves; configure approvals.mode: file no YAML.
mkdir -p runs
# O contêiner executa com UID 10001:
sudo chown 10001:10001 runs
docker compose build
docker compose run --rm pipeline --channel channels/meu_canal/config.yaml
```

O processo termina ao aguardar aprovação; os volumes preservam o estado. Abra os arquivos de revisão copiando-os por SSH/SFTP, ou use o ambiente gráfico de sua escolha. Os caminhos usados dentro do contêiner começam em `/app`:

```bash
docker compose run --rm pipeline --channel channels/meu_canal/config.yaml \
  --run-dir /app/runs/meu_canal/ID_DA_EXECUCAO \
  --approve pesquisa_titulos --select t1 --reviewer "Seu nome"

docker compose run --rm pipeline --channel channels/meu_canal/config.yaml \
  --run-dir /app/runs/meu_canal/ID_DA_EXECUCAO
```

Repita a revisão para thumbnails. Não configure reinício automático para contornar o código 2; ele representa uma pausa intencional. Mantenha `runs` persistente e faça backup se o Droplet for descartável. Não é necessário expor portas: a operação é pelo CLI/SSH.

Também é possível usar diretamente Python em um ambiente virtual no servidor, com os mesmos comandos locais.

## Testes e extensão

```bash
pip install -e '.[dev]'
ruff check .
ruff format --check .
pytest -q
```

Os testes cobrem decisões obrigatórias/opcionais, rejeição, revisão, retomada, isolamento por canal, integridade, contratos, pesquisa YouTube simulada, adaptadores HTTP simulados, narração local, biblioteca com imagem/B-roll e renderização/decodificação real de MP4. Nenhuma chave real é usada. O CI instala FFmpeg e testa Python 3.11–3.13.

Para trocar uma integração, implemente o adaptador em `pipeline/providers` e injete-o pelo `Context`. Para mudar o comportamento de uma skill, mantenha seus contratos em `pipeline/models.py` e a preservação dos campos anteriores. As sete skills são registradas explicitamente em `pipeline/registry.py`; aprovações ficam no orquestrador, não nos prompts.

Este escopo termina na produção do vídeo. O dashboard Express original foi substituído pelo novo dashboard FastAPI descrito acima. Upload, analytics, SEO e scheduler do projeto antigo não foram portados nem executados. Podem ser integrados posteriormente como serviços externos, preservando as sete skills de produção.
