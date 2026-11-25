---
name: thumbnail
description: "Skill independente de produção YouTube: thumbnail.candidates com prompt e artefato JPEG."
---

# thumbnail

Exija um título aprovado. Crie variantes e imagens de thumbnail coerentes com sua promessa e a estética do YAML. Não selecione a imagem em nome do humano.

## Contrato

- Implementação: `skills.thumbnail.Thumbnail`.
- Entrada: `pipeline.models.ResearchOutput`.
- Saída: `pipeline.models.ThumbnailOutput`, preservando todos os campos anteriores.
- Novos dados: thumbnail.candidates com prompt e artefato JPEG.
- Artefatos: caminhos relativos à raiz da execução, com SHA-256.
- Configuração: exclusivamente pelo `Context.config` carregado do YAML do canal.
- Nunca incorpore nomes, públicos, vozes ou regras de um canal específico no código.

## Execução

O orquestrador registra esta skill em `pipeline/registry.py` e aplica as aprovações devidas. Para desenvolvimento isolado:

```bash
python main.py --channel channels/canal_exemplo/config.yaml \
  --skill thumbnail --input scratch/input.json \
  --output scratch/thumbnail.json --assets-dir scratch/artifacts
```

Os arquivos de entrada e artefatos precisam existir e respeitar o contrato. Acrescente `--demo` para fixtures sintéticas sem APIs pagas. Uma skill isolada não executa decisões humanas nem representa um pipeline aprovado. Use o fluxo normal do orquestrador para produção.

Os contratos exportados ficam em `schemas/thumbnail/`; regenere com `python scripts/export_schemas.py` após mudar os modelos.
