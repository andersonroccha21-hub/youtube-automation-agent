# Análise e plano de adaptação

Baseline analisado: [darkzOGx/youtube-automation-agent no commit b9da1af](https://github.com/darkzOGx/youtube-automation-agent/tree/b9da1af5c5e3cb88a36ac21cb05c792f6878f482), versão declarada `2.12.0`. A inspeção foi feita antes da implementação, a partir de um clone público completo.

## Estrutura anterior

O projeto era JavaScript CommonJS, com `index.js` como servidor Express, integração de serviços e executor de jobs. `package.json` exigia Node.js e incluía SQLite, Google APIs, OpenAI, Playwright, Sharp e provedores de mídia. Existiam sete agentes, mas suas responsabilidades não correspondiam às sete skills solicitadas.

| Origem | Responsabilidade encontrada | Decisão na migração |
|---|---|---|
| `agents/content-strategy-agent.js` | Pesquisa YouTube/concorrentes e estratégia editorial | Portar o padrão de catálogo de evidências para `pesquisa_titulos`; extrair parâmetros globais para YAML |
| `agents/script-writer-agent.js` | Roteiro, título, seções e referências | Reescrever `roteiro` com contratos estritos; a escolha do título passa a ocorrer antes e depende do humano |
| `agents/thumbnail-designer-agent.js` | Conceitos, prompts, geração e variantes | Reescrever `thumbnail` para receber o título aprovado e pausar antes do roteiro |
| `agents/production-management-agent.js` | Narração, elementos visuais, legendas e montagem | Decompor em `plano_visual`, `narracao`, `imagens` e `edicao` |
| `agents/seo-optimizer-agent.js` | Metadata/SEO | Fora das sete skills de produção pedidas; não entra no runtime Python |
| `agents/publishing-scheduling-agent.js` | Upload e agendamento | Fora do escopo de produção; removido do fluxo ativo |
| `agents/analytics-optimization-agent.js` | Métricas e otimização | Serviço futuro, fora do pipeline solicitado |
| `utils/ai-text-service.js` | Seleção de provedores e modelos por credenciais globais | Reaproveitar a ideia de compatibilidade HTTP; usar adaptador Python com modelo/endpoint por canal |
| `utils/media-generation-service.js`, `ai-video-generator.js`, `video-providers.js` | Geração de mídias e integração com renderizadores | Separar adaptadores e política; implementar imagem, TTS e biblioteca de B-roll |
| `utils/ffmpeg.js` | Localização do binário, execução e inspeção | Portar o padrão de subprocesso sem shell e inspeção real por ffprobe |
| `utils/generation-recovery-service.js` | Checkpoints, validação e retomada | Reaproveitar o padrão; persistir JSON atômico e hashes, sem repetir automaticamente POSTs pagos |
| `database/db.js` | Estado, jobs e configurações globais em SQLite | Substituir por estado por execução, suficiente para o CLI local/servidor e fácil de inspecionar |
| `dashboard/`, `schedules/`, `oauth-server.js` | Interface, agendamento e autenticação YouTube | Não portados; o novo escopo termina no MP4 e não depende de OAuth de upload |

“Reaproveitar” aqui significa preservar ou portar padrões e responsabilidades úteis. O runtime e os módulos executáveis são Python; nenhum agente JavaScript é chamado por subprocesso. O histórico Git original está preservado no clone de trabalho, e a licença MIT acompanha a entrega.

## Problemas de encaixe na arquitetura solicitada

- Narração, planejamento visual e edição estavam acoplados ao agente de produção.
- As etapas do checkpoint original eram `strategy`, `script`, `thumbnail`, `seo`, `production`, `quality_review`.
- A revisão posterior à geração não fornecia os dois bloqueios exigidos antes de escrever o roteiro.
- Vários parâmetros dependiam de `process.env` e de um estado global do servidor, dificultando o isolamento por configuração de canal.
- Objetos JavaScript sem contratos estritos de fronteira não atendiam à passagem JSON limpa e tipada solicitada.
- Manter o servidor Node como dependência violaria a intenção de um núcleo modular em Python.

O repositório original já trazia configuração editorial e algumas proteções de revisão; a adaptação não parte da suposição de que ele estivesse preso a um único canal. A mudança concentra todo o comportamento de cada canal em um YAML e separa suas execuções.

## Plano apresentado antes do código

1. Reescrever o núcleo em Python, preservando a licença e documentando a origem.
2. Definir modelos de entrada/saída e validar a configuração YAML.
3. Criar exatamente as sete skills solicitadas, com interface independente.
4. Implementar orquestrador sequencial e seleção humana de títulos e thumbnails.
5. Persistir checkpoints e decisões para pausa/retomada em servidor sem terminal.
6. Adicionar provedores configuráveis, mídias locais e montagem FFmpeg.
7. Verificar contratos, integridade, isolamento e um vídeo real em testes sem cobrança.
8. Documentar novo canal, operação, extensão e implantação em DigitalOcean.

O plano foi executado na estrutura abaixo:

```text
main.py
pipeline/
  approvals.py
  cli.py
  config.py
  models.py
  orchestrator.py
  preflight.py
  registry.py
  skill.py
  storage.py
  providers/
    api.py
    media.py
    research.py
skills/
  pesquisa_titulos/{__init__.py,SKILL.md}
  thumbnail/{__init__.py,SKILL.md}
  roteiro/{__init__.py,SKILL.md}
  plano_visual/{__init__.py,SKILL.md}
  narracao/{__init__.py,SKILL.md}
  imagens/{__init__.py,SKILL.md}
  edicao/{__init__.py,SKILL.md}
channels/canal_exemplo/config.yaml
schemas/
scripts/export_schemas.py
tests/
deploy/Dockerfile
compose.yaml
requirements.lock
pyproject.toml
README.md
```

## Decisões e limites

- Sequência fixa solicitada, com extensão por adaptadores e configuração; sem criar agentes extras.
- JSON cumulativo para manter o contexto aprovado sem consultas implícitas a um banco global.
- Aprovação independente de prompts, vinculada a versões e conferida novamente na retomada.
- `flock` protege processos na mesma máquina; não é um coordenador distribuído entre servidores.
- Pesquisa YouTube usa metadados reais, sem fabricar volume de demanda ou checagem factual.
- A geração de vídeo por serviços remotos e o amplo catálogo de provedores antigos não foram portados. Há geração de imagens e seleção de B-roll local.
- Arquivos `.env`, modelos, vozes, estética e regras são configuráveis; não há nomes de canais de produção no código.
- O modo demo é explícito; nenhuma falha em produção é substituída silenciosamente por conteúdo de teste.
- O ambiente disponível validou Python/FFmpeg. Não houve chamada paga, publicação, implantação remota ou execução de Docker.

## Extensão posterior: dashboard web 3.1

Foi adicionada uma interface FastAPI em `web/app.py`, com worker em `web/runner.py` e HTML/JS/Tailwind em `web/static/`. A interface usa os mesmos checkpoints, decisões e locks do pipeline existente; não introduz novas skills.

O orquestrador passou a aceitar `run(interactive=False)` para pausar sem ler stdin no servidor e um hash esperado opcional em `decide(...)` para vincular a aprovação à versão exibida na tela. Os valores padrão preservam o comportamento anterior do CLI. Erros de sintaxe YAML agora são reportados como erros de configuração, permitindo que o dashboard liste os outros canais válidos.

O worker mantém uma fila local limitada, executa uma produção por vez e não reinicia automaticamente execuções interrompidas. O frontend mostra as sete etapas, seleção de canal, nova execução, aprovações, progresso, histórico e player final. O dashboard usa a configuração original salva em cada execução ao retomá-la; o YAML atual é usado para novas execuções.
