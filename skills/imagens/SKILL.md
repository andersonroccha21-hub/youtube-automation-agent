---
name: imagens
description: "Skill independente de produção YouTube: assets.items com scene_id, artefato, origem e licença."
---

# imagens

Gere imagens pelos prompts ou selecione imagens/B-roll da biblioteca por tags. Registre origem e licença. Não escolha mídia aleatória quando não houver correspondência.

## Contrato

- Implementação: `skills.imagens.Imagens`.
- Entrada: `pipeline.models.NarrationOutput`.
- Saída: `pipeline.models.ImagesOutput`, preservando todos os campos anteriores.
- Novos dados: assets.items com scene_id, artefato, origem e licença.
- Artefatos: caminhos relativos à raiz da execução, com SHA-256.
- Configuração: exclusivamente pelo `Context.config` carregado do YAML do canal.
- Nunca incorpore nomes, públicos, vozes ou regras de um canal específico no código.

## Execução

O orquestrador registra esta skill em `pipeline/registry.py` e aplica as aprovações devidas. Para desenvolvimento isolado:

```bash
python main.py --channel channels/canal_exemplo/config.yaml \
  --skill imagens --input scratch/input.json \
  --output scratch/imagens.json --assets-dir scratch/artifacts
```

Os arquivos de entrada e artefatos precisam existir e respeitar o contrato. Acrescente `--demo` para fixtures sintéticas sem APIs pagas. Uma skill isolada não executa decisões humanas nem representa um pipeline aprovado. Use o fluxo normal do orquestrador para produção.

Os contratos exportados ficam em `schemas/imagens/`; regenere com `python scripts/export_schemas.py` após mudar os modelos.
