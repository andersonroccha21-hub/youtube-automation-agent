---
name: edicao
description: "Skill independente de produção YouTube: video.file, duração, dimensões e sinalização demo."
---

# edicao

Monte seções e cenas na ordem do roteiro usando a duração medida da voz. Renderize visuais, concatene a narração e gere MP4 H.264/AAC via FFmpeg. Inspecione áudio e vídeo com ffprobe.

## Contrato

- Implementação: `skills.edicao.Edicao`.
- Entrada: `pipeline.models.ImagesOutput`.
- Saída: `pipeline.models.EditOutput`, preservando todos os campos anteriores.
- Novos dados: video.file, duração, dimensões e sinalização demo.
- Artefatos: caminhos relativos à raiz da execução, com SHA-256.
- Configuração: exclusivamente pelo `Context.config` carregado do YAML do canal.
- Nunca incorpore nomes, públicos, vozes ou regras de um canal específico no código.

## Execução

O orquestrador registra esta skill em `pipeline/registry.py` e aplica as aprovações devidas. Para desenvolvimento isolado:

```bash
python main.py --channel channels/canal_exemplo/config.yaml \
  --skill edicao --input scratch/input.json \
  --output scratch/edicao.json --assets-dir scratch/artifacts
```

Os arquivos de entrada e artefatos precisam existir e respeitar o contrato. Acrescente `--demo` para fixtures sintéticas sem APIs pagas. Uma skill isolada não executa decisões humanas nem representa um pipeline aprovado. Use o fluxo normal do orquestrador para produção.

Os contratos exportados ficam em `schemas/edicao/`; regenere com `python scripts/export_schemas.py` após mudar os modelos.
