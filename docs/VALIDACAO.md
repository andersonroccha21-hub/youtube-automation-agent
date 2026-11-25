# Validação da entrega

Validação executada em 25/11/2026, no macOS, com Python 3.12.15 e FFmpeg/ffprobe 9.0.1.

| Verificação | Resultado observado |
|---|---|
| `pytest -q` | 19 testes passaram |
| Ruff: análise estática e formatação | Aprovadas |
| Contratos JSON exportados | Iguais aos modelos usados pelo runtime |
| Quantidade de skills registradas | Exatamente 7 |
| Instalação editável via pip | Concluída; entrypoint `youtube-pipeline` validou o YAML |
| Dependências instaladas: `pip check` | Sem conflitos |
| CLI completo em modo demo | 8 comandos com os códigos de saída esperados |
| Aprovação de títulos | Pausa com código 2; exige seleção de um ID existente |
| Aprovação de thumbnails | Nova pausa; roteiro ainda não existe antes da decisão |
| Aprovação opcional de roteiro | Bloqueia o plano visual até uma decisão explícita |
| Rejeição/revisão | Rejeição impede avanço; revisão invalida etapas e aprovações seguintes |
| Alteração de checkpoint/mídia | Retomada e aprovação recusadas |
| Isolamento de configuração | Configurações alteradas ou de outro canal recusadas na retomada |
| Concorrência na mesma execução | Segundo processo não obtém o lock |
| B-roll local e imagens locais | Seleção por tags e renderização verificadas |
| Adaptadores de texto/imagem/TTS | Contratos HTTP exercitados com respostas simuladas |
| Pesquisa YouTube | Contrato HTTP e coleta de IDs/URLs testados com resposta simulada |
| MP4 demonstrativo | 1280×720, 3 segundos, H.264/AAC, decodificação completa sem erros |
| Retomada após conclusão | Reutilizou os checkpoints e preservou o MP4 existente |

O MP4 demonstrativo e os resultados dos comandos estão em `outputs/validacao` na entrega externa ao projeto. As decisões usadas nos testes são fixtures automatizadas, identificadas como demonstração; não representam aprovação humana de conteúdo de produção. O modo normal do pipeline não oferece autoaprovação.

Não foram executados: chamadas pagas a provedores, autenticação real da YouTube Data API, construção/execução Docker, implantação DigitalOcean, upload ou publicação. O ambiente não disponibiliza Docker. O workflow CI foi configurado para Python 3.11–3.13, mas não foi executado remotamente nesta entrega.

## Dashboard FastAPI — atualização 3.1

O projeto passou a incluir `web/`, com FastAPI, fila local em segundo plano e frontend HTML/JavaScript/Tailwind compilado. O CLI foi preservado.

- Suíte completa: **28 testes passaram**, incluindo os 19 testes anteriores e 9 testes web.
- Ruff e verificação de sintaxe JavaScript aprovados; `pip check` sem conflitos.
- Testes web cobrem descoberta de YAML/YML, configurações inválidas, IDs duplicados, canais isolados, início de execução, aprovações obrigatórias e opcionais, revisão, rejeição, retomada e bloqueio de ações concorrentes.
- Aprovações de versões antigas e arquivos de mídia alterados foram recusadas. A API não disponibiliza `state.json`, `.env` nem arquivos fora dos artefatos registrados.
- Vídeo final servido com suporte a HTTP Range, validado com resposta 206.
- Servidor iniciado e acessado em `http://localhost:8000` pelo navegador real.
- Pelo formulário web, foi criada uma demonstração sintética, selecionados título e thumbnail e concluídas as sete etapas. As decisões estão identificadas como teste automatizado, somente em modo DEMO.
- O player carregou o MP4 com duração de 3 segundos e dimensões 1280×720; `readyState=4` e console sem erros.
- Layout conferido no desktop e em viewport de 390×844. A sequência do pipeline usa rolagem própria; não houve overflow horizontal da página.
- Capturas de tela foram salvas na entrega em `outputs/dashboard-preview.jpg` e `outputs/dashboard-mobile.jpg`.

O TestClient da versão instalada do Starlette emitiu um aviso de depreciação relacionado ao transporte `httpx`; isso não impediu os testes. Não foram feitas chamadas pagas, implantação externa ou publicação do dashboard.
